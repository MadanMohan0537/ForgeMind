"""ForgeMind analyst agent — the always-on, sandboxed part.

What it may do:  read events/metrics from core, call the model, submit hypotheses/experiments/verdicts to core.
What it may NOT do (enforced by OpenShell policy, not by this code): call the robot service, reach the internet,
write outside /workspace/out. `--demo-denial` deliberately tries those so the denials show up on the dashboard.

Run (inside sandbox or plain):
  python -m services.agent.agent_loop --watch            # analyze every run when it ends
  python -m services.agent.agent_loop --run baseline_01  # analyze one run now
  python -m services.agent.agent_loop --demo-denial      # containment demo
Env: CORE_URL (http://host.docker.internal:8100 inside a sandbox), LLM_BASE_URL/LLM_MODEL (or NemoClaw inference URL),
     ROBOT_URL (should be UNREACHABLE from the sandbox), OUT_DIR (/workspace/out)
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx

from shared.schemas import Event, HypothesisSet, RunMetrics
from services.core import llm

CORE_URL = os.environ.get("CORE_URL", "http://127.0.0.1:8100")
ROBOT_URL = os.environ.get("ROBOT_URL", "http://127.0.0.1:8200")
OUT_DIR = Path(os.environ.get("OUT_DIR", "runs/agent_out"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
http = httpx.Client(timeout=30.0)


# ---- tools the agent is allowed to use ------------------------------------------
def get_events(run_id: str) -> list[Event]:
    response = http.get(f"{CORE_URL}/events", params={"run_id": run_id})
    response.raise_for_status()
    return [Event.model_validate(e) for e in response.json()]


def get_metrics(run_id: str) -> RunMetrics:
    response = http.get(f"{CORE_URL}/metrics/{run_id}")
    response.raise_for_status()
    return RunMetrics.model_validate(response.json())


def submit(run_id: str, kind: str, data: dict) -> None:
    http.post(f"{CORE_URL}/analysis/submit/{run_id}", json={"kind": kind, "data": data}).raise_for_status()
    (OUT_DIR / f"{run_id}_{kind}.json").write_text(json.dumps(data, indent=2))


def report_denial(attempted: str, detail: str) -> None:
    try:
        http.post(f"{CORE_URL}/policy/denied", json={
            "agent": "forgemind-analyst", "attempted": attempted,
            "detail": detail, "reporter": "openshell",
        }).raise_for_status()
    except Exception as ex:  # noqa: BLE001
        print(f"[agent] could not report denial: {ex}")


# ---- the job -----------------------------------------------------------------------
def analyze(run_id: str) -> None:
    evs = get_events(run_id)
    if not evs:
        print(f"[agent] no events for {run_id}")
        return
    m = get_metrics(run_id)
    print(f"[agent] {run_id}: {len(evs)} events, {m.incomplete_kits_detected} incomplete kits, {m.escapes} escapes")
    hs = llm.generate_hypotheses(run_id, evs, m, {e.id for e in evs if e.id})
    submit(run_id, "hypotheses", hs.model_dump())
    plan = llm.plan_experiment(hs, m)
    submit(run_id, "experiment", plan.model_dump())
    print(f"[agent] submitted {len(hs.hypotheses)} hypotheses + experiment '{plan.change}'")


def watch(poll_seconds: float = 5.0) -> None:
    seen: set[str] = set()
    last_id: int | None = None
    while True:
        try:
            if last_id is None:
                latest = http.get(f"{CORE_URL}/events", params={"limit": 1, "tail": True})
                latest.raise_for_status()
                current = latest.json()
                last_id = current[-1]["id"] if current else 0
                print(f"[agent] watching for finished runs after event #{last_id}")
            response = http.get(f"{CORE_URL}/events", params={"since_id": last_id, "limit": 500})
            response.raise_for_status()
            evs = response.json()
            for e in evs:
                last_id = max(last_id, e["id"])
                if e["event"] == "RUN_ENDED" and e["run_id"] not in seen:
                    seen.add(e["run_id"])
                    analyze(e["run_id"])
        except Exception as ex:  # noqa: BLE001
            print(f"[agent] poll error: {ex}")
        time.sleep(poll_seconds)


def demo_denial() -> None:
    """Try the three things the policy must block. Inside OpenShell these fail; we log the failure as evidence."""
    attempts = [
        ("POST robot add-part (bypass governor)", lambda: http.post(f"{ROBOT_URL}/robot/add-part", json={
            "kit_id": "kit_99", "part": "black_wheel", "quantity": 1, "source_bin": "wheel_bin", "target_zone": "inspection_zone"})),
        ("GET https://example.com (internet egress)", lambda: http.get("https://example.com", timeout=5)),
        ("write outside workspace", lambda: Path("/etc/forgemind_should_fail").write_text("x")),
    ]
    escaped: list[str] = []
    for name, fn in attempts:
        try:
            r = fn()
            status = getattr(r, "status_code", None)
            if status in (401, 403):
                detail = f"blocked: HTTP {status}"
                print(f"[agent] {name}: {detail}")
                report_denial(name, detail)
                continue
            detail = f"UNEXPECTEDLY SUCCEEDED: {status if status is not None else r}"
            escaped.append(name)
            print(f"[agent] {name}: {detail}  <-- policy is NOT containing this")
        except Exception as ex:  # noqa: BLE001
            detail = f"blocked: {type(ex).__name__}: {str(ex)[:120]}"
            print(f"[agent] {name}: {detail}")
            report_denial(name, detail)
    if escaped:
        raise RuntimeError(f"containment demo failed; {len(escaped)} attempt(s) escaped: {', '.join(escaped)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--demo-denial", action="store_true")
    a = ap.parse_args()
    if a.demo_denial:
        demo_denial()
    if a.run:
        analyze(a.run)
    if a.watch:
        watch()
    if not (a.run or a.watch or a.demo_denial):
        ap.print_help()
