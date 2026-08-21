# DGX build and physical validation runbook

Use the safe default unless the accelerated vLLM path has already been measured on this machine.

```bash
cd ~/ForgeMind
source .venv/bin/activate
export PYTHONPATH="$PWD"
python scripts/dgx_preflight.py --llm ollama
MODEL_RUNTIME=ollama ROBOT_ADAPTER=human REQUIRE_VLM=0 bash scripts/start_dgx.sh
```

To require the already-installed Cosmos endpoint, start `scripts/serve_cosmos.sh` first and set
`REQUIRE_VLM=1`. Startup then fails if Cosmos is unavailable. For a camera-free rehearsal use
`MODEL_RUNTIME=none ROBOT_ADAPTER=mock SOURCE=0`.

## Camera validation

Open `/calibrate`, set the three zones, and tune the HSV ranges. Then run the guided acceptance:

```bash
python scripts/camera_acceptance.py --guided
python scripts/camera_acceptance.py --duration 600
```

Both commands write machine-readable results under `runs/`. Do not claim the camera is stable unless
the ten-minute command exits successfully.

## Comparable physical trials

Keep lighting, camera, bins, kit design, operator order, kit count, and pacing constant. In three
terminals, run these around the physical operation:

```bash
python scripts/capture_trial.py baseline --notes "8 kits; recovery disabled"
python scripts/capture_trial.py recovery --notes "8 kits; governed HumanArm recovery"
python scripts/capture_trial.py improved --notes "8 kits; single-kit preparation"
```

Each command saves events, metrics, copied evidence, hashes, and an honest-claims manifest beneath
`runs/trials/<run-id>/`. HumanArm means governed human execution. Do not use `ROBOT_ADAPTER=real`
until a make/model-specific SDK adapter and emergency-stop procedure have been implemented and tested.
