# ForgeMind — 5-Person Execution Plan (direct mapping onto your real scaffold)

Good — with five people, you don't need to merge anything. Your scaffold's own `docs/PLAN.md` already has exactly five parts with five `owner: ______` blanks; this document fills those blanks in with a full role brief for each person, adds the pre-kickoff prep window, cross-training pairs, a per-person risk register, and a 5-way breakdown of the demo recording. Read it alongside `docs/PLAN.md` — this is the elaborated version, not a replacement.

**Where you are right now:** early-to-mid Saturday afternoon. The plan assumes a ~9 PM Saturday start, code freeze 11:00 AM Sunday, submission by 10:15 AM. That gives you a real head start window — see Section 1 — and it matters more with five people, because more of you means more independent things that can be getting done in parallel *before* the official clock starts.

---

## 1. Names, not letters

Assign an actual person to each part right now, in the group chat, before anyone reads further. For the rest of this document we'll refer to them as **P1–P5** matching your scaffold's Part 1–5 numbering. Don't use "A/B/C" as team labels — your product already has stations named Alice, Bob, and Charlie, and mixing those up during a 3 AM debugging session is exactly the kind of avoidable confusion you don't want.

| | Owns | Repo area |
|---|---|---|
| **P1** | Perception | `services/perception/` |
| **P2** | Core (orchestrator, state machine, governor, metrics, db, dashboard) | `services/core/` |
| **P3** | Models + agent (Nemotron, NemoClaw/OpenShell) | `services/agent/`, `services/core/llm.py`, `services/core/prompts.py` |
| **P4** | VSS / NVIDIA VLM + Spark story | `services/perception/verify.py`, `docs/SPARK_STORY.md` |
| **P5** | Product + submission (physical set, stations, video, README) | dashboard polish, physical rig, `docs/DEMO_SCRIPT.md` |

---

## 2. Right now, before 9 PM — five things happening in parallel

You have a real window before kickoff. Two of your own docs explicitly call for starting early (Part 4's NGC pull "takes hours"; Part 3's NemoClaw playbook install is also non-trivial) — don't let those sit idle until 9 PM just because the plan's checklist starts there.

| Who | Do now |
|---|---|
| **P1** | Buy/print the physical kit: red rectangle bodies, black wheel circles, blue roof pieces, index-card trays, printed car outline for Bob's station, three labeled bins. Install and test Larix Broadcaster (or confirm IP Webcam as fallback) on the phone you'll use. |
| **P2** | Read `main.py` (`_after_inspection`, `_recovery_flow`), `governor.py`, `state_machine.py`, `metrics.py` end to end until you can draw the flow from memory. If you have the repo already, run `PYTHONPATH=. python -m pytest -q` now so you know the 16 tests pass on a clean checkout before anyone's added real load. |
| **P3** | Confirm NGC/model access for Nemotron Super; get the checkpoint path ready for `serve_super.sh`. Read `services/agent/README.md` once so the NemoClaw steps aren't new to you at 1 AM. |
| **P4** | **Start the VSS DGX Spark playbook pull immediately** — this is the single most valuable thing anyone can do in this window, since it's pure unattended wait time otherwise. Get your NGC key sorted first if you haven't. |
| **P5** | Draft the shot-by-shot plan for `docs/DEMO_SCRIPT.md` against your specific space (where's the GN100 going to sit in frame, where's the overhead phone mount) so you're not solving two problems — content and physical logistics — at 1 AM. |

---

## 3. First 30 minutes — everyone together, exactly as your PLAN.md says

Do not skip this even though you have five capable people who could each just start coding in their own corner. This step is what prevents five working pieces from failing to fit together later:

- `git clone` the scaffold onto the GN100 and every laptop; `pip install -r requirements.txt` on the GN100.
- **Freeze the contracts:** read `shared/schemas.py` out loud, together. After this, nobody edits it without telling the whole group first — a silent schema change is the single most likely way to burn hours at 3 AM chasing a bug that isn't really a bug.
- Confirm this document's P1–P5 assignments out loud; write names next to the blanks in your own `docs/PLAN.md` too, so anyone opening that file mid-hackathon sees the same assignment.
- Ask in the hackathon Discord whether the NemoClaw+OpenShell bounty is open to your track — this decides how hard P3 should push on the sandbox step later.
- Network test: from the GN100, `ping <phone-ip>`. If it fails (client isolation), pick one fix now: USB-tether a phone to the Spark, or run a phone hotspot the Spark and every laptop joins.
- `bash scripts/start_all.sh` with `SOURCE=0` just to prove all three services boot; open the dashboard.
- Post the `pytest` output (16 passing) in the group chat.

---

## 4. Interface contracts — read, don't invent

`shared/schemas.py` is already the frozen contract between all five of you. The parts of it that matter most for cross-person handoffs:

- **P1 → P2:** `Event` objects, especially `KIT_ARRIVED` and `KIT_INSPECTED` (payload carries `detected`/`missing`/`extra`/`confidence`).
- **P2 → P3:** `RunMetrics` and the raw event log — P3's prompts should read these, never raw video or raw camera frames.
- **P3 → P2:** `ActionProposal` — this is a proposal only. `governor.py`'s `validate()` is the *only* code allowed to turn it into a `RobotRequest`. If anyone ever wires LLM output straight to the robot service "just to save time," stop — that's the exact governance story the judges are being shown.
- **P2 → P3 (after a run):** `VerificationVerdict` (`supported` / `weakened` / `inconclusive`) — P3's final narrative reads this, not raw before/after numbers it has to interpret itself.
- **P1 ↔ P4:** `VLM_VERIFICATION` events — once P4 hands P1 a `VLM_URL`, perception starts emitting these as a second opinion alongside its own OpenCV counts.
- **P2 → P5:** everything the dashboard renders (`RunMetrics`, `HypothesisSet`, `ExperimentPlan`, `POLICY_DENIED` events for the Containment tab) — P5 owns the *display* of P2's and P3's data, not new data shapes.

---

## 5. Part briefs

### P1 — Perception
**Milestones, in order:** get RTSP (or IP Webcam fallback) reaching the Spark → draw `inspection_zone`, `robot_zone`, `assembly_queue` in `/calibrate` → tune HSV until a complete kit reads `red_body=1 black_wheel=2 blue_roof=1` steadily for 10 seconds → remove one wheel and confirm the dashboard shows the kit HELD with `missing black_wheel` (**milestone 1**) → add the wheel back and confirm re-inspection releases it (**milestone 2**) → once P4 hands you a `VLM_URL`, confirm `VLM_VERIFICATION` events start appearing → record 60 seconds of a clean run to `runs/golden.mp4` as a replay fallback.

**Definition of done:** a live 2-minute run produces correctly timestamped events for all three stations with no manual correction, and it survives being replayed from `golden.mp4` if the live camera has to be swapped out.

### P2 — Core
**Milestones:** read the orchestrator until you can draw `_after_inspection` and `_recovery_flow` from memory → run `synthetic_run.py --mode baseline --fast` and `--mode recovery --fast --auto-human` with `ROBOT_ADAPTER=mock`, confirm metrics match `services/core/tests` → add any dashboard endpoints P5 needs, keeping tests green → run `open_data_ai4i.py --download` early (works without the LLM) → watch `logs/core.log` during the first live kits and fix state-machine surprises here, not by asking P1 to change perception.

**Definition of done:** feeding any two real event logs (baseline + experiment) through the pipeline produces metrics and a verification verdict that match what a human watching both runs would conclude — check this by hand at least once before 5:30 AM.

### P3 — Models + agent
**Milestones:** get Nemotron Super serving and confirm `llm.health()` responds → prove structured output on both `propose_action` and `generate_hypotheses` against `services/core/synthetic.run_events(...)` (the code already has a json_schema → guided_json → free-form fallback chain if the first attempt fails) → tune `prompts.py` until hypotheses cite real event IDs and name different stations, keeping outputs short → attempt NemoClaw per `services/agent/README.md`, checkpoint at 1:00 AM: if the sandbox can call vLLM and read `/events`, keep going; if not, fall back immediately to `python -m services.agent.agent_loop --watch` on the host and don't return to the sandbox → run `--demo-denial` and confirm three DENIED rows land on the Containment tab, screenshot it for `docs/BOUNTIES.md` → at the ~3 AM memory checkpoint, check `free -h`; only attempt Lightning if you have ≥25 GB free, and treat it as fully optional.

**Definition of done:** the hypothesis board shows scored, evidence-linked hypotheses that plausibly match a human's read of P2's real metrics, every recommended experiment comes from the approved list, and the containment demo runs cleanly on command.

### P4 — VSS / NVIDIA VLM + Spark story
**Milestones:** VSS pull already started in Section 1 → checkpoint 1:00 AM: VSS answers a question about a sample clip; if not, fall back to `serve_cosmos.sh` and hand P1 `VLM_URL=http://127.0.0.1:8001/v1 VLM_MODEL=cosmos` — either path gets you an NVIDIA VLM doing verification, which is what matters → if VSS is up, implement `vss_ask_video()` in `perception/verify.py` and register the two alerts ("kit placed in inspection zone", "hand in robot zone") → fill in `docs/SPARK_STORY.md`'s numbers as they become available (tokens/s, VLM latency, perception fps, memory in use) → run the Wi-Fi-off test once before recording and write down exactly what kept working → own `check_env.sh` on an hourly cadence all night.

**Definition of done:** `docs/SPARK_STORY.md` has real numbers in every blank (not placeholders), and you've personally verified the Wi-Fi-off claim works before anyone says it on camera.

### P5 — Product + submission
**Milestones:** build the physical set (matte tabletop, taped zones, three bins, parts, trays, phone mount) → get all four station pages working (`/station/alice`, `/station/bob`, `/station/charlie`, `/station/recovery`) and test every button once → polish the dashboard only where the camera will actually point — Now card, kit tickets, Findings tab, Containment tab, nothing else → draft the `docs/DEMO_SCRIPT.md` shot list by 1:00 AM and do one full rehearsal with `synthetic_run.py` mock data before anyone's tired → run the three real physical runs (baseline → recovery → improved single-kit-prep), 8 kits each, same duration, with Alice-the-station inducing batch-prep errors naturally (3 kits prepped at once, no checklist) — and say in the video exactly how the errors were induced, since that honesty is part of the pitch → record takes at 7:30 and 8:30, upload unlisted by 9:30, README + description by 10:00, submit by 10:15.

**Definition of done:** the video is under 5:00 (3:30 target), every claim in it matches a number that's actually on the dashboard in the shot, and the submission is in with time to spare, not at 10:14.

---

## 6. Cross-training pairs

With five people you can afford real backup coverage without anyone learning a whole extra subsystem. Pair up along natural handoffs, by the 1:00 AM checkpoint:

- **P1 ↔ P2:** P1 shows P2 how to regenerate an event log from `golden.mp4` if the live camera needs a reset mid-demo; P2 shows P1 the metrics engine's expectations for event shape so P1 can self-diagnose schema drift.
- **P2 ↔ P3:** P2 walks P3 through the exact metrics formulas so P3 can sanity-check hypothesis confidence without waiting on P2; P3 shows P2 how to re-trigger a hypothesis generation run manually in case the automatic analyst loop stalls.
- **P4 ↔ P1:** P4 shows P1 how to swap `VLM_URL` between VSS and the Cosmos fallback so P1 isn't blocked if P4 is mid-fix on something else.
- **P5 ↔ everyone:** P5 should know enough about each dashboard tab's data source to narrate any of it at a basic level during recording, since P5 is most likely to be behind the camera or driving playback.

No demo-day failure should require exactly one specific person to be available and calm at the exact right moment.

---

## 7. Risk register

| Risk | Owner | Mitigation |
|---|---|---|
| Live camera/lighting glitches during recording | P1 | `golden.mp4` replay fallback (`REPLAY_LOOP=1`), rehearsed swap in under 10 seconds |
| VSS/NGC pull doesn't finish in time | P4 | Direct Cosmos fallback via `serve_cosmos.sh`, already scripted — no schedule risk if you fall back at the 1:00 AM checkpoint instead of fighting it all night |
| NemoClaw sandbox never talks to vLLM | P3 | Host agent loop (`agent_loop.py --watch`) keeps the real multi-step agent behavior; only the containment bounty write-up is lost |
| A metrics number on screen doesn't match what happened on camera | P2 | Feature freeze at 7:00 AM — no formula changes after that point, even to "improve" them |
| Recording runs long or a take breaks | P5 | Two scheduled takes (7:30, 8:30); your own script's rule — no re-takes inside a shot, keep rolling and narrate what happened if something breaks |
| Judges ask to see a live, unrehearsed run | P1 + P2 | Confirm by the 7:00 AM freeze that the rig can be reset and re-run end to end in under 2 minutes |

---

## 8. Demo recording — 5-way roles

Your `docs/DEMO_SCRIPT.md` has a fixed shot list; here's who's doing what for both takes.

| Shot | On camera / narrating | Operating |
|---|---|---|
| 0:00 Table + GN100 + phones, opening line | **P5** | P1 stands by the physical table |
| 0:20–0:45 Baseline run, batch-prep induces an escape | P1 (or whoever's playing Alice) | P2 watches Core logs live for state-machine surprises |
| 1:05–1:55 Recovery: hold → propose → governor approves → HumanArm instruction → re-verify → release | **P2** narrates the governor's 9 checks | P1 executes the physical recovery step |
| 2:00–2:25 Findings tab: hypotheses, experiment, improved-run compare | **P3** narrates | P5 drives the dashboard |
| 2:50 Containment tab, `--demo-denial` | **P3** narrates | P2 has the terminal ready on cue |
| 3:05 Wi-Fi off | **P4** narrates (this is P4's verified claim from Section 5) | P1 or P2 physically flips Wi-Fi |
| 3:20 Open-data (AI4I) table | **P3** narrates | — |
| 3:30 Closing card | — | P5 edits |

Repeat rule from your own script: **no re-takes inside a shot.** If something breaks, keep rolling and say what happened — a team of five that visibly handles a hiccup on camera reads as more credible than one suspiciously perfect take.

---

## 9. One thing to agree on before 9 PM

With five people, you have real capacity to attempt the full scope — Lightning, the full VSS blueprint, NemoClaw sandboxing, all three physical runs. The cut order from your own `PLAN.md` (Lightning → VSS blueprint → NemoClaw sandbox → improved run) is the right one *if* you fall behind, and it should still be a real decision made at each checkpoint, not something you push through on inertia. Agree now on who has the authority to call a cut at each checkpoint — P2 is the natural owner of the 7:00 AM feature freeze since Core is the piece most likely to still have a live bug; P4 or P3 should be the one who calls off VSS or NemoClaw respectively, since they're closest to knowing whether one more hour will actually get it working or not.
