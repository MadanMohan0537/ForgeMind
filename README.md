# FactoryFlow AI / ForgeMind - local process intelligence on DGX Spark

**See the error. Recover the product. Improve the process.**

FactoryFlow AI uses ForgeMind's event-sourced services to reconstruct dependencies across a three-stage miniature assembly line. It distinguishes where a backlog is visible from where its cause originated, requests a governed intervention, and verifies recovery. The demo runs locally on an NVIDIA DGX Spark and does not require a physical camera or robot.

The primary demo story is **Station A supplies an incomplete kit → Station B is blocked and accumulates backlog → Station C becomes dependency-idle → FactoryFlow attributes the root cause to Station A → an external human teleoperates an Isaac Sim arm to deliver the missing wheel → the line resumes**.

## What is implemented

- Phone/recorded-video perception with deterministic OpenCV zones, HSV counts, stability gating, and evidence files.
- NVIDIA Cosmos Reason2 8B as a second-opinion image/video model through local vLLM.
- A complete hold -> propose -> govern -> recover -> reinspect -> release/retry/human-review state machine.
- A strict governor between model proposals and the `HumanArm`, `MockArm`, or future `RealArm` adapter.
- Nemotron 3.5 Lightning (`nemotron-3.5-lightning:latest`, 32.9B total / about 3B active MoE) through local Ollama for actions, hypotheses, experiments, and verification.
- Code-computed throughput, defect, escape, recovery, cycle, queue, and rework metrics from a replayable SQLite event log.
- Live dashboard and four real Core-connected station pages; no separate fake-data UI.
- Code-verified analysis of 10,000 UCI AI4I 2020 rows, rendered in the Findings tab.
- Host analyst fallback. NemoClaw is installed separately, but ForgeMind does not claim an OpenShell containment demonstration yet.
- Deterministic Station A/B/C dependency analysis, including observed bottleneck, upstream root cause, transfer time, blocked time, dependency-driven idle time, and supporting event IDs.
- `IsaacHumanArm`, which creates a human-operated teleoperation session; the AI never receives raw joint-control authority.

## Architecture

```text
phone / MP4 -> perception :8150 -> KIT_INSPECTED + evidence -> core :8100
                      |                                      | state, metrics, WebSocket
                      +-> Cosmos :8001                        +-> dashboard + station phones
                                                             +-> deterministic governor
Nemotron 3.5 Lightning (Ollama :11434) -> proposals/analysis  +-> robot :8200 (HumanArm/MockArm/IsaacHumanArm)
```

The language model produces high-level structured proposals only. It never computes the displayed metrics and never sends coordinates or raw motor commands.

## Quickstart on the Spark

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

bash scripts/start_mediamtx.sh &
MODEL_RUNTIME=ollama ROBOT_ADAPTER=human REQUIRE_VLM=0 bash scripts/start_dgx.sh
```

Set `REQUIRE_VLM=1` only after `bash scripts/serve_cosmos.sh` reports ready. See the
[DGX build and physical validation runbook](docs/DGX_RUNBOOK.md) for accelerated vLLM,
camera acceptance, ten-minute stability monitoring, and comparable trial capture.

Open:

- `http://<spark>:8100/dashboard`
- `http://<spark>:8100/factoryflow` — three-station root-cause demo
- `http://<spark>:8100/operator` — external Isaac Sim operator console
- `http://<spark>:8150/calibrate`
- `http://<spark>:8100/station/alice`
- `http://<spark>:8100/station/bob`
- `http://<spark>:8100/station/charlie`
- `http://<spark>:8100/station/recovery`

For a camera-free rehearsal:

```bash
python scripts/synthetic_run.py --mode baseline --kits 8 --fast
python scripts/synthetic_run.py --mode recovery --kits 8 --fast
python scripts/synthetic_run.py --mode improved --kits 8 --fast
python -m pytest -q
```

For the FactoryFlow normal-then-failure story, start Core and Robot with
`ROBOT_ADAPTER=isaac_human`, open `/factoryflow`, and press **Run demo scenario**.
When an intervention is requested, the external operator uses `/operator` to accept,
teleoperate the arm inside Isaac Sim, and explicitly confirm completion.

## Demo and submission

- [Demo script](docs/DEMO_SCRIPT.md)
- [DGX build and physical validation runbook](docs/DGX_RUNBOOK.md)
- [Physical rig and rehearsal](docs/PHYSICAL_RIG.md)
- [Submission checklist](docs/SUBMISSION_CHECKLIST.md)
- [Spark measurements](docs/SPARK_STORY.md)
- [Core API and operations](docs/CORE.md)
- [P3 model/agent handoff](docs/P3_HANDOFF.md)
- [Nemotron 3.5 Lightning NVFP4 + DSpark wrapper](docs/LIGHTNING_DSPARK.md)
- [P4 VLM setup](docs/VSS_SETUP.md)

## Honest limitations

- Color counting assumes a calibrated, controlled view; Cosmos is a second opinion, not ground truth.
- Recovery supports adding one known missing part. Extra/uncertain parts require a human.
- `IsaacHumanArm` implements the safe session boundary and operator controls. The Isaac Sim scene, robot asset, and input-device bindings must still be launched/configured in Isaac Sim.
- The deterministic scenario proves event causality inside the simulation; it is not statistical proof about a real production line.
- Short runs are demonstrations, not statistically strong causal evidence.
- Wi-Fi-off behavior must be tested physically before it is claimed.
- The current host analyst fallback is not evidence of NemoClaw/OpenShell containment.

ForgeMind was built for the Spark track at NVIDIA Spark Hack Seattle, August 14-16, 2026.
