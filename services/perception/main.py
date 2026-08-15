"""ForgeMind perception. Deterministic OpenCV counting; VLM second opinion; events to core.

Run:  SOURCE=rtsp://127.0.0.1:8554/line uvicorn services.perception.main:app --host 0.0.0.0 --port 8150
      SOURCE can also be: 0 (USB cam), http://<phone>:8080/video (IP Webcam MJPEG), path/to/run.mp4 (replay)
Env:  CORE_URL, FRAME_WIDTH (960), STABLE_SECONDS (1.0), EMPTY_SECONDS (1.5), MOTION_THRESH (6.0),
      VLM_URL/VLM_MODEL (optional second opinion), CONF_LOW (0.6), CONF_HIGH (0.9), REPLAY_LOOP (0|1)
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import Counter, deque
from pathlib import Path
from typing import Optional

import cv2
import httpx
import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

from shared.schemas import REQUIRED_PARTS
from services.perception import verify

CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:8100")
SOURCE = os.environ.get("SOURCE", "0")
FRAME_WIDTH = int(os.environ.get("FRAME_WIDTH", "960"))
STABLE_SECONDS = float(os.environ.get("STABLE_SECONDS", "1.0"))
EMPTY_SECONDS = float(os.environ.get("EMPTY_SECONDS", "1.5"))
MOTION_THRESH = float(os.environ.get("MOTION_THRESH", "6.0"))
CONF_LOW, CONF_HIGH = float(os.environ.get("CONF_LOW", "0.6")), float(os.environ.get("CONF_HIGH", "0.9"))
REPLAY_LOOP = os.environ.get("REPLAY_LOOP", "0") == "1"
CFG = Path(__file__).parent / "config"
STATIC = Path(__file__).parent / "static"
EVIDENCE = Path(os.environ.get("EVIDENCE_DIR", "runs/evidence"))
EVIDENCE.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ForgeMind perception")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_json(name: str) -> dict:
    return json.loads((CFG / name).read_text())


def save_json(name: str, data: dict) -> None:
    (CFG / name).write_text(json.dumps(data, indent=2))


class Cfg:
    zones: dict = {k: v for k, v in load_json("zones.json").items() if not k.startswith("_")}
    colors: dict = {k: v for k, v in load_json("colors.json").items() if not k.startswith("_")}
    lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Vision primitives
# --------------------------------------------------------------------------- #
def poly_mask(shape: tuple[int, int], pts_norm: list, ) -> np.ndarray:
    h, w = shape
    pts = np.array([[int(x * w), int(y * h)] for x, y in pts_norm], dtype=np.int32)
    m = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(m, [pts], 255)
    return m


def count_parts(hsv: np.ndarray, zone_mask: np.ndarray, colors: dict) -> tuple[dict[str, int], list]:
    """Returns ({part: count}, [(part, contour)...]) inside the zone."""
    counts: dict[str, int] = {}
    contours_out = []
    for part, spec in colors.items():
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lo, hi in spec["ranges"]:
            mask |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
        mask = cv2.bitwise_and(mask, zone_mask)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        n = 0
        for c in cnts:
            a = cv2.contourArea(c)
            if a < spec.get("min_area", 200) or a > spec.get("max_area", 1e9):
                continue
            if "circularity_min" in spec:
                per = cv2.arcLength(c, True)
                circ = 4 * np.pi * a / (per * per) if per else 0
                if circ < spec["circularity_min"]:
                    continue
            n += 1
            contours_out.append((part, c))
        counts[part] = n
    return counts, contours_out


def motion_score(gray: np.ndarray, prev: Optional[np.ndarray], mask: np.ndarray) -> float:
    if prev is None:
        return 0.0
    d = cv2.absdiff(gray, prev)
    return float(cv2.mean(d, mask=mask)[0])


# --------------------------------------------------------------------------- #
# Zone state machine (per inspection zone)
# --------------------------------------------------------------------------- #
class Inspector:
    """EMPTY -> (occupied & still) -> INSPECTED -> (motion) DISTURBED -> (still) re-INSPECTED ; (empty) -> EMPTY."""

    def __init__(self) -> None:
        self.state = "EMPTY"
        self.token: Optional[str] = None
        self.token_n = 0
        self.still_since: Optional[float] = None
        self.empty_since: Optional[float] = None
        self.window: deque = deque(maxlen=int(os.environ.get("WINDOW_FRAMES", "12")))
        self.force = False
        self.last_result: dict = {}
        self.inspections = 0

    def step(self, occupied: bool, moving: bool, counts: dict, now: float) -> Optional[dict]:
        """Returns an inspection dict when one should be emitted, else None."""
        self.window.append(tuple(sorted(counts.items())))
        if occupied:
            self.empty_since = None
        else:
            self.empty_since = self.empty_since or now
        if moving:
            self.still_since = None
        else:
            self.still_since = self.still_since or now
        still_for = (now - self.still_since) if self.still_since else 0.0
        empty_for = (now - self.empty_since) if self.empty_since else 0.0

        if self.state == "EMPTY":
            if occupied and still_for >= STABLE_SECONDS:
                self.token_n += 1
                self.token = f"p{int(now)}_{self.token_n}"
                self.state = "INSPECTED"
                return self._result(reinspection=False, arrived=True)
        elif self.state == "INSPECTED":
            if not occupied and empty_for >= EMPTY_SECONDS:
                self.state, self.token = "EMPTY", None
            elif moving:
                self.state = "DISTURBED"
            elif self.force and still_for >= 0.3:
                self.force = False
                return self._result(reinspection=True, arrived=False)
        elif self.state == "DISTURBED":
            if not occupied and empty_for >= EMPTY_SECONDS:
                self.state, self.token = "EMPTY", None
            elif still_for >= STABLE_SECONDS:
                self.state = "INSPECTED"
                self.force = False
                return self._result(reinspection=True, arrived=False)
        return None

    def _result(self, reinspection: bool, arrived: bool) -> dict:
        votes = Counter(self.window)
        mode, n = votes.most_common(1)[0]
        confidence = round(n / max(1, len(self.window)), 3)
        detected = {k: int(v) for k, v in mode}
        missing = {p: REQUIRED_PARTS[p] - detected.get(p, 0) for p in REQUIRED_PARTS if detected.get(p, 0) < REQUIRED_PARTS[p]}
        extra = {p: detected.get(p, 0) - REQUIRED_PARTS.get(p, 0) for p in detected if detected.get(p, 0) > REQUIRED_PARTS.get(p, 0)}
        self.inspections += 1
        self.last_result = {"detected": detected, "missing": missing, "extra": extra, "confidence": confidence,
                            "reinspection": reinspection, "arrived": arrived, "perception_token": self.token,
                            "n_frames": len(self.window)}
        return self.last_result


# --------------------------------------------------------------------------- #
# Runtime state shared between the CV thread and HTTP handlers
# --------------------------------------------------------------------------- #
class Live:
    jpeg: Optional[bytes] = None
    lock = threading.Lock()
    counts: dict = {}
    zone_states: dict = {}
    workspace_clear = True
    fps = 0.0
    queue: dict = {}
    frames = 0
    source_ok = False
    last_error: str = ""
    inspector = Inspector()
    ring: deque = deque(maxlen=int(os.environ.get("RING_FRAMES", "150")))   # ~6 s at 25 fps
    last_snapshot: Optional[np.ndarray] = None


L = Live()
_http = httpx.Client(timeout=5.0)


def post_event(event: str, payload: dict, evidence_path: Optional[str] = None) -> None:
    try:
        _http.post(f"{CORE_URL}/events", json={"event": event, "payload": payload, "source": "perception",
                                                "evidence_path": evidence_path})
    except Exception as ex:  # noqa: BLE001
        L.last_error = f"core unreachable: {ex}"


def save_evidence(frame: np.ndarray, token: str, tag: str) -> str:
    p = EVIDENCE / f"{token}_{tag}_{int(time.time())}.jpg"
    cv2.imwrite(str(p), frame)
    return str(p)


def save_clip(token: str, tag: str) -> Optional[str]:
    frames = list(L.ring)
    if len(frames) < 5:
        return None
    p = EVIDENCE / f"{token}_{tag}_{int(time.time())}.mp4"
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(str(p), cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (w, h))
    for f in frames:
        vw.write(f)
    vw.release()
    return str(p)


def second_opinion(image_path: str, result: dict) -> None:
    try:
        v = verify.vlm_verify(image_path)
    except Exception as ex:  # noqa: BLE001
        v = {"error": str(ex)}
    if v:
        post_event("VLM_VERIFICATION", {"perception_token": result["perception_token"], "opencv": result["detected"],
                                        "vlm": v, "agrees": v.get("detected") == result["detected"]}, image_path)


def open_source():
    src: object = SOURCE
    if SOURCE.isdigit():
        src = int(SOURCE)
    cap = cv2.VideoCapture(src)
    if isinstance(src, int):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    return cap


def cv_loop() -> None:
    cap = open_source()
    prev_gray = None
    last_status, last_queue_post = 0.0, 0.0
    robot_still_since: Optional[float] = None
    t_fps, n_fps = time.time(), 0
    is_file = not SOURCE.isdigit() and not SOURCE.startswith(("rtsp", "http", "srt", "udp"))
    while True:
        ok, frame = cap.read()
        if not ok:
            L.source_ok = False
            if is_file and REPLAY_LOOP:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            time.sleep(1.0)
            cap.release()
            cap = open_source()
            continue
        L.source_ok = True
        now = time.time()
        if is_file:
            time.sleep(1.0 / 25)  # real-time pacing for replay
        h0, w0 = frame.shape[:2]
        scale = FRAME_WIDTH / w0
        frame = cv2.resize(frame, (FRAME_WIDTH, int(h0 * scale)))
        H, W = frame.shape[:2]
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        with Cfg.lock:
            zones, colors = dict(Cfg.zones), dict(Cfg.colors)

        annotated = frame.copy()
        for name, pts in zones.items():          # zones first so evidence frames show them
            p = np.array([[int(x * W), int(y * H)] for x, y in pts], dtype=np.int32)
            color = (0, 200, 255) if name == "inspection_zone" else (200, 200, 200)
            cv2.polylines(annotated, [p], True, color, 2)
            cv2.putText(annotated, name, (p[0][0] + 4, p[0][1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        L.ring.append(frame)
        L.last_snapshot = frame

        # --- inspection zone ---------------------------------------------------------
        insp = zones.get("inspection_zone")
        if insp:
            m = poly_mask((H, W), insp)
            counts, cnts = count_parts(hsv, m, colors)
            moving = motion_score(gray, prev_gray, m) > MOTION_THRESH
            occupied = sum(counts.values()) > 0
            L.counts = counts
            res = L.inspector.step(occupied, moving, counts, now)
            L.zone_states["inspection_zone"] = {"state": L.inspector.state, "moving": moving, "occupied": occupied}
            for part, c in cnts:
                cv2.drawContours(annotated, [c], -1, (0, 255, 0), 2)
                x, y, _, _ = cv2.boundingRect(c)
                cv2.putText(annotated, part.split("_")[1], (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
            if res:
                tag = "reinspect" if res["reinspection"] else "inspect"
                ev_path = save_evidence(annotated, res["perception_token"], tag)
                if res["arrived"]:
                    post_event("KIT_ARRIVED", {"perception_token": res["perception_token"]})
                post_event("KIT_INSPECTED", res, ev_path)
                threading.Thread(target=save_clip, args=(res["perception_token"], tag), daemon=True).start()
                if verify.available() and (res["reinspection"] or CONF_LOW <= res["confidence"] < CONF_HIGH or res["missing"]):
                    threading.Thread(target=second_opinion, args=(ev_path, res), daemon=True).start()

        # --- robot zone: workspace clear? -------------------------------------------
        rz = zones.get("robot_zone")
        if rz:
            rm = poly_mask((H, W), rz)
            rmoving = motion_score(gray, prev_gray, rm) > MOTION_THRESH
            robot_still_since = None if rmoving else (robot_still_since or now)
            L.workspace_clear = bool(robot_still_since and now - robot_still_since >= 2.0)

        # --- assembly queue: rough item count -----------------------------------------
        qz = zones.get("assembly_queue")
        if qz and now - last_queue_post > 2.0:
            qm = poly_mask((H, W), qz)
            union = np.zeros((H, W), dtype=np.uint8)
            for spec in colors.values():
                for lo, hi in spec["ranges"]:
                    union |= cv2.inRange(hsv, np.array(lo, dtype=np.uint8), np.array(hi, dtype=np.uint8))
            union = cv2.bitwise_and(union, qm)
            union = cv2.dilate(union, np.ones((25, 25), np.uint8))
            n, _ = cv2.connectedComponents(union)
            L.queue["assembly_queue"] = max(0, n - 1)
            post_event("QUEUE_MEASURED", {"zone": "assembly_queue", "count": L.queue["assembly_queue"]})
            last_queue_post = now

        # --- telemetry -------------------------------------------------------------------
        n_fps += 1
        if now - t_fps >= 1.0:
            L.fps = round(n_fps / (now - t_fps), 1)
            t_fps, n_fps = now, 0
        if now - last_status > 1.0:
            post_event("ZONE_STATUS", {"workspace_clear": L.workspace_clear, "fps": L.fps,
                                       "zone_occupied": bool(L.zone_states.get("inspection_zone", {}).get("occupied"))})
            last_status = now

        # --- HUD ---------------------------------------------------------------------------
        hud = f"{L.inspector.state} {L.counts} conf_frames={len(L.inspector.window)} fps={L.fps} clear={L.workspace_clear}"
        cv2.putText(annotated, hud, (10, H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with L.lock:
                L.jpeg = buf.tobytes()
        prev_gray = gray
        L.frames += 1


@app.on_event("startup")
def _start() -> None:
    threading.Thread(target=cv_loop, daemon=True).start()


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _mjpeg():
    while True:
        with L.lock:
            b = L.jpeg
        if b:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + b + b"\r\n"
        time.sleep(0.05)


@app.get("/video.mjpg")
def video():
    return StreamingResponse(_mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/snapshot.jpg")
def snapshot():
    with L.lock:
        b = L.jpeg
    return Response(content=b or b"", media_type="image/jpeg")


@app.get("/state")
def state() -> dict:
    return {"source": SOURCE, "source_ok": L.source_ok, "fps": L.fps, "frames": L.frames, "counts": L.counts,
            "zone_states": L.zone_states, "workspace_clear": L.workspace_clear, "queue": L.queue,
            "last_inspection": L.inspector.last_result, "inspections": L.inspector.inspections,
            "vlm_available": verify.available(), "last_error": L.last_error}


@app.post("/inspect_now")
def inspect_now() -> dict:
    """Core asks for a re-inspection (after RECOVERY_EXECUTED / HUMAN_RESOLVED)."""
    L.inspector.force = True
    if L.inspector.state == "EMPTY" and L.inspector.window:
        L.inspector.state = "DISTURBED"   # something should be there; treat as disturbed so it re-inspects when still
    return {"forced": True, "state": L.inspector.state}


class ZoneIn(BaseModel):
    name: str
    points: list[list[float]]


@app.get("/zones")
def zones_get() -> dict:
    return Cfg.zones


@app.post("/zones")
def zones_set(z: ZoneIn) -> dict:
    with Cfg.lock:
        Cfg.zones[z.name] = z.points
        save_json("zones.json", {"_comment": "normalized polygon points", **Cfg.zones})
    return Cfg.zones


@app.delete("/zones/{name}")
def zones_del(name: str) -> dict:
    with Cfg.lock:
        Cfg.zones.pop(name, None)
        save_json("zones.json", {"_comment": "normalized polygon points", **Cfg.zones})
    return Cfg.zones


@app.get("/colors")
def colors_get() -> dict:
    return Cfg.colors


@app.post("/colors")
def colors_set(c: dict) -> dict:
    with Cfg.lock:
        Cfg.colors.update({k: v for k, v in c.items() if not k.startswith("_")})
        save_json("colors.json", {"_comment": "HSV ranges", **Cfg.colors})
    return Cfg.colors


@app.get("/calibrate", response_class=HTMLResponse)
def calibrate() -> FileResponse:
    return FileResponse(STATIC / "calibrate.html")


@app.get("/health")
def health() -> dict:
    return {"ok": L.source_ok, "fps": L.fps, "source": SOURCE}
