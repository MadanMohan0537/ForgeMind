# ForgeMind P3 Handoff

Date: 2026-08-15  
Owner: P3 — Models + analyst agent

## Status

P3 is complete on the documented host-agent fallback path. Nemotron 3.5 Lightning is hosted on the DGX Spark, the structured action/hypothesis/experiment paths are live, the P2 merge is integrated, the recovery loop passed end to end, and the AI4I open-data result is generated.

The optional NemoClaw/OpenShell containment bounty is **not** claimed. NemoClaw v0.0.90 is installed, but its existing sandbox is an unrelated Qwen setup and was deliberately left untouched. The ForgeMind analyst currently runs on the host, exactly as the execution plan's fallback permits.

## Source-control integration

- Local branch: `p3-model-agent`
- Base: P2 merge on `main`, commit `6619d38`
- P3 code commits:
  - `f7c5deb` — harden Nemotron analyst runtime
  - `fa71159` — disambiguate computed missing counts
  - `e7ea621` — constrain evidence interpretation
- DGX checkout: `/home/acer01/ForgeMind-p3`
- DGX branch: `p3-integration-final`
- P4 checkout `/home/acer01/ForgeMind` was not modified.

There was no Git merge conflict with P2. The only semantic overlap was `services/core/llm.py`: P2 added runtime `reconfigure()`, and P3 preserved it while adding Ollama reasoning controls and output validation.

## P3 changes

- Added `LLM_THINK_MODE=ollama`, sending native `think=false` and `reasoning_effort=none`. Without this, Ollama could consume the token budget in reasoning and leave structured `message.content` empty.
- Enforced source grounding: invalid/duplicate event IDs are removed, unsupported hypotheses are dropped, and fewer than two distinct grounded hypotheses fail visibly.
- Enforced the experiment allowlist and required the plan to reference an actual generated hypothesis.
- Added prompt rules that preserve mandatory post-action reinspection, separate symptoms/containment/root causes, respect event order, and avoid unsupported station blame.
- Clarified computed counts so `detected black_wheel=1` plus `missing black_wheel=1` is correctly treated as one of two required wheels absent.
- Made agent HTTP reads fail on non-2xx responses.
- Made the watcher start at the newest event after restart, avoiding reprocessing every historical run; use `--run RUN_ID` for deliberate replay.
- Denial reports now include explicit reporter provenance and check the Core response.
- The denial demo now reports only actual exceptions or HTTP 401/403 blocks. An action that succeeds is a failing containment test and returns non-zero instead of being mislabeled `DENIED`.
- Added P3 model/agent contract tests.
- Completed `runs/open_data_ai4i.json` and `.md` with 10,000-row UCI AI4I statistics, four Nemotron hypotheses, and deterministic verdicts.

## Validation evidence

Local merged suite:

```text
61 passed in 34.49s
```

Real DGX recovery run `recovery_03`:

```text
12 kits started / 12 inspected / 12 correct
3 incomplete kits detected
3 recovery attempts / 3 verified recoveries
0 escapes / 0 rejects / 0 human reviews
recovery success rate: 1.0
duration: 20.8 seconds (synthetic --fast run; not production cycle time)
```

The watcher then generated three hypotheses with real event IDs and one allowlisted experiment. Hypothesis generation took 9.9 s and experiment generation took 5.0 s in the final replay.

AI4I open-data result:

```text
10,000 rows; overall machine-failure rate 3.39%
H3 high tool wear: supported, 3.06x lift
H1 and H2: not supported by deterministic code
H4: inconclusive because its predicate selected zero rows
```

The rejected and inconclusive hypotheses are intentional evidence that model proposals are tested by code rather than presented as facts.

## Live DGX runtime

Snapshot at handoff:

- Ollama 0.32.13: `127.0.0.1:11434`
- Model: `nemotron-3.5-lightning:latest`, 32.9B total / Q4_K_M / 25.3 GB loaded
- Context length: 8,192
- Ollama: flash attention on, keep-alive forever
- Core: port 8100
- Mock robot: port 8200
- Host analyst watcher: active
- Unified memory: 33 GiB used, 88 GiB available
- P1 perception service is not currently running.
- No Qwen model or Qwen process is used by ForgeMind.

Quick checks:

```bash
ssh 404-NameNA
curl -s http://127.0.0.1:8100/health
curl -s http://127.0.0.1:11434/api/ps
curl -s http://127.0.0.1:8200/robot/status
tail -f /home/acer01/ForgeMind-p3/logs/agent-p3.log
```

Manual analysis replay:

```bash
cd /home/acer01/ForgeMind-p3
PYTHONPATH=$PWD CORE_URL=http://127.0.0.1:8100 \
LLM_BASE_URL=http://127.0.0.1:11434/v1 \
LLM_MODEL=nemotron-3.5-lightning:latest \
LLM_FAST_MODEL=nemotron-3.5-lightning:latest \
LLM_THINK_MODE=ollama \
/home/acer01/.hermes/hermes-agent/venv/bin/python \
-m services.agent.agent_loop --run recovery_03
```

Synthetic recovery check:

```bash
cd /home/acer01/ForgeMind-p3
PYTHONPATH=$PWD /home/acer01/.hermes/hermes-agent/venv/bin/python \
scripts/synthetic_run.py --mode recovery --fast
```

## Dependencies and remaining team actions

1. **P1 / real camera:** Core currently logs `re-inspection request failed` because P1 perception is down. The synthetic runner supplies the reinspection event itself, so the synthetic test is valid. A physical demo needs P1's `/inspect_now` service reachable at the configured `PERCEPTION_URL`.
2. **P2/P5 / open-data display:** `POST /analysis/submit/ai4i_2020` accepts and stores `kind=open_data`, but `GET /analysis/{run_id}` only returns hypotheses, experiment, and verification, and the current dashboard has no open-data renderer. The JSON/Markdown artifacts are ready; P2 must expose the stored item or P5 must render the artifact for the 3:20 demo shot.
3. **P2 repository hygiene:** P2's merge tracks `runs/forgemind.sqlite-shm` and `runs/forgemind.sqlite-wal`. A running Core modifies them, so the DGX checkout appears dirty during normal operation. They should be untracked in a separate P2 cleanup, not changed in P3.
4. **Containment claim:** Do not say the current host watcher is sandboxed or show fabricated denial evidence. To claim the NemoClaw/OpenShell bounty, create a dedicated ForgeMind sandbox, apply `services/agent/openshell_policy.yaml`, run `--demo-denial`, and independently verify that all three attempts had no side effect.

## Handoff conclusion

P3 does not need additional code from P2 to operate. It needs P1 only for physical-camera reinspection and P2/P5 only to surface the already-generated open-data artifact in the UI. The model, agent loop, structured contracts, governed recovery proposal, and open-data analysis are ready.
