"""End-to-end tests for the core orchestrator (services/core/main.py).

The pure modules (governor, metrics, state machine) already have tests. This file covers
the part that actually decides what happens to a kit: event ingestion, the hold ->
propose -> govern -> actuate -> re-verify -> release loop, and the failure branches that
only appear when another service misbehaves.

The app is driven over ASGI, so routing, request models and status codes are exercised
too. Nothing here touches the network: the robot and perception services are replaced by
`FakeHttp`, and the rule planner is used so no model is needed.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import time
from typing import Any, Callable, Optional

import httpx
import pytest

REQ = {"red_body": 1, "black_wheel": 2, "blue_roof": 1}
MISSING_WHEEL = {"red_body": 1, "black_wheel": 1, "blue_roof": 1}


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeResp:
    """Just enough of httpx.Response for core's two outbound calls."""

    def __init__(self, status_code: int = 200, data: Optional[dict] = None):
        self.status_code = status_code
        self._data = data or {}
        self.text = str(self._data)

    def json(self) -> dict:
        return self._data


class FakeHttp:
    """Stands in for core's httpx client: the robot service and perception.

    Records what core tried to do so tests can assert that the robot was called exactly
    when the governor allowed it, and never otherwise.
    """

    def __init__(self) -> None:
        self.robot_state = "idle"
        self.add_part_calls: list[dict] = []
        self.inspect_now_calls = 0
        self.perception_down = False
        self.robot_rejects = False

    async def get(self, url: str, **_: Any) -> FakeResp:
        if url.endswith("/robot/status"):
            return FakeResp(200, {"state": self.robot_state, "adapter": "fake"})
        return FakeResp(404, {})

    async def post(self, url: str, json: Optional[dict] = None, **_: Any) -> FakeResp:
        if url.endswith("/robot/add-part"):
            if self.robot_rejects:
                return FakeResp(409, {"detail": "robot busy"})
            self.add_part_calls.append(json or {})
            return FakeResp(200, {"accepted": True})
        if url.endswith("/inspect_now"):
            self.inspect_now_calls += 1
            if self.perception_down:
                raise httpx.ConnectError("perception is down")
            return FakeResp(200, {})
        return FakeResp(200, {})


def boot(tmp_path, **env) -> Any:
    """Import a fresh core bound to a throwaway database.

    Core keeps its store and its tuning constants at module scope, so a reload is the
    honest way to get an isolated instance — and it is also exactly what a restart does,
    which is what `test_resume_*` needs.
    """
    os.environ["FORGE_DB"] = str(tmp_path / "core.sqlite")
    os.environ["PLANNER"] = env.pop("planner", "rule")
    os.environ["CORE_STALL_SECONDS"] = str(env.pop("stall_seconds", 3600))
    os.environ["CORE_WATCHDOG_INTERVAL"] = str(env.pop("watchdog_interval", 3600))
    os.environ["FORGE_TOKEN"] = env.pop("token", "")      # explicit: never inherit between tests
    os.environ["FORGE_TRUST_LOOPBACK"] = env.pop("trust_loopback", "1")
    import services.core.db as db
    import services.core.main as main

    importlib.reload(db)
    importlib.reload(main)
    main._http = FakeHttp()          # type: ignore[assignment]
    return main


def client(main: Any, from_host: str = "127.0.0.1") -> httpx.AsyncClient:
    """A client for the app. `from_host` fakes the caller's address.

    Anything other than loopback stands in for a phone or laptop on the venue network,
    which is what the shared-token gate is aimed at.
    """
    transport = httpx.ASGITransport(app=main.app, client=(from_host, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://core")


# Generous by default, and stretchable from the environment. These tests run on the Spark
# while it is also serving a 120B model, where a background task can be descheduled for a
# noticeable fraction of a second; a tight bound would fail there for no real reason.
TIMEOUT_SCALE = float(os.environ.get("FORGE_TEST_TIMEOUT_SCALE", "1"))


async def until(cond: Callable[[], bool], timeout: float = 10.0) -> bool:
    """Wait for a background orchestration task to reach a state."""
    deadline = time.time() + timeout * TIMEOUT_SCALE
    while time.time() < deadline:
        if cond():
            return True
        await asyncio.sleep(0.02)
    return False


async def kit_state(c: httpx.AsyncClient, kit_id: str, run_id: Optional[str] = None) -> Optional[str]:
    params = {"run_id": run_id} if run_id else {}
    for k in (await c.get("/kits", params=params)).json():
        if k["kit_id"] == kit_id:
            return k["state"]
    return None


async def events(c: httpx.AsyncClient, run_id: str) -> list[dict]:
    return (await c.get("/events", params={"run_id": run_id, "limit": 5000})).json()


async def start_kit(c: httpx.AsyncClient, detected: dict, confidence: float = 0.97) -> str:
    """Alice prepares and sends a kit; perception reports what it counted."""
    await c.post("/station/alice/start")
    await c.post("/station/alice/sent")
    r = await c.post("/events", json={"event": "KIT_INSPECTED", "source": "perception",
                                      "payload": {"detected": detected, "confidence": confidence}})
    return r.json()["kit_id"]


# --------------------------------------------------------------------------- #
# The loop the demo depends on
# --------------------------------------------------------------------------- #
def test_hold_recover_verify_release(tmp_path):
    """Incomplete kit -> held -> governed ADD_PART -> camera confirms -> released."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL)
            assert await until(lambda: bool(main._http.add_part_calls)), "governor never called the robot"

            req = main._http.add_part_calls[0]
            assert (req["part"], req["source_bin"], req["quantity"]) == ("black_wheel", "wheel_bin", 1)
            assert req["target_zone"] == "inspection_zone"

            # the robot service reports the routine finished
            await c.post("/events", json={"event": "RECOVERY_EXECUTED", "kit_id": kit_id, "source": "robot"})
            assert await kit_state(c, kit_id) == "REVERIFYING"
            assert main._http.inspect_now_calls == 1, "core must ask perception to re-inspect"

            # the camera now sees a complete kit
            await c.post("/events", json={"event": "KIT_INSPECTED", "kit_id": kit_id, "source": "perception",
                                          "payload": {"detected": REQ, "confidence": 0.96, "reinspection": True}})
            assert await kit_state(c, kit_id) == "RELEASED"

            seq = [e["event"] for e in await events(c, "r1") if e["kit_id"] == kit_id]
            assert seq == ["KIT_STARTED", "KIT_SENT", "KIT_INSPECTED", "KIT_HELD", "RECOVERY_PROPOSED",
                           "RECOVERY_APPROVED", "RECOVERY_EXECUTED", "KIT_INSPECTED", "RECOVERY_VERIFIED",
                           "KIT_RELEASED"]
            m = (await c.get("/metrics/r1")).json()
            assert m["recovery_attempts"] == 1 and m["verified_recoveries"] == 1
            assert m["escapes"] == 0

    asyncio.run(scenario())


def test_complete_kit_is_released_without_the_robot(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, REQ)
            assert await kit_state(c, kit_id) == "RELEASED"
            assert main._http.add_part_calls == []

    asyncio.run(scenario())


def test_extra_part_is_denied_and_goes_to_a_human(tmp_path):
    """Extra parts are outside the one supported routine: nothing may move."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, {"red_body": 1, "black_wheel": 2, "blue_roof": 2})
            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")
            assert main._http.add_part_calls == [], "the robot must never be called on a denied proposal"

            evs = [e for e in await events(c, "r1") if e["kit_id"] == kit_id]
            denied = [e for e in evs if e["event"] == "RECOVERY_DENIED"]
            # The planner stops this one before the governor: extra parts are outside the
            # supported routine, so it asks for a human rather than proposing a motion.
            assert denied, "the hold must be recorded, not just acted on"
            assert denied[0]["payload"]["action"] == "HOLD_FOR_HUMAN"
            assert "extra" in denied[0]["payload"]["rationale"], "a denial with no stated reason is unreadable"
            assert any(e["event"] == "HUMAN_REVIEW_REQUESTED" for e in evs)

            proposed = [e for e in evs if e["event"] == "RECOVERY_PROPOSED"][0]
            assert proposed["payload"]["world"]["extra"] == {"blue_roof": 1}

    asyncio.run(scenario())


def test_low_confidence_is_denied(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL, confidence=0.40)
            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")
            assert main._http.add_part_calls == []
            denied = [e for e in await events(c, "r1") if e["event"] == "RECOVERY_DENIED"]
            assert denied[0]["payload"]["checks"]["confidence"] is False

    asyncio.run(scenario())


def test_failed_recovery_retries_once_then_asks_for_a_human(tmp_path):
    """The camera, not the actuator, decides whether the fix worked."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL)

            for attempt in (1, 2):
                assert await until(lambda: len(main._http.add_part_calls) == attempt)
                await c.post("/events", json={"event": "RECOVERY_EXECUTED", "kit_id": kit_id, "source": "robot"})
                # still missing the wheel
                await c.post("/events", json={"event": "KIT_INSPECTED", "kit_id": kit_id, "source": "perception",
                                              "payload": {"detected": MISSING_WHEEL, "confidence": 0.97,
                                                          "reinspection": True}})

            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")
            assert len(main._http.add_part_calls) == 2, "must not keep retrying past the limit"
            evs = [e["event"] for e in await events(c, "r1") if e["kit_id"] == kit_id]
            assert evs.count("RECOVERY_FAILED") == 2
            assert evs[-1] == "HUMAN_REVIEW_REQUESTED"

    asyncio.run(scenario())


def test_human_resolution_releases_the_kit(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, {"red_body": 1, "black_wheel": 2, "blue_roof": 2})
            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")

            await c.post("/station/recovery/resolved")            # human fixed the kit
            assert main._http.inspect_now_calls >= 1
            await c.post("/events", json={"event": "KIT_INSPECTED", "kit_id": kit_id, "source": "perception",
                                          "payload": {"detected": REQ, "confidence": 0.95}})
            assert await kit_state(c, kit_id) == "RELEASED"

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Escapes: the dashboard flag and the metric must be the same number
# --------------------------------------------------------------------------- #
def test_baseline_escape_flag_matches_the_metric(tmp_path):
    """In baseline mode nothing is released, so every kit reaches Bob from ARRIVED.

    Only the kit the camera found defective is an escape. Flagging all of them (the old
    state-only rule) put a number on the event feed that the metrics tab contradicted.
    """
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "baseline", "run_id": "b1"})
            good = await start_kit(c, REQ)
            assert await kit_state(c, good) == "ARRIVED", "baseline mode must not hold or release"
            await c.post("/station/bob/received")
            await c.post("/station/bob/done")
            await c.post("/station/charlie/approve")

            bad = await start_kit(c, MISSING_WHEEL)
            assert main._http.add_part_calls == [], "baseline mode must not run recovery"
            await c.post("/station/bob/received")
            await c.post("/station/bob/done", json={"payload": {"rework_seconds": 14}})
            await c.post("/station/charlie/reject")

            evs = await events(c, "b1")
            flagged = {e["kit_id"] for e in evs if e["payload"].get("escape")}
            assert flagged == {bad}, f"expected only {bad} flagged, got {flagged}"

            m = (await c.get("/metrics/b1")).json()
            assert m["escapes"] == len(flagged) == 1
            assert m["incomplete_kits_detected"] == 1 and m["rejected_products"] == 1
            assert m["rework_seconds"] == 14.0

    asyncio.run(scenario())


def test_kit_taken_while_held_is_an_escape(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL)
            await c.post("/station/bob/received")                  # Bob grabs it anyway
            evs = await events(c, "r1")
            received = [e for e in evs if e["event"] == "KIT_RECEIVED"][0]
            assert received["payload"].get("escape") is True
            assert (await c.get("/metrics/r1")).json()["escapes"] == 1

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Failure branches in the other services
# --------------------------------------------------------------------------- #
def test_robot_error_is_recorded_and_escalated(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            main._http.robot_rejects = True
            kit_id = await start_kit(c, MISSING_WHEEL)
            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")
            evs = [e["event"] for e in await events(c, "r1") if e["kit_id"] == kit_id]
            assert "ROBOT_ERROR" in evs and "HUMAN_REVIEW_REQUESTED" in evs

    asyncio.run(scenario())


def test_failed_reinspection_request_is_recorded(tmp_path):
    """Perception being unreachable must not look like "the camera saw nothing wrong"."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL)
            assert await until(lambda: bool(main._http.add_part_calls))
            main._http.perception_down = True
            await c.post("/events", json={"event": "RECOVERY_EXECUTED", "kit_id": kit_id, "source": "robot"})

            evs = await events(c, "r1")
            assert any(e["payload"].get("reinspection_request_failed") for e in evs), \
                "a silent perception failure leaves the kit stuck with no explanation"

    asyncio.run(scenario())


def test_watchdog_escalates_a_stalled_kit(tmp_path):
    """A kit waiting on a service that never answers ends up with a human, not in limbo."""
    main = boot(tmp_path, stall_seconds=1.0, watchdog_interval=0.1)

    async def scenario() -> None:
        async with main.lifespan(main.app):
            async with client(main) as c:
                await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
                main._http.perception_down = True
                kit_id = await start_kit(c, MISSING_WHEEL)
                assert await until(lambda: bool(main._http.add_part_calls))
                await c.post("/events", json={"event": "RECOVERY_EXECUTED", "kit_id": kit_id, "source": "robot"})
                assert await kit_state(c, kit_id) == "REVERIFYING"   # perception will never answer

                assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW", timeout=20)
                stalled = [e for e in await events(c, "r1") if e["source"] == "watchdog"]
                assert stalled and stalled[0]["payload"]["stalled_state"] == "REVERIFYING"
                assert (await c.get("/metrics/r1")).json()["human_reviews"] == 1

    asyncio.run(scenario())


def test_orchestration_crash_becomes_a_human_review(tmp_path):
    """A bug in the recovery path must surface as an event, not a dropped background task."""
    main = boot(tmp_path)

    async def scenario() -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("planner exploded")

        main.governor.rule_planner = boom          # type: ignore[assignment]
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            kit_id = await start_kit(c, MISSING_WHEEL)
            assert await until(lambda: main.store.kit(kit_id, "r1").state.value == "HUMAN_REVIEW")
            reasons = [e["payload"].get("reason", "") for e in await events(c, "r1")
                       if e["event"] == "HUMAN_REVIEW_REQUESTED"]
            assert any("core error" in r for r in reasons)

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Runs: isolation, restart, resume
# --------------------------------------------------------------------------- #
def test_kits_are_isolated_between_runs(tmp_path):
    """Kit ids restart every run; an earlier run's kits must survive the next one."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "baseline", "run_id": "b1"})
            first = await start_kit(c, MISSING_WHEEL)
            await c.post("/runs/end")

            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            second = await start_kit(c, REQ)
            assert first == second == "kit_01", "both runs number their first kit kit_01"

            b1 = (await c.get("/kits", params={"run_id": "b1"})).json()
            assert len(b1) == 1 and b1[0]["missing"] == {"black_wheel": 1}, "run b1's kit was overwritten"
            r1 = (await c.get("/kits", params={"run_id": "r1"})).json()
            assert len(r1) == 1 and r1[0]["state"] == "RELEASED"
            assert (await c.get("/metrics/b1")).json()["incomplete_kits_detected"] == 1

    asyncio.run(scenario())


def test_core_restart_resumes_the_open_run(tmp_path):
    """A restart mid-run must keep writing to that run, not open a "scratch" one."""
    main = boot(tmp_path)

    async def before_restart() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "recovery_01"})
            await start_kit(c, REQ)
            await start_kit(c, REQ)

    asyncio.run(before_restart())

    restarted = boot(tmp_path)          # same database, fresh process state

    async def after_restart() -> None:
        async with restarted.lifespan(restarted.app):
            async with client(restarted) as c:
                assert (await c.get("/runs/current")).json() == {"run_id": "recovery_01", "mode": "recovery"}
                kit_id = await start_kit(c, REQ)
                assert kit_id == "kit_03", "kit numbering must continue, not restart"
                runs = {r["run_id"] for r in (await c.get("/runs")).json()}
                assert "scratch" not in runs
                assert (await c.get("/metrics/recovery_01")).json()["kits_started"] == 3

    asyncio.run(after_restart())


def test_resume_endpoint_reopens_an_ended_run(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            await start_kit(c, REQ)
            await c.post("/runs/end")
            assert (await c.get("/runs/current")).json()["run_id"] is None

            r = await c.post("/runs/resume/r1")
            assert r.status_code == 200 and r.json()["kits"] == 1
            assert (await c.get("/runs/current")).json()["run_id"] == "r1"
            assert await start_kit(c, REQ) == "kit_02"
            assert (await c.post("/runs/resume/nope")).status_code == 404

    asyncio.run(scenario())


def test_telemetry_dedup_resets_between_runs(tmp_path):
    """The first queue reading of a new run must be recorded even if the number repeated."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            for run_id in ("r1", "r2"):
                await c.post("/runs/start", json={"mode": "recovery", "run_id": run_id})
                await c.post("/events", json={"event": "QUEUE_MEASURED", "source": "perception",
                                              "payload": {"zone": "assembly_queue", "count": 3}})
                await c.post("/events", json={"event": "ZONE_STATUS", "source": "perception",
                                              "payload": {"workspace_clear": True, "fps": 12}})
                await c.post("/runs/end")
            for run_id in ("r1", "r2"):
                m = (await c.get(f"/metrics/{run_id}")).json()
                assert m["max_queue"] == 3, f"{run_id} lost its queue baseline"

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Read APIs the dashboard depends on
# --------------------------------------------------------------------------- #
def test_events_tail_returns_the_newest_window(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            for _ in range(12):
                await c.post("/station/alice/start")
            all_ids = [e["id"] for e in await events(c, "r1")]

            tail = (await c.get("/events", params={"run_id": "r1", "limit": 5, "tail": True})).json()
            assert [e["id"] for e in tail] == all_ids[-5:], "a mid-run dashboard must see the latest events"

            head = (await c.get("/events", params={"run_id": "r1", "limit": 5})).json()
            assert [e["id"] for e in head] == all_ids[:5], "since_id polling still needs oldest-first"

            since = (await c.get("/events", params={"run_id": "r1", "since_id": all_ids[4]})).json()
            assert [e["id"] for e in since] == all_ids[5:]

    asyncio.run(scenario())


def test_metrics_compare_is_not_shadowed_by_the_run_id_route(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            for run_id, mode in (("b1", "baseline"), ("r1", "recovery")):
                await c.post("/runs/start", json={"mode": mode, "run_id": run_id})
                await start_kit(c, MISSING_WHEEL if mode == "baseline" else REQ)
                await c.post("/runs/end")

            for path in ("/metrics/compare", "/metrics/compare/"):
                r = await c.get(path, params={"before": "b1", "after": "r1"})
                assert r.status_code == 200, path
                body = r.json()
                assert body["before_run"] == "b1" and body["after_run"] == "r1", \
                    f"{path} fell through to /metrics/{{run_id}} and returned an empty run"
                assert any(row["metric"] == "escapes" for row in body["rows"])

    asyncio.run(scenario())


def test_station_actions_reject_unknown_buttons(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            assert (await c.post("/station/alice/nope")).status_code == 404
            assert (await c.post("/station/charlie/approve")).status_code == 409  # nothing assembled yet

    asyncio.run(scenario())


def test_analysis_returns_503_without_a_model(tmp_path, monkeypatch):
    """Core must stay useful when the LLM is absent; it says so instead of a 500."""
    main = boot(tmp_path)
    monkeypatch.setattr(main, "llm", None)
    monkeypatch.setattr(main, "LLM_IMPORT_ERROR", "no openai package")

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            await start_kit(c, REQ)
            assert (await c.post("/analysis/hypotheses/r1")).status_code == 503
            assert (await c.get("/health")).json()["llm"]["ok"] is False
            # the physical loop and the numbers still work
            assert (await c.get("/metrics/r1")).json()["kits_started"] == 1

    asyncio.run(scenario())


def test_policy_denials_are_counted(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})
            for attempt in ("write /etc/hosts", "curl example.com", "POST /robot/add-part"):
                r = await c.post("/policy/denied", json={"attempted": attempt, "detail": "blocked by policy"})
                assert r.status_code == 200
            assert (await c.get("/metrics/r1")).json()["policy_denials"] == 3

    asyncio.run(scenario())


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
