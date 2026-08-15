# Core (Part 2) — owner's note

Everything in `services/core`. Core is the only service that decides what happens to a kit,
the only one that calls the robot service, and the only place metrics come from.

Read this before asking core to change. If something in your service looks wrong, check
here first — most "perception is miscounting" reports are core resolving the event to the
wrong kit, which is my problem, not yours.

## What core promises the rest of you

1. **Every event you POST is stored and answered.** The reply tells you which kit it hit
   and what state that kit is now in: `{"ok": true, "event_id": 41, "kit_id": "kit_03",
   "kit_state": "HELD"}`. If a kit ever changes state with no event explaining why, that is
   a bug — tell me, don't work around it.
2. **Nothing stalls silently.** A kit waiting on the planner, the robot or the camera for
   more than `CORE_STALL_SECONDS` (180) gets a `HUMAN_REVIEW_REQUESTED` from the watchdog
   naming the state it was stuck in. A crash inside core's own recovery path does the same
   thing instead of dropping the kit.
3. **Only the governor moves the actuator.** `POST /robot/add-part` is called in exactly one
   place, after `governor.validate()` passes. A proposal that fails any check produces
   `RECOVERY_DENIED` plus `HUMAN_REVIEW_REQUESTED`, and the robot is not called at all.
4. **The LLM is never load-bearing.** With `PLANNER=rule`, or with the model down, or with
   the OpenAI SDK not even installed, the whole physical loop still runs. Only `/analysis/*`
   needs a model, and it answers 503 rather than 500 when there isn't one.
5. **Numbers come from `metrics.py` and nowhere else**, computed from the event log. Re-run a
   metric any time; it will give the same answer from the same events.

## Endpoints you'll use

| Who | Call | Notes |
|---|---|---|
| perception | `POST /events` | `KIT_ARRIVED`, `KIT_INSPECTED`, `QUEUE_MEASURED`, `ZONE_STATUS`, `VLM_VERIFICATION`. Send `perception_token` in the payload and core will keep mapping it to the same kit. |
| robot | `POST /events` | `RECOVERY_EXECUTED`, `ROBOT_ERROR`. Core asks perception to re-inspect on the first. |
| stations | `POST /station/{alice,bob,charlie,recovery}/{action}` | Unknown action → 404. Nothing in the right state → 409. |
| agent | `GET /events?run_id=&since_id=&limit=` | Poll with `since_id`; leave `tail` off or you'll skip the middle of the log. |
| agent | `POST /analysis/submit/{run_id}` | Submit analysis you produced yourself; needs no model on core's side. |
| dashboard | `GET /state`, `WS /ws` | The socket sends a snapshot (kits + last 200 events) then live events. |
| dashboard | `GET /metrics/{run_id}`, `GET /metrics/compare?before=&after=` | Both slash forms of `compare` work. |
| anyone | `POST /runs/resume/{run_id}` | Re-attach to a run core isn't on (see below). |

## Environment

```
ROBOT_URL=http://127.0.0.1:8200      PERCEPTION_URL=http://127.0.0.1:8150
PLANNER=llm|rule                     FORGE_DB=runs/forgemind.sqlite
CORE_STALL_SECONDS=180               CORE_WATCHDOG_INTERVAL=5
```

`CORE_STALL_SECONDS` must stay above the robot service's `HUMAN_TIMEOUT_SECONDS` (120), or
the watchdog will call for help while a human is still placing the part.

## Run discipline (this is the part that bites at 3 AM)

- Start every run from the dashboard or `POST /runs/start`. Events posted with no run open
  land in an implicit run called `scratch`, which is a sign something started out of order.
- **If core restarts mid-run it re-adopts the open run automatically** — same run id, same
  mode, kit numbering continues. You'll see `[core] resumed run ... with N kits` in
  `logs/core.log`. Check that line after any restart before recording anything.
- Kit ids restart at `kit_01` every run and that is fine: kits are keyed by
  `(run_id, kit_id)`, so an earlier run's kits are still there. `GET /kits?run_id=baseline_01`
  after three runs still returns baseline's twelve.
- End a run before starting the next one, so the before/after comparison has clean bounds.

## Definitions worth agreeing on out loud

**Escape** = a kit the camera found defective reached Bob. It is stamped on the
`KIT_RECEIVED` event *and* counted in `metrics.escapes`, and those two are now the same
number by construction — if the event feed and the metrics tab ever disagree on camera,
that's the bug to report. A kit that was never inspected is **not** an escape; that gap
shows up as `kits_started - kits_inspected`.

**Recovery attempt** = a `RECOVERY_APPROVED`, i.e. the governor let the actuator move.
**Verified recovery** = the camera then saw a complete kit. Attempts without verification
are the honest denominator of `recovery_success_rate`.

## Debugging

```bash
tail -f logs/core.log                                    # resume line, watchdog, planner fallbacks
curl -s localhost:8100/state | python -m json.tool       # run, telemetry, robot, every kit
curl -s "localhost:8100/events?run_id=recovery_01&limit=30&tail=true" | python -m json.tool
```

Look for `illegal_transition` in an event payload: it means core got an event that made no
sense for that kit's state. It is recorded, never silently dropped, and it is usually the
first sign that events are being matched to the wrong kit.

Drive the whole loop with no camera and no model:

```bash
ROBOT_ADAPTER=mock uvicorn services.robot.main:app --port 8200 &
PLANNER=rule uvicorn services.core.main:app --port 8100 &
python scripts/synthetic_run.py --mode recovery --fast --auto-human
```

## Tests

`PYTHONPATH=. python -m pytest -q` → 42 tests, no network, no model, no camera.

- `test_governor.py` (9), `test_metrics.py` (4), `test_state_machine.py` (3) — pure logic.
- `test_orchestrator.py` (21) — the real loop over ASGI with the robot and perception faked:
  hold → recover → verify → release, denials, retry-then-human, robot errors, a dead camera,
  the watchdog, restart/resume, run isolation, and the escape flag matching the metric.
- `test_store.py` (5) — kit identity across runs, legacy-database migration, event windows.

If you change `shared/schemas.py`, tell everyone first and run this suite; it is the fastest
check that the contract still holds.
