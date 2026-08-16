"""Contract and deployment tests for core.

Covers what core accepts from the outside — the sandboxed agent's analysis submissions,
containment denial reports, verification requests — plus the switches that only matter on
the Spark: the shared-token gate, runtime model reconfiguration, and SQLite's journal mode.

Everything the agent posts is untrusted input: it is produced outside core, often straight
from model output, and it is rendered on the dashboard during the demo.
"""
from __future__ import annotations

import asyncio
import sqlite3
from typing import Any

from services.core.tests.test_orchestrator import boot, client, start_kit

VALID_HYPOTHESES = {
    "run_id": "r1",
    "summary": "Batch preparation at Alice's station drops parts.",
    "hypotheses": [{
        "id": "H1", "title": "Batch prep drops wheels",
        "explanation": "Kits prepared three at a time are missing a wheel more often.",
        "confidence": 0.6, "supporting_event_ids": [1, 2], "contradicting_event_ids": [],
        "status": "active",
    }],
}
VALID_EXPERIMENT = {
    "change": "single-kit preparation (Alice completes one kit fully before starting the next)",
    "keep_unchanged": ["Bob's assembly procedure", "Charlie's QC criteria"],
    "reason": "Isolates batching as the cause of missing wheels.",
    "tests_hypothesis_id": "H1",
    "expected_observation": "Fewer incomplete kits detected at inspection.",
    "metric_to_watch": "incomplete_kits_detected",
}
VALID_VERIFICATION = {
    "comparison": {"rows": []},
    "verdicts": [{"hypothesis_id": "H1", "verdict": "supported",
                  "explanation": "Incomplete kits fell from 3 to 1.",
                  "before_value": 3.0, "after_value": 1.0}],
}


async def _open_run(c: Any, run_id: str = "r1") -> None:
    await c.post("/runs/start", json={"mode": "recovery", "run_id": run_id})


# --------------------------------------------------------------------------- #
# What the agent submits
# --------------------------------------------------------------------------- #
def test_valid_agent_submissions_are_stored(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await _open_run(c)
            for kind, data in (("hypotheses", VALID_HYPOTHESES), ("experiment", VALID_EXPERIMENT),
                               ("verification", VALID_VERIFICATION)):
                r = await c.post("/analysis/submit/r1", json={"kind": kind, "data": data})
                assert r.status_code == 200, (kind, r.text)

            stored = (await c.get("/analysis/r1")).json()
            assert stored["hypotheses"]["hypotheses"][0]["id"] == "H1"
            assert stored["experiment"]["tests_hypothesis_id"] == "H1"
            assert stored["verification"]["verdicts"][0]["verdict"] == "supported"
            evs = [e["event"] for e in (await c.get("/events", params={"run_id": "r1"})).json()]
            assert "HYPOTHESES_GENERATED" in evs and "EXPERIMENT_PROPOSED" in evs

    asyncio.run(scenario())


def test_open_data_submission_is_returned_for_dashboard(tmp_path):
    """P5 renders the code-verified AI4I result from the normal analysis API."""
    main = boot(tmp_path)
    result = {
        "dataset": "UCI AI4I 2020",
        "rows": 10000,
        "overall_failure_rate": 0.0339,
        "results": [{"id": "H3", "hypothesis": "High tool wear regime",
                     "lift": 3.06, "verdict": "supported"}],
    }

    async def scenario() -> None:
        async with client(main) as c:
            await _open_run(c, "ai4i_2020")
            response = await c.post("/analysis/submit/ai4i_2020", json={"kind": "open_data", "data": result})
            assert response.status_code == 200
            stored = (await c.get("/analysis/ai4i_2020")).json()
            assert stored["open_data"] == result

    asyncio.run(scenario())


def test_product_pages_use_live_core_routes(tmp_path):
    """P5 ships the real Core UI, not the disconnected local-storage prototype."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            dashboard = (await c.get("/dashboard")).text
            assert 'id="coreconn"' in dashboard
            assert 'href="/station/alice"' in dashboard
            assert 'id="openData"' in dashboard
            assert "forgemind-demo-events" not in dashboard

            for station in ("alice", "bob", "charlie", "recovery"):
                page = await c.get(f"/station/{station}")
                assert page.status_code == 200
                assert f"/station/${{who}}/${{action}}" in page.text

    asyncio.run(scenario())


def test_malformed_agent_submissions_are_rejected(tmp_path):
    """The dashboard renders this straight into the Findings tab; junk must not reach it."""
    main = boot(tmp_path)

    bad = [
        ("hypotheses", {"lol": "not a hypothesis set"}),                      # wrong shape entirely
        ("hypotheses", {"run_id": "r1", "summary": "s", "hypotheses": [
            {"id": "H1", "title": "t", "explanation": "e", "confidence": 5.0}]}),   # confidence out of range
        ("experiment", {"change": "x"}),                                      # missing required fields
        ("verification", {"verdicts": []}),                                   # empty verdicts
        ("verification", {"verdicts": [{"hypothesis_id": "H1", "verdict": "definitely"}]}),  # bad enum
        ("hypothesissss", VALID_HYPOTHESES),                                  # typo'd kind
    ]

    async def scenario() -> None:
        async with client(main) as c:
            await _open_run(c)
            for kind, data in bad:
                r = await c.post("/analysis/submit/r1", json={"kind": kind, "data": data})
                assert r.status_code == 422, f"{kind} {data} was accepted: {r.status_code}"

            stored = (await c.get("/analysis/r1")).json()
            assert stored["hypotheses"] is None and stored["experiment"] is None
            evs = [e["event"] for e in (await c.get("/events", params={"run_id": "r1"})).json()]
            assert "HYPOTHESES_GENERATED" not in evs, "a rejected submission must not announce itself"

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Containment evidence
# --------------------------------------------------------------------------- #
def test_denials_record_who_reported_them(tmp_path):
    """Core cannot witness a sandbox denial, so it must not claim to have.

    The Containment tab is bounty evidence. Stamping every POST as `source=openshell`
    made an unauthenticated claim look like an observation core had made itself.
    """
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await _open_run(c)
            r = await c.post("/policy/denied", json={"agent": "forgemind-agent",
                                                    "attempted": "POST /robot/add-part",
                                                    "detail": "blocked by openshell policy",
                                                    "reporter": "openshell"})
            assert r.status_code == 200 and r.json()["verified_by_core"] is False

            await c.post("/policy/denied", json={"attempted": "rm -rf /", "detail": "made up"})

            evs = [e for e in (await c.get("/events", params={"run_id": "r1"})).json()
                   if e["event"] == "POLICY_DENIED"]
            assert evs[0]["source"] == "report:openshell"
            assert evs[1]["source"] == "report:unverified", "an unnamed reporter must not read as openshell"
            for e in evs:
                assert e["payload"]["verified_by_core"] is False
                assert "reported_by_host" in e["payload"]
            assert (await c.get("/metrics/r1")).json()["policy_denials"] == 2

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Verification needs a real experiment
# --------------------------------------------------------------------------- #
def test_verify_refuses_without_an_experiment_plan(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            await _open_run(c, "before")
            await start_kit(c, {"red_body": 1, "black_wheel": 2, "blue_roof": 1})
            await c.post("/runs/end")
            await _open_run(c, "after")
            await start_kit(c, {"red_body": 1, "black_wheel": 2, "blue_roof": 1})
            await c.post("/runs/end")
            await c.post("/analysis/submit/before", json={"kind": "hypotheses", "data": VALID_HYPOTHESES})

            r = await c.post("/analysis/verify", json={"before": "before", "after": "after"})
            assert r.status_code == 409 and "experiment plan" in r.json()["detail"]

    asyncio.run(scenario())


def test_verify_marks_an_uncontrolled_comparison(tmp_path):
    """Opting out is allowed, but the verifier must be told the change was not recorded."""
    main = boot(tmp_path)

    async def scenario() -> None:
        seen: dict = {}

        def fake_verify(h, experiment, before, after):
            from shared.schemas import VerificationVerdict
            seen["experiment"] = experiment
            return VerificationVerdict(hypothesis_id=h["id"], verdict="inconclusive", explanation="x")

        main.llm.verify_hypothesis = fake_verify
        async with client(main) as c:
            await _open_run(c, "before")
            await start_kit(c, {"red_body": 1, "black_wheel": 2, "blue_roof": 1})
            await c.post("/runs/end")
            await c.post("/analysis/submit/before", json={"kind": "hypotheses", "data": VALID_HYPOTHESES})

            r = await c.post("/analysis/verify", json={"before": "before", "after": "before",
                                                       "allow_missing_experiment": True})
            assert r.status_code == 200
            assert seen["experiment"]["uncontrolled"] is True
            assert seen["experiment"]["change"] == "not recorded"

        # with a plan recorded, the real plan is what reaches the verifier
        async with client(main) as c:
            await c.post("/analysis/submit/before", json={"kind": "experiment", "data": VALID_EXPERIMENT})
            r = await c.post("/analysis/verify", json={"before": "before", "after": "before"})
            assert r.status_code == 200
            assert seen["experiment"]["tests_hypothesis_id"] == "H1"
            assert "uncontrolled" not in seen["experiment"]

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# The shared-token gate (only active when FORGE_TOKEN is set)
# --------------------------------------------------------------------------- #
def test_no_token_configured_means_no_gate(tmp_path):
    """The default must stay open, or the station phones stop working."""
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            assert (await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})).status_code == 200
            assert (await c.post("/station/alice/start")).status_code == 200
            assert (await c.get("/state")).json()["auth"] is False

    asyncio.run(scenario())


def test_token_gates_writes_but_never_reads(tmp_path):
    main = boot(tmp_path, token="s3cret")

    async def scenario() -> None:
        async with client(main, from_host="192.168.1.55") as c:      # a phone on the venue LAN
            # reads stay open: a judge opening the dashboard must not need the secret
            for path in ("/health", "/state", "/runs", "/kits", "/events", "/dashboard", "/station/alice"):
                assert (await c.get(path)).status_code == 200, path
            assert (await c.get("/state")).json()["auth"] is True

            # writes without the token are refused
            assert (await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})).status_code == 401
            assert (await c.post("/station/alice/start")).status_code == 401
            assert (await c.post("/policy/denied", json={"attempted": "x"})).status_code == 401

            # header or query parameter both work
            hdr = {"X-Forge-Token": "s3cret"}
            assert (await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"},
                                 headers=hdr)).status_code == 200
            assert (await c.post("/station/alice/start", headers=hdr)).status_code == 200
            assert (await c.post("/station/alice/sent", params={"token": "s3cret"})).status_code == 200
            assert (await c.post("/station/alice/start", headers={"X-Forge-Token": "wrong"})).status_code == 401

            assert len((await c.get("/kits")).json()) == 1

    asyncio.run(scenario())


def test_same_box_services_are_not_locked_out_by_the_token(tmp_path):
    """Perception, the robot and the agent post over loopback with no token.

    Regression test for a live failure: turning the gate on made core answer 401 to the
    robot service's RECOVERY_EXECUTED, so recovery stalled at RECOVERING and the run
    silently produced no verified recoveries.
    """
    main = boot(tmp_path, token="s3cret")

    async def scenario() -> None:
        async with client(main, from_host="127.0.0.1") as c:         # a service on the Spark
            assert (await c.post("/runs/start", json={"mode": "recovery", "run_id": "r1"})).status_code == 200
            kit_id = await start_kit(c, {"red_body": 1, "black_wheel": 1, "blue_roof": 1})

            from services.core.tests.test_orchestrator import until
            assert await until(lambda: bool(main._http.add_part_calls))
            r = await c.post("/events", json={"event": "RECOVERY_EXECUTED", "kit_id": kit_id, "source": "robot"})
            assert r.status_code == 200, "the robot service must not need the token over loopback"

            await c.post("/events", json={"event": "KIT_INSPECTED", "kit_id": kit_id, "source": "perception",
                                          "payload": {"detected": {"red_body": 1, "black_wheel": 2, "blue_roof": 1},
                                                      "confidence": 0.96, "reinspection": True}})
            assert (await c.get("/metrics/r1")).json()["verified_recoveries"] == 1

    asyncio.run(scenario())


def test_loopback_trust_can_be_switched_off(tmp_path):
    main = boot(tmp_path, token="s3cret", trust_loopback="0")

    async def scenario() -> None:
        async with client(main, from_host="127.0.0.1") as c:
            assert (await c.post("/runs/start", json={"mode": "recovery"})).status_code == 401
            assert (await c.post("/runs/start", json={"mode": "recovery"},
                                 headers={"X-Forge-Token": "s3cret"})).status_code == 200

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# Runtime reconfiguration and deployment settings
# --------------------------------------------------------------------------- #
def test_planner_switches_without_a_restart(tmp_path):
    main = boot(tmp_path)

    async def scenario() -> None:
        async with client(main) as c:
            assert (await c.get("/state")).json()["planner"] == "rule"
            r = await c.post("/admin/llm", json={"planner": "llm"})
            assert r.status_code == 200 and r.json()["planner"] == "llm"
            assert (await c.get("/state")).json()["planner"] == "llm"
            assert (await c.post("/admin/llm", json={"planner": "sideways"})).status_code == 422
            assert (await c.post("/admin/llm", json={"planner": "rule"})).json()["planner"] == "rule"

    asyncio.run(scenario())


def test_model_endpoint_switches_without_a_restart(tmp_path):
    """Bringing Lightning up mid-night must not require dropping the run in progress."""
    main = boot(tmp_path)
    before = main.llm.MODEL

    async def scenario() -> None:
        async with client(main) as c:
            r = await c.post("/admin/llm", json={"model": "lightning",
                                                 "base_url": "http://127.0.0.1:8002/v1",
                                                 "fast_model": "lightning"})
            assert r.status_code == 200
            assert main.llm.MODEL == "lightning" != before
            assert main.llm.BASE_URL == "http://127.0.0.1:8002/v1"
            assert (await c.get("/state")).json()["llm_model"] == "lightning"

    asyncio.run(scenario())
    main.llm.reconfigure(model=before, base_url="http://127.0.0.1:8000/v1", fast_model=before)


def test_sqlite_runs_in_wal_mode(tmp_path):
    """Three services and the agent poller hit this database at once during a run."""
    main = boot(tmp_path)
    path = str(tmp_path / "core.sqlite")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert main.store is not None
