# ForgeMind - local AI process scientist on DGX Spark

**See the error. Recover the product. Improve the process.**

ForgeMind watches a miniature assembly line, counts kit components, holds incomplete kits, directs a governed recovery, visually verifies the correction, and studies the event history to propose a controlled process improvement. The deployed model and data services run locally on an NVIDIA GB10 Grace Blackwell system.

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

## Architecture

```text
phone / MP4 -> perception :8150 -> KIT_INSPECTED + evidence -> core :8100
                      |                                      | state, metrics, WebSocket
                      +-> Cosmos :8001                        +-> dashboard + station phones
                                                             +-> deterministic governor
Nemotron 3.5 Lightning (Ollama :11434) -> proposals/analysis  +-> robot :8200 (HumanArm/MockArm)
```

The language model produces high-level structured proposals only. It never computes the displayed metrics and never sends coordinates or raw motor commands.

## Quickstart on the Spark

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

bash scripts/serve_cosmos.sh
bash scripts/start_mediamtx.sh &

SOURCE=rtsp://127.0.0.1:8554/line \
LLM_BASE_URL=http://127.0.0.1:11434/v1 \
LLM_MODEL=nemotron-3.5-lightning:latest \
LLM_FAST_MODEL=nemotron-3.5-lightning:latest \
LLM_THINK_MODE=ollama \
VLM_URL=http://127.0.0.1:8001/v1 \
VLM_MODEL=cosmos \
bash scripts/start_all.sh
```

Open:

- `http://<spark>:8100/dashboard`
- `http://<spark>:8150/calibrate`
- `http://<spark>:8100/station/alice`
- `http://<spark>:8100/station/bob`
- `http://<spark>:8100/station/charlie`
- `http://<spark>:8100/station/recovery`

For a camera-free rehearsal (event injection, no perception):

```bash
python scripts/synthetic_run.py --mode baseline --kits 8 --fast
python scripts/synthetic_run.py --mode recovery --kits 8 --fast
python scripts/synthetic_run.py --mode improved --kits 8 --fast
python -m pytest -q
```

For a camera-free rehearsal **with perception** (replay a generated line video):

```bash
python scripts/generate_demo_video.py          # writes runs/demo_line.mp4
SOURCE=runs/demo_line.mp4 REPLAY_LOOP=1 \
PLANNER=rule ROBOT_ADAPTER=mock \
bash scripts/start_all.sh
```

The demo MP4 shows complete kits and missing-wheel kits inside the default inspection zone so OpenCV counting works without a phone or RTSP stream. Regenerate anytime with `python scripts/generate_demo_video.py`.

## Demo and submission

- [Demo script](docs/DEMO_SCRIPT.md)
- [Physical rig and rehearsal](docs/PHYSICAL_RIG.md)
- [Submission checklist](docs/SUBMISSION_CHECKLIST.md)
- [Spark measurements](docs/SPARK_STORY.md)
- [Core API and operations](docs/CORE.md)
- [P3 model/agent handoff](docs/P3_HANDOFF.md)
- [P4 VLM setup](docs/VSS_SETUP.md)

## Honest limitations

- Color counting assumes a calibrated, controlled view; Cosmos is a second opinion, not ground truth.
- Recovery supports adding one known missing part. Extra/uncertain parts require a human.
- The hackathon actuator is HumanArm or MockArm; the physical-arm adapter remains a stub.
- Short runs are demonstrations, not statistically strong causal evidence.
- Wi-Fi-off behavior must be tested physically before it is claimed.
- The current host analyst fallback is not evidence of NemoClaw/OpenShell containment.

ForgeMind was built for the Spark track at NVIDIA Spark Hack Seattle, August 14-16, 2026.
