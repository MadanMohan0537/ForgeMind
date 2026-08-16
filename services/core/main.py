"""ForgeMind core: event store + orchestrator + station buttons + metrics + analysis API.

Run:  uvicorn services.core.main:app --host 0.0.0.0 --port 8100
Env:  ROBOT_URL (http://127.0.0.1:8200)  PERCEPTION_URL (http://127.0.0.1:8150)
      PLANNER=llm|rule (default llm, falls back to rule)  FORGE_DB (runs/forgemind.sqlite)
      CORE_STALL_SECONDS (180) — how long a kit may sit mid-recovery before core calls a human.
        Must stay above the robot service's HUMAN_TIMEOUT_SECONDS or it will interrupt a
        human who is still placing the part.
      CORE_WATCHDOG_INTERVAL (5) — how often the stall watchdog scans.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ValidationError

from shared.schemas import (REQUIRED_PARTS, ActionProposal, Event, EventType as E, ExperimentPlan,
                            HypothesisSet, Kit, KitState as S, RobotRequest, RunMetrics,
                            VerificationVerdict, WorldState)
from services.core import governor, metrics as M
from services.core.db import Store
from services.core.state_machine import IllegalTransition, is_escape, next_state

try:
    # The LLM client pulls in the OpenAI SDK. Core must boot and run the whole physical
    # loop without it: PLANNER falls back to the rule planner and /analysis returns 503.
    from services.core import llm
    LLM_IMPORT_ERROR: Optional[str] = None
except Exception as _ex:  # noqa: BLE001
    llm = None  # type: ignore[assignment]
    LLM_IMPORT_ERROR = str(_ex)

ROBOT_URL = os.environ.get("ROBOT_URL", "http://127.0.0.1:8200")
PERCEPTION_URL = os.environ.get("PERCEPTION_URL", "http://127.0.0.1:8150")
STALL_SECONDS = float(os.environ.get("CORE_STALL_SECONDS", "180"))
WATCHDOG_INTERVAL = float(os.environ.get("CORE_WATCHDOG_INTERVAL", "5"))
STATIC = Path(__file__).parent / "static"

# Shared-secret gate for everything that changes state. Unset (the default) means no gate,
# which is what the stations need on a plain LAN. Set FORGE_TOKEN on the Spark and every
# page picks it up from its own URL (?token=...), so phones keep working after one scan.
# This is a wrong-device guard on a hackathon network, not real authentication: a token
# handed to a browser is readable by anyone holding that browser.
TOKEN = os.environ.get("FORGE_TOKEN", "").strip()
CORS_ORIGINS = [o.strip() for o in os.environ.get("FORGE_CORS_ORIGINS", "*").split(",") if o.strip()]
# Perception, the robot service and the agent all run on the Spark and post to core over
# loopback without a token. Exempting loopback keeps the gate aimed at what it is for —
# other devices on the venue network — without making three other services carry a secret.
# Set FORGE_TRUST_LOOPBACK=0 if you want even same-box callers to authenticate.
TRUST_LOOPBACK = os.environ.get("FORGE_TRUST_LOOPBACK", "1") != "0"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

# States a kit must not sit in forever. Each is waiting on another service to answer.
STALLABLE_STATES = {S.HELD, S.RECOVERY_PROPOSED, S.RECOVERING, S.REVERIFYING}

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Adopt an unfinished run, then run the stall watchdog for the life of the process.

    Core restarting mid-run (a crash, or someone re-running start_all.sh) used to send
    every later event to an implicit "scratch" run, quietly truncating the run the team
    was recording.
    """
    open_run = store.active_run()
    if open_run:
        info = _adopt_run(open_run)
        print(f"[core] resumed run {info['run_id']} ({info['mode']}) with {info['kits']} kits", flush=True)
    if llm is None:
        print(f"[core] LLM client unavailable ({LLM_IMPORT_ERROR}); planner=rule, /analysis disabled", flush=True)
    watchdog = asyncio.create_task(_watchdog())
    try:
        yield
    finally:
        watchdog.cancel()


app = FastAPI(title="ForgeMind core", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
store = Store()


@app.middleware("http")
async def require_token(request, call_next):
    """Gate state-changing requests on the shared token, when one is configured.

    Off by default. With FORGE_TOKEN set, a POST must carry it as an X-Forge-Token header
    or a ?token= query parameter. GETs are never gated — a judge or a teammate loading the
    dashboard must not need a secret, and reading is harmless. Same-box services posting
    over loopback are exempt unless FORGE_TRUST_LOOPBACK=0.
    """
    if TOKEN and request.method not in ("GET", "HEAD", "OPTIONS"):
        host = request.client.host if request.client else ""
        if not (TRUST_LOOPBACK and host in LOOPBACK_HOSTS):
            supplied = request.headers.get("x-forge-token") or request.query_params.get("token", "")
            if not secrets.compare_digest(supplied, TOKEN):
                return JSONResponse({"detail": "missing or bad X-Forge-Token"}, status_code=401)
    return await call_next(request)


# --------------------------------------------------------------------------- #
# In-memory state (everything durable is in the Store)
# --------------------------------------------------------------------------- #
class Live:
    run_id: Optional[str] = None
    mode: str = "recovery"                # baseline | recovery | improved
    telemetry: dict = {"workspace_clear": True, "zone_occupied": False, "fps": 0, "queue": {}}
    token_to_kit: dict[str, str] = {}
    kit_counter: int = 0
    robot_status: dict = {"state": "unknown"}
    ws_clients: set[WebSocket] = set()
    last_zone_status_clear: Optional[bool] = None
    last_queue: dict[str, int] = {}
    stall_escalated: set[str] = set()     # kit ids the watchdog has already handed to a human
    # Switchable at runtime via POST /admin/llm, so bringing a model up mid-night does not
    # need a restart. Falls back to the rule planner when the LLM client is unavailable.
    planner: str = os.environ.get("PLANNER", "llm") if llm is not None else "rule"


live = Live()
_http = httpx.AsyncClient(timeout=5.0)


def _current_run_id() -> str:
    if live.run_id is None:
        _start_run("scratch", "recovery", notes="implicit run")
    return live.run_id  # type: ignore[return-value]


def _reset_live_run_state() -> None:
    """Clear everything that is scoped to one run.

    The telemetry de-duplication keys belong here: they are what stops core writing a
    ZONE_STATUS/QUEUE_MEASURED row for every frame, and if they survive into the next
    run its first telemetry reading is dropped as "unchanged".
    """
    live.token_to_kit = {}
    live.kit_counter = 0
    live.last_zone_status_clear = None
    live.last_queue = {}
    live.stall_escalated = set()


def _start_run(run_id: str, mode: str, notes: str = "") -> dict:
    live.run_id, live.mode = run_id, mode
    _reset_live_run_state()
    store.start_run(run_id, mode, time.time(), notes)
    return {"run_id": run_id, "mode": mode}


def _adopt_run(run: dict) -> dict:
    """Continue an existing run after a core restart.

    Rebuilds the in-memory state that would otherwise be lost: the run id and mode, the
    kit counter (so the next kit is not kit_01 again) and perception's token map (so a
    kit already in the inspection zone is still recognised as the same kit).
    """
    live.run_id, live.mode = run["run_id"], run["mode"]
    _reset_live_run_state()
    kits = store.kits(live.run_id)
    live.kit_counter = max((int(k.kit_id.rsplit("_", 1)[-1]) for k in kits
                            if k.kit_id.rsplit("_", 1)[-1].isdigit()), default=0)
    for e in store.events(run_id=live.run_id):
        token = (e.payload or {}).get("perception_token")
        if token and e.kit_id:
            live.token_to_kit[token] = e.kit_id
    return {"run_id": live.run_id, "mode": live.mode, "kits": len(kits)}


async def _broadcast(obj: dict) -> None:
    dead = []
    for ws in list(live.ws_clients):
        try:
            await ws.send_text(json.dumps(obj, default=str))
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        live.ws_clients.discard(ws)


async def emit(event: E, kit: Optional[Kit] = None, payload: Optional[dict] = None, *, source: str = "core",
               run_id: Optional[str] = None, evidence_path: Optional[str] = None) -> Event:
    """Append an event, apply the kit state machine, broadcast. Returns the stored event."""
    ev = Event(run_id=run_id or _current_run_id(), event=event, kit_id=kit.kit_id if kit else None,
               payload=payload or {}, source=source, evidence_path=evidence_path)
    if kit is not None:
        try:
            prev = kit.state
            incomplete = bool(kit.missing or kit.extra)
            kit.state = next_state(kit.state, event)
            if is_escape(prev, event, incomplete):
                ev.payload["escape"] = True
        except IllegalTransition as ex:
            ev.payload["illegal_transition"] = str(ex)
        kit.last_event = event.value
        if event == E.KIT_STARTED and kit.started_ts is None:
            kit.started_ts = ev.ts
        if event in (E.QC_APPROVED, E.QC_REJECTED):
            kit.finished_ts = ev.ts
        store.save_kit(kit)
    store.append(ev)
    await _broadcast({"type": "event", "event": ev.model_dump(), "kit": kit.model_dump() if kit else None})
    return ev


def _new_kit(run_id: str) -> Kit:
    live.kit_counter += 1
    kit = Kit(kit_id=f"kit_{live.kit_counter:02d}", run_id=run_id, started_ts=time.time())
    store.save_kit(kit)
    return kit


def _oldest_kit(run_id: str, states: set[S]) -> Optional[Kit]:
    kits = store.kits_in_state(run_id, states)
    return kits[0] if kits else None


def _supervise(coro: Awaitable[None], kit_id: str, run_id: str, what: str) -> None:
    """Run a background orchestration step, and never let it fail silently.

    A bare `create_task` drops its exception on the floor: the kit stays parked in a
    transient state, nothing appears on the dashboard, and the run looks fine until
    someone notices a kit that never moved. Any unexpected failure here becomes a
    logged, recorded HUMAN_REVIEW_REQUESTED instead.
    """
    async def runner() -> None:
        try:
            await coro
        except Exception as ex:  # noqa: BLE001
            print(f"[core] {what} failed for {kit_id}: {ex}\n{traceback.format_exc()}", flush=True)
            kit = store.kit(kit_id, run_id)
            if kit is not None and kit.state in STALLABLE_STATES:
                await emit(E.HUMAN_REVIEW_REQUESTED, kit,
                           {"reason": f"core error during {what}: {str(ex)[:160]}"}, run_id=run_id)

    asyncio.create_task(runner())


# --------------------------------------------------------------------------- #
# Orchestrator: what happens after an inspection
# --------------------------------------------------------------------------- #
def _apply_inspection(kit: Kit, payload: dict) -> None:
    detected = {k: int(v) for k, v in (payload.get("detected") or {}).items()}
    missing = {p: REQUIRED_PARTS[p] - detected.get(p, 0) for p in REQUIRED_PARTS if detected.get(p, 0) < REQUIRED_PARTS[p]}
    extra = {p: detected.get(p, 0) - REQUIRED_PARTS.get(p, 0) for p in detected if detected.get(p, 0) > REQUIRED_PARTS.get(p, 0)}
    payload["missing"], payload["extra"] = missing, extra
    kit.detected, kit.missing, kit.extra = detected, missing, extra
    kit.confidence = float(payload.get("confidence", 0.0))


async def _after_inspection(kit: Kit, payload: dict) -> None:
    complete = not kit.missing and not kit.extra
    if live.mode == "baseline":
        return  # observe only: no holds, no recovery. Escapes get counted when Bob takes the kit.
    if kit.state == S.ARRIVED:
        if complete:
            await emit(E.KIT_RELEASED, kit, {"reason": "complete on first inspection"})
        else:
            await emit(E.KIT_HELD, kit, {"missing": kit.missing, "extra": kit.extra})
            _supervise(_recovery_flow(kit.kit_id, kit.run_id), kit.kit_id, kit.run_id, "recovery")
    elif kit.state == S.REVERIFYING:
        if complete:
            await emit(E.RECOVERY_VERIFIED, kit, {"verification_confidence": kit.confidence})
            await emit(E.KIT_RELEASED, kit, {"reason": "recovery verified"})
        else:
            kit.retry_count += 1
            await emit(E.RECOVERY_FAILED, kit, {"missing": kit.missing, "extra": kit.extra, "retry_count": kit.retry_count})
            if kit.retry_count <= governor.MAX_RETRIES:
                _supervise(_recovery_flow(kit.kit_id, kit.run_id), kit.kit_id, kit.run_id, "recovery retry")
            else:
                await emit(E.HUMAN_REVIEW_REQUESTED, kit, {"reason": "retry limit exceeded"})
    elif kit.state in (S.HELD, S.HUMAN_REVIEW):
        if complete:
            if kit.state == S.HUMAN_REVIEW:
                await emit(E.HUMAN_RESOLVED, kit, {"resolved_by": "camera confirmed complete"})
            await emit(E.KIT_RELEASED, kit, {"reason": "re-inspection complete"})
    # RECOVERY_PROPOSED / RECOVERING: ignore mid-action inspections (hand in the zone)


async def _robot_status() -> dict:
    try:
        r = await _http.get(f"{ROBOT_URL}/robot/status")
        live.robot_status = r.json()
    except Exception as ex:  # noqa: BLE001
        live.robot_status = {"state": "unreachable", "error": str(ex)}
    return live.robot_status


async def _recovery_flow(kit_id: str, run_id: Optional[str] = None) -> None:
    kit = store.kit(kit_id, run_id)
    if kit is None:
        return
    rs = await _robot_status()
    world = WorldState(kit_id=kit.kit_id, kit_in_inspection_zone=bool(live.telemetry.get("zone_occupied", True)),
                       workspace_clear=bool(live.telemetry.get("workspace_clear", True)),
                       detection_confidence=kit.confidence, detected=kit.detected, missing=kit.missing,
                       extra=kit.extra, retry_count=kit.retry_count, robot_state=rs.get("state", "unknown"))
    # 1. plan (LLM proposes; deterministic rule if it fails)
    proposal: ActionProposal
    if live.planner == "llm" and llm is not None:
        try:
            proposal = await asyncio.to_thread(llm.propose_action, world)
        except Exception as ex:  # noqa: BLE001
            proposal = governor.rule_planner(world)
            proposal.rationale += f" (llm fallback: {str(ex)[:80]})"
    else:
        proposal = governor.rule_planner(world)
    await emit(E.RECOVERY_PROPOSED, kit, {"proposal": proposal.model_dump(), "world": world.model_dump()}, source="planner")
    # 2. govern
    decision = governor.validate(proposal, world)
    if proposal.action == "HOLD_FOR_HUMAN" or not decision.allowed:
        # The planner asking for a human is a legal outcome, not a failed check, so
        # decision.reasons is empty for it. Carry the rationale across or the dashboard
        # shows a denial with no explanation.
        await emit(E.RECOVERY_DENIED, kit, {"reasons": decision.reasons, "checks": decision.checks,
                                            "action": proposal.action, "rationale": proposal.rationale},
                   source="governor")
        await emit(E.HUMAN_REVIEW_REQUESTED, kit, {"reason": "; ".join(decision.reasons) or "planner requested human"})
        return
    if proposal.action == "RELEASE":
        await emit(E.KIT_RELEASED, kit, {"reason": "planner+governor release"})
        return
    await emit(E.RECOVERY_APPROVED, kit, {"checks": decision.checks, "action": proposal.model_dump()}, source="governor")
    # 3. actuate — the ONLY place the robot is called
    req = RobotRequest(kit_id=kit.kit_id, part=proposal.part, quantity=1, source_bin=proposal.source_bin,  # type: ignore[arg-type]
                       target_zone=proposal.target_zone, action_id=uuid.uuid4().hex[:8], run_id=kit.run_id)
    try:
        r = await _http.post(f"{ROBOT_URL}/robot/add-part", json=req.model_dump())
        if r.status_code >= 400:
            raise RuntimeError(r.text)
    except Exception as ex:  # noqa: BLE001
        await emit(E.ROBOT_ERROR, kit, {"error": str(ex)}, source="robot")
        await emit(E.HUMAN_REVIEW_REQUESTED, kit, {"reason": f"robot error: {str(ex)[:120]}"})
    # RECOVERY_EXECUTED arrives from the robot service via POST /events, which triggers re-inspection.


async def _request_reinspection(kit: Optional[Kit] = None) -> None:
    """Ask perception to re-inspect now.

    Perception may be down or restarting. That is survivable — the kit stays in
    REVERIFYING and the stall watchdog escalates it — but it must be recorded, because
    an un-recorded failure here looks exactly like "the camera saw nothing wrong".
    """
    try:
        await _http.post(f"{PERCEPTION_URL}/inspect_now")
    except Exception as ex:  # noqa: BLE001
        print(f"[core] re-inspection request failed: {ex}", flush=True)
        await emit(E.ZONE_STATUS, None, {"reinspection_request_failed": str(ex)[:160],
                                         "kit_id": kit.kit_id if kit else None}, source="core")


async def _watchdog() -> None:
    """Escalate kits that stopped moving.

    Every transient state is core waiting on somebody else: the planner, the robot
    service, the camera. If that answer never comes the kit would sit there for the
    rest of the run with no event explaining why. This turns the silence into a
    HUMAN_REVIEW_REQUESTED that shows up on the recovery station and in the metrics.
    """
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        try:
            run_id = live.run_id
            if not run_id:
                continue
            now = time.time()
            for kit in store.kits_in_state(run_id, STALLABLE_STATES):
                if kit.kit_id in live.stall_escalated:
                    continue
                last = store.last_event_ts(run_id, kit.kit_id)
                if last is None or now - last < STALL_SECONDS:
                    continue
                live.stall_escalated.add(kit.kit_id)
                await emit(E.HUMAN_REVIEW_REQUESTED, kit,
                           {"reason": f"stalled in {kit.state.value} for {int(now - last)}s with no further events",
                            "stalled_state": kit.state.value, "stalled_seconds": int(now - last)},
                           source="watchdog", run_id=run_id)
        except Exception as ex:  # noqa: BLE001
            print(f"[core] watchdog error: {ex}", flush=True)




# --------------------------------------------------------------------------- #
# Event ingestion (perception, robot, stations, agent all POST here)
# --------------------------------------------------------------------------- #
class EventIn(BaseModel):
    event: E
    run_id: Optional[str] = None
    kit_id: Optional[str] = None
    payload: dict = {}
    evidence_path: Optional[str] = None
    source: str = "external"


@app.post("/events")
async def post_event(ev: EventIn) -> dict:
    run_id = ev.run_id or _current_run_id()
    payload = dict(ev.payload)
    kit: Optional[Kit] = None

    # -- telemetry (persist only on change to keep the log readable) ---------
    if ev.event == E.ZONE_STATUS:
        live.telemetry.update({k: payload[k] for k in ("workspace_clear", "zone_occupied", "fps") if k in payload})
        wc = payload.get("workspace_clear")
        if wc is not None and wc != live.last_zone_status_clear:
            live.last_zone_status_clear = wc
            await emit(E.ZONE_STATUS, None, payload, source=ev.source, run_id=run_id)
        else:
            await _broadcast({"type": "telemetry", "telemetry": live.telemetry})
        return {"ok": True}
    if ev.event == E.QUEUE_MEASURED:
        zone, count = payload.get("zone", "assembly_queue"), int(payload.get("count", 0))
        live.telemetry.setdefault("queue", {})[zone] = count
        if live.last_queue.get(zone) != count:
            live.last_queue[zone] = count
            await emit(E.QUEUE_MEASURED, None, payload, source=ev.source, run_id=run_id)
        else:
            await _broadcast({"type": "telemetry", "telemetry": live.telemetry})
        return {"ok": True}

    # -- resolve which kit this event is about ---------------------------------
    if ev.kit_id:
        kit = store.kit(ev.kit_id, run_id)
        if kit is None:
            kit = Kit(kit_id=ev.kit_id, run_id=run_id, started_ts=time.time())
    elif ev.event == E.KIT_STARTED:
        kit = _new_kit(run_id)
    elif ev.event == E.KIT_SENT:
        kit = _oldest_kit(run_id, {S.PREPARING}) or _new_kit(run_id)
    elif ev.event in (E.KIT_ARRIVED, E.KIT_INSPECTED):
        token = payload.get("perception_token")
        if token and token in live.token_to_kit:
            kit = store.kit(live.token_to_kit[token], run_id)
        else:
            kit = _oldest_kit(run_id, {S.SENT}) or _oldest_kit(run_id, {S.PREPARING}) or _new_kit(run_id)
            if token:
                live.token_to_kit[token] = kit.kit_id
    elif ev.event == E.KIT_RECEIVED:
        kit = (_oldest_kit(run_id, {S.RELEASED}) or
               _oldest_kit(run_id, {S.HELD, S.HUMAN_REVIEW, S.RECOVERY_PROPOSED, S.RECOVERING, S.REVERIFYING, S.ARRIVED}) or
               _oldest_kit(run_id, {S.SENT, S.PREPARING}) or _new_kit(run_id))
    elif ev.event == E.CAR_DONE:
        kit = _oldest_kit(run_id, {S.AT_ASSEMBLY})
    elif ev.event in (E.QC_APPROVED, E.QC_REJECTED):
        kit = _oldest_kit(run_id, {S.ASSEMBLED}) or _oldest_kit(run_id, {S.AT_ASSEMBLY})
    elif ev.event == E.HUMAN_RESOLVED:
        kit = _oldest_kit(run_id, {S.HUMAN_REVIEW}) or _oldest_kit(run_id, {S.HELD})
    elif ev.event in (E.RECOVERY_EXECUTED, E.ROBOT_ERROR):
        kit = _oldest_kit(run_id, {S.RECOVERING})

    if kit is None and ev.event in (E.CAR_DONE, E.QC_APPROVED, E.QC_REJECTED, E.HUMAN_RESOLVED):
        raise HTTPException(409, f"no kit is in the right state for {ev.event.value}")

    if ev.event == E.KIT_INSPECTED and kit is not None:
        _apply_inspection(kit, payload)
        live.telemetry["zone_occupied"] = True     # the inspection itself is evidence the kit is in the zone

    stored = await emit(ev.event, kit, payload, source=ev.source, run_id=run_id, evidence_path=ev.evidence_path)

    # -- hooks --------------------------------------------------------------------
    if ev.event == E.KIT_INSPECTED and kit is not None:
        await _after_inspection(kit, payload)
    elif ev.event in (E.RECOVERY_EXECUTED, E.HUMAN_RESOLVED):
        await _request_reinspection(kit)
    return {"ok": True, "event_id": stored.id, "kit_id": kit.kit_id if kit else None,
            "kit_state": kit.state.value if kit else None}


@app.get("/events")
def get_events(run_id: Optional[str] = None, since_id: int = 0, limit: int = 2000,
               tail: bool = False) -> list[dict]:
    """Events in id order. `tail=true` returns the newest `limit` rows instead of the oldest.

    Leave `tail` false when polling with `since_id`, or a burst larger than `limit`
    would skip the middle of the log.
    """
    return [e.model_dump() for e in store.events(run_id=run_id, since_id=since_id, limit=limit, tail=tail)]


# --------------------------------------------------------------------------- #
# Runs, kits, metrics
# --------------------------------------------------------------------------- #
class RunStart(BaseModel):
    mode: str = "recovery"       # baseline | recovery | improved
    run_id: Optional[str] = None
    notes: str = ""


@app.post("/runs/start")
async def runs_start(r: RunStart) -> dict:
    n = len([x for x in store.runs() if x["mode"] == r.mode]) + 1
    run_id = r.run_id or f"{r.mode}_{n:02d}"
    _start_run(run_id, r.mode, r.notes)
    await emit(E.RUN_STARTED, None, {"mode": r.mode, "notes": r.notes}, run_id=run_id)
    return {"run_id": run_id, "mode": r.mode}


@app.post("/runs/end")
async def runs_end() -> dict:
    if not live.run_id:
        raise HTTPException(409, "no active run")
    rid = live.run_id
    await emit(E.RUN_ENDED, None, {}, run_id=rid)
    store.end_run(rid, time.time())
    live.run_id = None
    return {"ended": rid, "metrics": M.compute(rid, store.events(run_id=rid)).model_dump()}


@app.get("/runs")
def runs_list() -> list[dict]:
    return store.runs()


@app.get("/runs/current")
def runs_current() -> dict:
    return {"run_id": live.run_id, "mode": live.mode}


@app.post("/runs/resume/{run_id}")
async def runs_resume(run_id: str) -> dict:
    """Re-attach to an existing run.

    Core does this by itself on startup for the newest unfinished run. Use this when
    core came up on the wrong run, or when a run was ended by mistake mid-recording.
    """
    run = store.run(run_id)
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    info = _adopt_run(run)
    store.start_run(run_id, run["mode"], run["started_ts"], run.get("notes") or "")   # clears ended_ts
    await emit(E.RUN_STARTED, None, {"mode": run["mode"], "resumed": True, "kits": info["kits"]}, run_id=run_id)
    return info


@app.get("/kits")
def kits(run_id: Optional[str] = None) -> list[dict]:
    return [k.model_dump() for k in store.kits(run_id or live.run_id)]


# Declared before /metrics/{run_id}: otherwise "compare" is read as a run id and the
# dashboard silently gets an empty metrics object instead of a comparison.
@app.get("/metrics/compare/")
@app.get("/metrics/compare")
def metrics_compare(before: str, after: str) -> dict:
    b = M.compute(before, store.events(run_id=before))
    a = M.compute(after, store.events(run_id=after))
    return M.compare(b, a)


@app.get("/metrics/{run_id}")
def metrics_run(run_id: str) -> dict:
    return M.compute(run_id, store.events(run_id=run_id)).model_dump()


@app.get("/state")
async def state() -> dict:
    await _robot_status()
    return {"run": {"run_id": live.run_id, "mode": live.mode}, "telemetry": live.telemetry,
            "robot": live.robot_status, "kits": [k.model_dump() for k in store.kits(live.run_id)],
            "planner": live.planner, "llm_model": llm.MODEL if llm else None,
            "fast_model": llm.FAST_MODEL if llm else None, "auth": bool(TOKEN)}


@app.get("/health")
def health() -> dict:
    return {"ok": True, "run": live.run_id, "planner": live.planner,
            "llm": llm.health() if llm else {"ok": False, "error": LLM_IMPORT_ERROR}}


# --------------------------------------------------------------------------- #
# Runtime configuration. Bringing Lightning up at 3 AM should not need a restart.
# --------------------------------------------------------------------------- #
class LLMConfigIn(BaseModel):
    base_url: Optional[str] = None
    model: Optional[str] = None
    fast_model: Optional[str] = None
    fast_base_url: Optional[str] = None
    planner: Optional[str] = None          # llm | rule


@app.post("/admin/llm")
async def admin_llm(cfg: LLMConfigIn) -> dict:
    """Point core at a different model, or switch the planner, without restarting.

    The model client reads its configuration at import, so before this endpoint existed
    the only way to move from Super to Lightning was a restart — which meant dropping the
    run in progress. (A restart is now survivable, since core re-adopts the open run, but
    it still interrupts a recording.)
    """
    if cfg.planner is not None:
        if cfg.planner not in ("llm", "rule"):
            raise HTTPException(422, "planner must be 'llm' or 'rule'")
        if cfg.planner == "llm" and llm is None:
            raise HTTPException(409, f"cannot use the llm planner: {LLM_IMPORT_ERROR}")
        live.planner = cfg.planner
    fields = {k: v for k, v in cfg.model_dump(exclude={"planner"}).items() if v is not None}
    if fields:
        _require_llm()
        llm.reconfigure(**fields)
    return {"planner": live.planner, "llm_model": llm.MODEL if llm else None,
            "fast_model": llm.FAST_MODEL if llm else None,
            "base_url": llm.BASE_URL if llm else None,
            "health": llm.health() if llm else {"ok": False, "error": LLM_IMPORT_ERROR}}


# --------------------------------------------------------------------------- #
# Station buttons (phones)
# --------------------------------------------------------------------------- #
STATION_ACTIONS: dict[tuple[str, str], E] = {
    ("alice", "start"): E.KIT_STARTED, ("alice", "sent"): E.KIT_SENT,
    ("bob", "received"): E.KIT_RECEIVED, ("bob", "done"): E.CAR_DONE,
    ("charlie", "approve"): E.QC_APPROVED, ("charlie", "reject"): E.QC_REJECTED,
    ("recovery", "resolved"): E.HUMAN_RESOLVED,
}


class StationIn(BaseModel):
    kit_id: Optional[str] = None
    payload: dict = {}


@app.post("/station/{who}/{action}")
async def station_action(who: str, action: str, body: StationIn = StationIn()) -> dict:
    if (who, action) == ("recovery", "done"):
        try:
            r = await _http.post(f"{ROBOT_URL}/robot/human-done")
            return r.json()
        except Exception as ex:  # noqa: BLE001
            raise HTTPException(502, f"robot service unreachable: {ex}")
    key = (who, action)
    if key not in STATION_ACTIONS:
        raise HTTPException(404, f"unknown station action {who}/{action}")
    return await post_event(EventIn(event=STATION_ACTIONS[key], kit_id=body.kit_id, payload=body.payload, source=f"station:{who}"))


# --------------------------------------------------------------------------- #
# Robot proxy (dashboard e-stop / status without CORS pain)
# --------------------------------------------------------------------------- #
@app.get("/robot/status")
async def robot_status() -> dict:
    return await _robot_status()


@app.post("/robot/stop")
async def robot_stop() -> dict:
    r = await _http.post(f"{ROBOT_URL}/robot/stop")
    return r.json()


# --------------------------------------------------------------------------- #
# Analysis (LLM). The sandboxed agent may call these OR do the LLM work itself and submit.
# --------------------------------------------------------------------------- #
def _require_llm() -> None:
    """503 rather than a 500 traceback when core is running without the LLM client.

    Analysis is the only part of core that needs a model. Perception, the governor, the
    recovery loop and every metric keep working without one.
    """
    if llm is None:
        raise HTTPException(503, f"LLM client unavailable: {LLM_IMPORT_ERROR}. "
                                 f"The agent can still POST results to /analysis/submit/{{run_id}}.")


@app.post("/analysis/hypotheses/{run_id}")
async def analysis_hypotheses(run_id: str) -> dict:
    _require_llm()
    evs = store.events(run_id=run_id)
    if not evs:
        raise HTTPException(404, "no events for run")
    m = M.compute(run_id, evs)
    hs = await asyncio.to_thread(llm.generate_hypotheses, run_id, evs, m, {e.id for e in evs if e.id})
    store.save_analysis(run_id, "hypotheses", time.time(), hs.model_dump())
    await emit(E.HYPOTHESES_GENERATED, None, {"count": len(hs.hypotheses), "summary": hs.summary}, source="analyst", run_id=run_id)
    return hs.model_dump()


@app.post("/analysis/experiment/{run_id}")
async def analysis_experiment(run_id: str) -> dict:
    _require_llm()
    hs = store.latest_analysis(run_id, "hypotheses")
    if not hs:
        raise HTTPException(409, "generate hypotheses first")
    m = M.compute(run_id, store.events(run_id=run_id))
    from shared.schemas import HypothesisSet
    plan = await asyncio.to_thread(llm.plan_experiment, HypothesisSet.model_validate(hs), m)
    store.save_analysis(run_id, "experiment", time.time(), plan.model_dump())
    await emit(E.EXPERIMENT_PROPOSED, None, {"change": plan.change, "tests": plan.tests_hypothesis_id}, source="planner", run_id=run_id)
    return plan.model_dump()


class VerifyIn(BaseModel):
    before: str
    after: str
    hypothesis_id: Optional[str] = None
    allow_missing_experiment: bool = False   # opt in to an explicitly uncontrolled comparison


@app.post("/analysis/verify")
async def analysis_verify(v: VerifyIn) -> dict:
    _require_llm()
    hs = store.latest_analysis(v.before, "hypotheses") or {}
    plan = store.latest_analysis(v.before, "experiment")
    hyps = hs.get("hypotheses", [])
    if v.hypothesis_id:
        hyps = [h for h in hyps if h["id"] == v.hypothesis_id]
    if not hyps:
        raise HTTPException(409, "no hypotheses for the before-run")
    # A verdict with no recorded experiment is not a controlled result: the model would be
    # handed an empty plan and left to infer what changed between the runs. Refuse by
    # default, and mark the output plainly when the caller insists.
    if not plan and not v.allow_missing_experiment:
        raise HTTPException(409, f"no experiment plan recorded for {v.before}; run "
                                 f"POST /analysis/experiment/{v.before} first, or pass "
                                 f"allow_missing_experiment=true for an uncontrolled comparison")
    plan = plan or {"change": "not recorded", "uncontrolled": True}
    b = M.compute(v.before, store.events(run_id=v.before))
    a = M.compute(v.after, store.events(run_id=v.after))
    out = []
    for h in hyps:
        verdict = await asyncio.to_thread(llm.verify_hypothesis, h, plan, b, a)
        out.append(verdict.model_dump())
    result = {"before": v.before, "after": v.after, "comparison": M.compare(b, a), "verdicts": out}
    store.save_analysis(v.after, "verification", time.time(), result)
    await emit(E.HYPOTHESIS_VERIFIED, None, {"n": len(out)}, source="verifier", run_id=v.after)
    return result


@app.get("/analysis/{run_id}")
def analysis_get(run_id: str) -> dict:
    return {"hypotheses": store.latest_analysis(run_id, "hypotheses"),
            "experiment": store.latest_analysis(run_id, "experiment"),
            "verification": store.latest_analysis(run_id, "verification"),
            "open_data": store.latest_analysis(run_id, "open_data")}


class SubmitIn(BaseModel):
    kind: str          # hypotheses | experiment | verification | open_data
    data: dict


# What each submitted `kind` must validate against before core stores it. The dashboard
# renders these straight into the Findings tab, so anything that does not match the schema
# would blank that tab mid-demo rather than fail visibly here.
SUBMIT_SCHEMAS: dict[str, type[BaseModel]] = {
    "hypotheses": HypothesisSet,
    "experiment": ExperimentPlan,
}
SUBMIT_EVENTS = {"hypotheses": E.HYPOTHESES_GENERATED, "experiment": E.EXPERIMENT_PROPOSED,
                 "verification": E.HYPOTHESIS_VERIFIED}
# Anything not in SUBMIT_SCHEMAS or here is rejected, so a typo'd kind cannot land in the
# store as analysis nobody will ever read.
SUBMIT_FREEFORM = {"verification", "open_data"}


def _validate_submission(kind: str, data: dict) -> None:
    """Reject analysis that does not match the shared contract.

    The agent produces this outside core, possibly from raw model output, so it is
    untrusted input like any other.
    """
    if kind not in SUBMIT_SCHEMAS and kind not in SUBMIT_FREEFORM:
        raise HTTPException(422, f"unknown analysis kind {kind!r}; "
                                 f"expected one of {sorted(set(SUBMIT_SCHEMAS) | SUBMIT_FREEFORM)}")
    if kind in SUBMIT_SCHEMAS:
        try:
            SUBMIT_SCHEMAS[kind].model_validate(data)
        except ValidationError as ex:
            raise HTTPException(422, f"{kind} does not match the schema: {ex.errors()[:3]}")
    elif kind == "verification":
        # Shaped by core's own /analysis/verify: a comparison plus a list of verdicts.
        verdicts = data.get("verdicts")
        if not isinstance(verdicts, list) or not verdicts:
            raise HTTPException(422, "verification must carry a non-empty 'verdicts' list")
        try:
            for v in verdicts:
                VerificationVerdict.model_validate(v)
        except ValidationError as ex:
            raise HTTPException(422, f"verdict does not match the schema: {ex.errors()[:3]}")


@app.post("/analysis/submit/{run_id}")
async def analysis_submit(run_id: str, s: SubmitIn) -> dict:
    """The sandboxed agent (NemoClaw/OpenShell) submits analysis it produced itself."""
    _validate_submission(s.kind, s.data)
    store.save_analysis(run_id, s.kind, time.time(), s.data)
    if s.kind in SUBMIT_EVENTS:
        await emit(SUBMIT_EVENTS[s.kind], None, {"submitted_by": "agent"}, source="agent", run_id=run_id)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Containment log (OpenShell denials → visible on the dashboard)
# --------------------------------------------------------------------------- #
class Denial(BaseModel):
    agent: str = "forgemind-agent"
    attempted: str
    detail: str = ""
    reporter: str = "unverified"     # who says this was denied; see below


@app.post("/policy/denied")
async def policy_denied(d: Denial, request: Request) -> dict:
    """Record a containment denial reported by the sandbox.

    Core cannot verify that OpenShell actually blocked anything — the denial happens
    inside the sandbox, and this endpoint only hears about it afterwards. So it records
    what it can actually observe: which host posted the claim, and the reporter the
    caller named. It must not stamp `source="openshell"` on an unauthenticated POST,
    which is what it used to do — that fabricated the provenance of the exact evidence
    the containment demo rests on.

    Treat a row as evidence only when `reporter` is the sandbox and the run log shows the
    attempted action did not take effect.
    """
    payload = d.model_dump()
    payload["reported_by_host"] = request.client.host if request.client else "unknown"
    payload["verified_by_core"] = False
    ev = await emit(E.POLICY_DENIED, None, payload, source=f"report:{d.reporter}")
    return {"ok": True, "event_id": ev.id, "verified_by_core": False}


# --------------------------------------------------------------------------- #
# WebSocket + static pages
# --------------------------------------------------------------------------- #
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    live.ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "snapshot", "run": {"run_id": live.run_id, "mode": live.mode},
                                       "telemetry": live.telemetry,
                                       "kits": [k.model_dump() for k in store.kits(live.run_id)],
                                       # tail: a dashboard opened mid-run must see the LAST 200 events,
                                       # not the first 200 followed by a gap.
                                       "events": [e.model_dump() for e in
                                                  store.events(run_id=live.run_id, limit=200, tail=True)]},
                                      default=str))
        while True:
            await ws.receive_text()   # we don't expect messages; keeps the socket alive
    except WebSocketDisconnect:
        pass
    finally:
        live.ws_clients.discard(ws)


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> FileResponse:
    return FileResponse(STATIC / "dashboard.html")


@app.get("/station/{who}", response_class=HTMLResponse)
def station_page(who: str) -> FileResponse:
    return FileResponse(STATIC / "station.html")
