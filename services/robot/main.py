"""ForgeMind robot service. Small API, whitelist everything, one routine.

Run:  ROBOT_ADAPTER=human uvicorn services.robot.main:app --host 0.0.0.0 --port 8200
Env:  ROBOT_ADAPTER=mock|human|isaac_human|real   CORE_URL=http://127.0.0.1:8100
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared.schemas import INSPECTION_ZONE, PART_TO_BIN, RobotRequest, RobotStatus
from services.robot.adapters import HumanArm, IsaacHumanArm, MockArm, RealArm

CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:8100")
ADAPTER = os.environ.get("ROBOT_ADAPTER", "human")

app = FastAPI(title="ForgeMind robot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RobotState:
    state = "idle"
    instruction: Optional[str] = None
    last_action: Optional[dict] = None
    action_id: Optional[str] = None
    step: Optional[str] = None
    lock = threading.Lock()


R = RobotState()


def _on_step(step: str) -> None:
    R.step = step


def _on_instruction(text: Optional[str]) -> None:
    R.instruction = text
    if text:
        R.state = "waiting_operator" if ADAPTER == "isaac_human" else "waiting_human"


if ADAPTER == "mock":
    arm = MockArm(_on_step)
elif ADAPTER == "real":
    arm = RealArm(_on_step)
elif ADAPTER == "isaac_human":
    arm = IsaacHumanArm(_on_step, _on_instruction)
else:
    arm = HumanArm(_on_step, _on_instruction)


def _post_event(event: str, req: RobotRequest, payload: dict) -> None:
    try:
        httpx.post(f"{CORE_URL}/events", json={"event": event, "run_id": req.run_id, "kit_id": req.kit_id,
                                                "payload": payload, "source": "robot"}, timeout=5)
    except Exception as ex:  # noqa: BLE001
        print(f"[robot] could not post {event}: {ex}", flush=True)


def _run(req: RobotRequest) -> None:
    t0 = time.time()
    try:
        R.state = "moving"
        arm.run_add_part(req.part, req.source_bin, req.target_zone)
        R.state = "done"
        R.last_action = {**req.model_dump(), "result": "ok", "seconds": round(time.time() - t0, 1), "adapter": arm.name}
        _post_event("RECOVERY_EXECUTED", req, {"action_id": req.action_id, "part": req.part, "adapter": arm.name,
                                                "seconds": R.last_action["seconds"]})
    except Exception as ex:  # noqa: BLE001
        R.state = "estopped" if "stopped" in str(ex) else "error"
        R.last_action = {**req.model_dump(), "result": "error", "error": str(ex), "adapter": arm.name}
        _post_event("ROBOT_ERROR", req, {"action_id": req.action_id, "error": str(ex)})
    finally:
        R.instruction = None
        R.step = None
        # return to idle shortly so the next kit can be served
        threading.Timer(2.0, lambda: setattr(R, "state", "idle") if R.state in ("done",) else None).start()


@app.get("/robot/status")
def status() -> RobotStatus:
    return RobotStatus(state=R.state, adapter=arm.name, instruction=R.instruction,  # type: ignore[arg-type]
                       last_action=R.last_action, action_id=R.action_id)


@app.post("/robot/add-part")
def add_part(req: RobotRequest) -> dict:
    # Whitelist. Anything not on it is a 400 — this is the last line before physical motion.
    if req.part not in PART_TO_BIN:
        raise HTTPException(400, f"unsupported part {req.part}")
    if req.quantity != 1:
        raise HTTPException(400, "quantity must be exactly 1")
    if req.source_bin != PART_TO_BIN[req.part]:
        raise HTTPException(400, f"source_bin must be {PART_TO_BIN[req.part]} for {req.part}")
    if req.target_zone != INSPECTION_ZONE:
        raise HTTPException(400, f"target_zone must be {INSPECTION_ZONE}")
    with R.lock:
        if R.state in ("moving", "waiting_human", "waiting_operator", "teleoperating"):
            raise HTTPException(409, f"robot busy ({R.state})")
        R.state = "moving"
        R.action_id = req.action_id
    threading.Thread(target=_run, args=(req,), daemon=True).start()
    return {"accepted": True, "action_id": req.action_id, "adapter": arm.name}


@app.post("/robot/stop")
def stop() -> dict:
    arm.stop()
    R.state = "estopped"
    R.instruction = None
    return {"stopped": True}


@app.post("/robot/reset")
def reset() -> dict:
    arm.reset()
    R.state = "idle"
    return {"state": R.state}


@app.get("/robot/last-action")
def last_action() -> dict:
    return R.last_action or {}


@app.post("/robot/human-done")
def human_done() -> dict:
    if isinstance(arm, HumanArm):
        arm.human_done()
        return {"ok": True}
    raise HTTPException(409, f"adapter is {arm.name}, not human")


@app.post("/robot/isaac/accept")
def isaac_accept() -> dict:
    if not isinstance(arm, IsaacHumanArm):
        raise HTTPException(409, f"adapter is {arm.name}, not isaac_human")
    if R.state != "waiting_operator":
        raise HTTPException(409, f"no intervention is awaiting an operator ({R.state})")
    R.state = "teleoperating"
    return {"ok": True, "state": R.state, "action_id": R.action_id}


@app.post("/robot/isaac/complete")
def isaac_complete() -> dict:
    if not isinstance(arm, IsaacHumanArm):
        raise HTTPException(409, f"adapter is {arm.name}, not isaac_human")
    if R.state not in ("waiting_operator", "teleoperating"):
        raise HTTPException(409, f"no active Isaac intervention ({R.state})")
    arm.operator_complete()
    return {"ok": True, "action_id": R.action_id}


@app.post("/robot/isaac/cancel")
def isaac_cancel() -> dict:
    if not isinstance(arm, IsaacHumanArm):
        raise HTTPException(409, f"adapter is {arm.name}, not isaac_human")
    arm.operator_cancel()
    return {"ok": True, "action_id": R.action_id}
