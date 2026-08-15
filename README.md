# ForgeMind

ForgeMind is a local AI process scientist for a miniature production line. It observes kits, measures delays and defects, proposes governed recovery actions, verifies the result, and compares process experiments.

The hackathon build runs locally on an NVIDIA GB10 Grace Blackwell system and uses the **NVIDIA Nemotron Lightning 30B** model for fast reasoning. The language model proposes high-level actions only; deterministic policy checks remain between every proposal and any physical recovery action.

## Product interface (P5)

The P5 interface is dependency-free and can run before the Core service is ready:

```bash
python -m http.server 8080 -d dashboard
```

Open `http://127.0.0.1:8080`. The interface includes:

- `/` — camera-facing operations dashboard
- `/station/alice/` — kit preparation and inspection handoff
- `/station/bob/` — assembly queue controls
- `/station/charlie/` — quality approval/rejection controls
- `/station/recovery/` — governed recovery and reinspection controls

By default, actions are stored in the browser so the full product flow can be rehearsed with synthetic data. To connect P2's Core service, open a station page with `?api=http://127.0.0.1:8000`; actions will be posted to `<api>/api/station/actions`. The UI visibly reports whether each action was accepted by Core or saved only in demo mode.

## Demo safety and honesty

- Never describe a proposed action as executed until the governor approves it and visual reinspection succeeds.
- Use measured dashboard values in the video; do not replace `TBD` fields with estimates.
- State how errors were induced during the three comparison runs.
- Automatic removal of extra/incorrect parts is out of scope; request human review.

See [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md), [`docs/PHYSICAL_RIG.md`](docs/PHYSICAL_RIG.md), and [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md).
