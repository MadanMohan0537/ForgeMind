# ForgeMind — a local AI process scientist on DGX Spark

**See the error. Recover the product. Improve the process.**

ForgeMind watches a small assembly line through a phone camera, counts every kit, holds incomplete kits, directs a
governed recovery action, visually verifies the fix, and then studies the run: it proposes competing hypotheses,
recommends one controlled experiment, and measures whether the process actually improved. Everything — the 120B
reasoner, the vision-language model, the video buffer, the event log — runs on one NVIDIA DGX Spark (Acer Veriton GN100).

Track: **Spark** (See + Do inside). Built at NVIDIA Spark Hack Seattle, Aug 14–16 2026.

## What is real in this build
- Live perception from a phone camera (RTSP) → deterministic OpenCV counting → stability-gated inspection events with evidence clips.
- Second-opinion verification by an NVIDIA VLM (Cosmos Reason 2 via VSS or vLLM).
- Multi-step recovery loop with branching: hold → Nemotron proposes → deterministic governor validates (9 checks) → actuator → camera re-verifies → release / retry / human review.
- The actuator is a **pluggable adapter**: `HumanArm` (station screen instruction, hackathon) / `MockArm` / `RealArm` (stub). Same command path either way; nothing is trusted until the camera confirms it.
- Metrics computed only by code (throughput, defect rate, escapes, recovery success, cycle time, idle, rework, intervention reduction).
- Core survives its own failures: a mid-run restart re-adopts the open run, a kit waiting on a service that never answers is escalated to a human by a watchdog rather than sitting in limbo, and the whole physical loop runs with the model absent.
- Nemotron 3 Super 120B-A12B (vLLM, local) as analyst / planner / verifier with schema-validated JSON and code-checked citations.
- Always-on analyst agent runnable inside NemoClaw / OpenShell with a deny-by-default policy; denials are logged to the dashboard.
- Open data: the same analyst on UCI AI4I 2020 (predictive maintenance) — hypotheses as predicates, verdicts by code.

## Architecture
```
phone (Larix/RTSP) → mediamtx :8554 ─┬─→ VSS blueprint (Cosmos Reason 2 VLM, alerts) ──┐
                                     └─→ perception :8150 (OpenCV zones, HSV counts, ── KIT_INSPECTED ──→ core :8100
                                              stability gate, evidence, VLM verify)                    (SQLite events, kit state machine,
station phones :8100/station/{alice,bob,charlie,recovery} ── taps ─────────────────────────────────────→  governor, metrics, WebSocket)
                                                                                                             │            │
                                          Nemotron 3 Super (vLLM :8000) ←── planner/analyst/verifier ────────┘            │ ADD_PART (governor only)
                                          [optional Lightning :8002 for the fast loop]                                    ▼
                                          agent (NemoClaw/OpenShell sandbox) ── read events/metrics, submit analysis    robot :8200 (HumanArm | MockArm | RealArm)
```

## Quickstart (on the Spark)
```bash
pip install -r requirements.txt
bash scripts/serve_super.sh &            # Nemotron 3 Super on :8000  (edit MODEL path)
bash scripts/start_mediamtx.sh &         # RTSP in :8554; phone publishes rtsp://<spark>:8554/line
bash scripts/start_all.sh                # core :8100, robot :8200 (HumanArm), perception :8150
# open http://<spark>:8100/dashboard, http://<spark>:8150/calibrate, phones on /station/alice|bob|charlie, laptop on /station/recovery
python scripts/synthetic_run.py --mode recovery --auto-human   # no camera? drive the whole loop synthetically
PYTHONPATH=. python -m pytest -q                              # 42 tests: orchestrator, governor, metrics, state machine, store
python scripts/open_data_ai4i.py                              # open-data analysis (Nemotron + code verdicts)
```
Docs: `docs/PLAN.md` (who does what, hour by hour), `docs/CORE.md` (how core behaves and how to debug it), `docs/DEMO_SCRIPT.md`, `docs/BOUNTIES.md`, `docs/SPARK_STORY.md`, `services/agent/README.md`.

## How this maps to the judging rubric
- **Technical execution:** streaming input, VLM-verified detections, multi-step agent with hold/retry/human-review branches, deterministic governor, replayable event log, tests.
- **NVIDIA ecosystem & Spark story:** Nemotron 3 Super on vLLM (local), Cosmos Reason 2 via VSS blueprint, NemoClaw + OpenShell; one 128 GB pool holds reasoner + VLM + video buffer + full run history; works with Wi-Fi off (see `docs/SPARK_STORY.md`).
- **Value:** station screens a worker can use tomorrow; the output is a tested process change, not just an alert.
- **Innovation:** the system says what to test next and measures whether it worked; the actuator gets used less over time.

## Honest limitations
Single short runs are weak evidence and the verifier says so. Counting is color-based in a constrained scene. Recovery is one supported part per kit; extra/incorrect parts go to a human. The LLM never computes numbers and never touches the actuator. No physical arm on site — `HumanArm` is the actuator; the arm adapter is a stub.

## Consciously not used
cuDF/RAPIDS (200 events don't need it), Isaac Sim (no arm), speech models (workers use screens), Content Safety NIM (no free-text user input). Depth over breadth.
