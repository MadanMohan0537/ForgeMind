# ForgeMind

Local AI "process scientist" for a miniature assembly line. Pure Python (3.10+), event-sourced
over SQLite. Four FastAPI/uvicorn services plus an agent CLI and offline scripts. See `README.md`
and `docs/` for architecture and demo details.

## Cursor Cloud specific instructions

The update script creates `.venv` and installs `requirements.txt`. Activate it and set
`PYTHONPATH` before running anything, because all imports are absolute from the repo root:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD"
```

### Test / lint

- Tests: `python -m pytest -q` (runs `services/core/tests` per `pytest.ini`). There are additional
  suites at `services/agent/tests` and `services/perception/tests` not covered by the default
  `testpaths`; run them explicitly with `python -m pytest services/agent/tests services/perception/tests -q`.
- There is no linter/formatter configured in the repo.
- Tests are pure unit/contract tests: no running services, GPU, camera, or LLM required.

### Running the product (no GPU / camera / LLM needed)

The product degrades gracefully. For a full end-to-end run without hardware, set
`PLANNER=rule` (deterministic planner, no LLM) and `ROBOT_ADAPTER=mock` (auto-closes the recovery
loop with no human tap):

```bash
PLANNER=rule ROBOT_ADAPTER=mock bash scripts/start_all.sh   # core:8100, robot:8200, perception:8150
python scripts/synthetic_run.py --mode recovery --kits 8 --fast   # camera-free E2E driver
```

Then open `http://127.0.0.1:8100/dashboard`.

Non-obvious caveats:

- `scripts/start_all.sh` forces `SOURCE` to default to an RTSP URL (`${SOURCE:-...}` treats an empty
  string as unset), so perception starts with no reachable camera and reports `"ok":false` at
  `/health`. This is expected and fine — perception is optional. The **synthetic driver posts
  `KIT_ARRIVED`/`KIT_INSPECTED` events directly to core**, so the full
  hold → propose → govern → recover → reinspect → release loop works without perception, a camera,
  or the RTSP server.
- With no LLM endpoint reachable, `/health` shows `"llm":{"ok":false}` and core auto-falls back to
  the deterministic rule planner; `/analysis/*` endpoints return 503. This is expected without a
  local vLLM/Ollama server.
- GPU model services (vLLM Nemotron, Cosmos VLM), MediaMTX/RTSP, and the `agent` CLI are all
  optional and target the DGX Spark hardware; they are not needed to exercise or test core logic.
- Runtime artifacts (SQLite event log, evidence) are written under `runs/` and logs under `logs/`
  (both gitignored).
