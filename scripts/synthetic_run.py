"""Drive core exactly like the real system would, without a camera.

  python scripts/synthetic_run.py --mode baseline            # 12 kits, 3 missing a wheel, recovery disabled
  python scripts/synthetic_run.py --mode recovery            # same errors; exercises planner->governor->robot->reverify
  python scripts/synthetic_run.py --mode improved --kits 12  # only kit 8 incomplete
  python scripts/synthetic_run.py --mode recovery --fast     # no sleeps (CI)

Use it to develop the dashboard, LLM prompts and agent while perception is being built.
With ROBOT_ADAPTER=mock the recovery loop closes by itself; with ROBOT_ADAPTER=human someone must tap DONE
on /station/recovery (or pass --auto-human to tap it for you).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import httpx

CORE = "http://127.0.0.1:8100"
REQ = {"red_body": 1, "black_wheel": 2, "blue_roof": 1}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="recovery", choices=["baseline", "recovery", "improved"])
    ap.add_argument("--kits", type=int, default=12)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--auto-human", action="store_true", help="tap DONE at the recovery station automatically")
    ap.add_argument("--core", default=CORE)
    ap.add_argument("--token", default=os.environ.get("FORGE_TOKEN", ""),
                    help="shared token, only needed when core runs with FORGE_TOKEN set "
                         "and you are driving it from another machine")
    a = ap.parse_args()
    headers = {"X-Forge-Token": a.token} if a.token else {}
    c = httpx.Client(base_url=a.core, timeout=30, headers=headers)
    z = 0.05 if a.fast else 1.0
    bad = {3, 7, 11} if a.mode in ("baseline", "recovery") else {8}

    r = c.post("/runs/start", json={"mode": a.mode, "notes": "synthetic"}).json()
    run_id = r["run_id"]
    print(f"run {run_id} ({a.mode})")
    for i in range(1, a.kits + 1):
        missing = i in bad
        c.post("/station/alice/start", json={})
        time.sleep(z * 0.5)
        c.post("/station/alice/sent", json={})
        time.sleep(z * 0.5)
        det = dict(REQ)
        if missing:
            det["black_wheel"] = 1
        tok = f"synth_{run_id}_{i}"
        c.post("/events", json={"event": "KIT_ARRIVED", "payload": {"perception_token": tok}, "source": "replay"})
        res = c.post("/events", json={"event": "KIT_INSPECTED", "source": "replay",
                                       "payload": {"detected": det, "confidence": 0.97, "perception_token": tok}}).json()
        kit_id, state = res["kit_id"], res["kit_state"]
        print(f"  {kit_id}: detected={det} -> {state}")
        if missing and a.mode != "baseline":
            # wait for the recovery loop: planner -> governor -> robot -> RECOVERY_EXECUTED -> reinspection request
            deadline = time.time() + 90
            executed, st = False, "?"
            while time.time() < deadline:
                k = next((k for k in c.get("/kits").json() if k["kit_id"] == kit_id), None)
                st = k["state"] if k else "?"
                rob = c.get("/robot/status").json()
                if a.auto_human and rob.get("state") == "waiting_human":
                    time.sleep(z)
                    c.post("/station/recovery/done")
                if st == "REVERIFYING":
                    executed = True
                    break
                if st in ("HUMAN_REVIEW", "RELEASED"):
                    break
                time.sleep(0.3)
            if executed:
                # perception would now re-inspect and see a complete kit
                time.sleep(z * 0.5)
                res = c.post("/events", json={"event": "KIT_INSPECTED", "source": "replay",
                                               "payload": {"detected": dict(REQ), "confidence": 0.96,
                                                           "reinspection": True, "perception_token": tok}}).json()
                print(f"    reinspected -> {res['kit_state']}")
            else:
                print(f"    recovery did not execute (state {st}); check logs/core.log and logs/robot.log")
        time.sleep(z * 0.5)
        c.post("/station/bob/received", json={})
        time.sleep(z * (2.5 if (missing and a.mode == "baseline") else 1.5))
        c.post("/station/bob/done", json={"payload": {"rework_seconds": 14} if (missing and a.mode == "baseline") else {}})
        time.sleep(z * 0.3)
        if missing and a.mode == "baseline" and i != 11:
            c.post("/station/charlie/reject", json={})
        else:
            c.post("/station/charlie/approve", json={})
        c.post("/events", json={"event": "QUEUE_MEASURED", "payload": {"zone": "assembly_queue", "count": min(4, i % 5)}, "source": "replay"})
    out = c.post("/runs/end").json()
    print("metrics:")
    for k, v in out["metrics"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print("core is not running: uvicorn services.core.main:app --port 8100", file=sys.stderr)
        sys.exit(1)
