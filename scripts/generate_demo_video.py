#!/usr/bin/env python3
"""Generate a camera-free demo MP4 that perception can use as SOURCE.

Draws toy-car kits (1 red body, 2 black wheels, 1 blue roof) inside the default
inspection zone so OpenCV HSV counting works without a phone/RTSP stream.

Usage:
  python scripts/generate_demo_video.py
  python scripts/generate_demo_video.py --out runs/demo_line.mp4 --seconds 24

Then:
  SOURCE=runs/demo_line.mp4 REPLAY_LOOP=1 PLANNER=rule ROBOT_ADAPTER=mock \\
    bash scripts/start_all.sh
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

# BGR colors tuned to services/perception/config/colors.json HSV ranges.
BG = (235, 238, 242)          # light matte tabletop
RED_BODY = (25, 25, 210)      # H≈0–2, S high, V high
BLUE_ROOF = (210, 90, 20)     # H≈105–115
BLACK_WHEEL = (18, 18, 18)    # V low
TRAY = (250, 250, 250)
ZONE_HINT = (210, 215, 220)
LABEL = (80, 85, 95)


def blank(w: int, h: int) -> np.ndarray:
    frame = np.full((h, w, 3), BG, dtype=np.uint8)
    # Soft inspection-zone hint (center 35–65% x, 30–70% y) so humans see the target area.
    x0, y0 = int(0.35 * w), int(0.30 * h)
    x1, y1 = int(0.65 * w), int(0.70 * h)
    cv2.rectangle(frame, (x0, y0), (x1, y1), ZONE_HINT, 2)
    cv2.putText(frame, "inspection zone", (x0 + 8, y0 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, LABEL, 1, cv2.LINE_AA)
    return frame


def draw_kit(frame: np.ndarray, cx: int, cy: int, *, missing_wheel: bool = False) -> None:
    """Draw one kit centered at (cx, cy). Parts stay well inside the inspection zone."""
    # White tray under the kit for contrast.
    cv2.rectangle(frame, (cx - 95, cy - 70), (cx + 95, cy + 70), TRAY, -1)
    cv2.rectangle(frame, (cx - 95, cy - 70), (cx + 95, cy + 70), (180, 185, 190), 1)

    # Red body (rectangle) — area comfortably above min_area 900 at 960-wide.
    cv2.rectangle(frame, (cx - 55, cy - 18), (cx + 55, cy + 28), RED_BODY, -1)

    # Blue roof on top of the body.
    roof = np.array([[cx - 40, cy - 18], [cx + 40, cy - 18], [cx + 28, cy - 48], [cx - 28, cy - 48]], dtype=np.int32)
    cv2.fillConvexPoly(frame, roof, BLUE_ROOF)

    # Two black circular wheels (circularity ≈ 1.0).
    r = 18
    cv2.circle(frame, (cx - 38, cy + 42), r, BLACK_WHEEL, -1)
    if not missing_wheel:
        cv2.circle(frame, (cx + 38, cy + 42), r, BLACK_WHEEL, -1)


def draw_queue_kits(frame: np.ndarray, n: int) -> None:
    """Place n queued kits in the default assembly_queue zone (right side)."""
    h, w = frame.shape[:2]
    for i in range(n):
        qx = int(0.82 * w)
        qy = int(0.38 * h + i * 0.12 * h)
        # Tiny queue placeholders (outside inspection counting) for visual realism.
        cv2.rectangle(frame, (qx - 30, qy - 18), (qx + 30, qy + 18), (200, 120, 80), -1)


def scene_empty(w: int, h: int, queue: int = 2) -> np.ndarray:
    frame = blank(w, h)
    draw_queue_kits(frame, queue)
    cv2.putText(frame, "EMPTY", (24, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, LABEL, 2, cv2.LINE_AA)
    return frame


def scene_kit(w: int, h: int, *, missing_wheel: bool, label: str, queue: int = 2) -> np.ndarray:
    frame = blank(w, h)
    draw_queue_kits(frame, queue)
    # Center of default inspection_zone.
    cx, cy = int(0.50 * w), int(0.50 * h)
    draw_kit(frame, cx, cy, missing_wheel=missing_wheel)
    cv2.putText(frame, label, (24, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, LABEL, 2, cv2.LINE_AA)
    return frame


def write_video(path: Path, width: int, height: int, fps: int, timeline: list[tuple[str, float, dict]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # mp4v is what perception's evidence writer uses; widely readable by OpenCV VideoCapture.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"could not open VideoWriter for {path}")

    for kind, seconds, opts in timeline:
        n = max(1, int(round(seconds * fps)))
        for _ in range(n):
            if kind == "empty":
                frame = scene_empty(width, height, queue=opts.get("queue", 2))
            else:
                frame = scene_kit(
                    width, height,
                    missing_wheel=opts.get("missing_wheel", False),
                    label=opts.get("label", "KIT"),
                    queue=opts.get("queue", 2),
                )
            writer.write(frame)
    writer.release()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="runs/demo_line.mp4", help="output MP4 path")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=25)
    args = ap.parse_args()

    # Timeline notes:
    # - still ≥1s (STABLE_SECONDS) so perception inspects
    # - empty ≥1.5s (EMPTY_SECONDS) to reset the FSM between distinct kits
    # - for recovery kits: incomplete → hard-cut to complete (no empty) so MockArm's
    #   ~4s execute + reinspect sees the "fixed" kit instead of the still-missing frame
    timeline: list[tuple[str, float, dict]] = [
        ("kit", 3.5, {"missing_wheel": False, "label": "KIT A — complete (1B 2W 1R)", "queue": 3}),
        ("empty", 2.0, {"queue": 2}),
        ("kit", 2.0, {"missing_wheel": True, "label": "KIT B — missing black_wheel", "queue": 2}),
        ("kit", 5.5, {"missing_wheel": False, "label": "KIT B — recovered (wheel added)", "queue": 2}),
        ("empty", 2.0, {"queue": 1}),
        ("kit", 3.5, {"missing_wheel": False, "label": "KIT C — complete (1B 2W 1R)", "queue": 1}),
        ("empty", 2.0, {"queue": 0}),
        ("kit", 2.0, {"missing_wheel": True, "label": "KIT D — missing black_wheel", "queue": 0}),
        ("kit", 5.5, {"missing_wheel": False, "label": "KIT D — recovered (wheel added)", "queue": 0}),
        ("empty", 2.0, {"queue": 0}),
    ]

    out = Path(args.out)
    write_video(out, args.width, args.height, args.fps, timeline)
    total = sum(s for _, s, _ in timeline)
    print(f"wrote {out} ({args.width}x{args.height} @ {args.fps}fps, ~{total:.0f}s)")
    print("use with:")
    print(f"  SOURCE={out} REPLAY_LOOP=1 PLANNER=rule ROBOT_ADAPTER=mock bash scripts/start_all.sh")


if __name__ == "__main__":
    main()
