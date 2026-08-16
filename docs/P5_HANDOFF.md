# P5 product and submission handoff

Date: 2026-08-15

## Completed

- Kept the production UI served by Core at `/dashboard` and `/station/{alice,bob,charlie,recovery}`; rejected the disconnected local-storage prototype and its fabricated metrics.
- Added visible Core connection/reconnection state, failed-action messages, station links, double-tap protection, and phone-width validation.
- Exposed stored `open_data` analysis through `GET /analysis/{run_id}` and added a one-click AI4I results card to Findings.
- Corrected model and containment claims across README, demo, bounty, and submission material.
- Added physical-rig, recording, and final-submission checklists.
- Ignored SQLite runtime sidecars so a running demo does not dirty Git.

## Validation

Focused P4/P5 contracts: `21 passed`.

Browser checks against a live local Core:

- dashboard reported `core live` with no JavaScript warnings/errors;
- Alice Start/Sent, Bob Received/Done, and Charlie Approve worked;
- invalid Charlie Reject and Recovery Resolved transitions showed visible errors;
- Recovery Done stayed disabled without an approved human task;
- 390x844 station view had no horizontal overflow and two 362x82 px tap targets;
- AI4I rendered 10,000 rows, 3.39% overall failure rate, and all four deterministic verdicts.

Eight-kit synthetic rehearsals (not physical performance measurements):

| Run | Incomplete | Escapes | Rejects | Recoveries | Verified | Correct |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 2 | 2 | 2 | 0 | 0 | 6/8 |
| recovery | 2 | 0 | 0 | 2 | 2 | 8/8 |
| improved | 1 | 0 | 0 | 1 | 1 | 8/8 |

These fast synthetic durations are test timing and must not appear as production cycle-time evidence.

## Physical-only work remaining

Code cannot arrange the tabletop, operate the phones, perform comparable physical runs, disconnect Wi-Fi safely over an SSH session, record/upload the video, or submit the form. Follow `docs/PHYSICAL_RIG.md`, `docs/DEMO_SCRIPT.md`, and `docs/SUBMISSION_CHECKLIST.md` with the team.
