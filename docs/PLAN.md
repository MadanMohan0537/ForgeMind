# ForgeMind — 14-hour build plan (Spark track, See + Do inside)

Code freeze **11:00 AM Sunday**. Submission needs: GitHub link, project description, 3–5 min video.
Everything below assumes ~9 PM Saturday start. If you start later, cut from the bottom of each list, never the top.

## 0. First 30 minutes — everyone, together

- [ ] `git clone` this scaffold onto the GN100 and every laptop. `pip install -r requirements.txt` on the GN100.
- [ ] Freeze the contracts: read `shared/schemas.py` once, out loud. Nobody edits it after this without telling the group.
- [ ] Assign parts 1–5 below. Write names next to them here.
- [ ] Ask Kiana/Apurv in Discord: "Is the NemoClaw+OpenShell bounty open to Spark-track teams?" (decides Part 3's priority).
- [ ] Network test: from the GN100, `ping <phone-ip>`. If it fails (client isolation), pick ONE: USB-tether a phone to the Spark, or run a phone hotspot that the Spark and all laptops join.
- [ ] `bash scripts/start_all.sh` on the GN100 with `SOURCE=0` (or a file) just to prove the three services boot; open `http://<spark>:8100/dashboard`.
- [ ] Post `PYTHONPATH=. python -m pytest -q` output in the group chat (42 tests should pass).

## 1. Parts

### Part 1 — Perception (services/perception)   owner: ______
- [ ] `bash scripts/start_mediamtx.sh` on the GN100. Phone: Larix Broadcaster → publish `rtsp://<spark>:8554/line`. Lock exposure/WB, plug in, no auto-lock.
- [ ] `SOURCE=rtsp://127.0.0.1:8554/line uvicorn services.perception.main:app --port 8150` → open `http://<spark>:8150/calibrate`.
- [ ] Draw `inspection_zone`, `robot_zone` (where the recovery hand works), `assembly_queue`. Save.
- [ ] Put a complete kit in the zone; tune HSV until counts read `red_body=1 black_wheel=2 blue_roof=1` for 10 s straight. Save colors.
- [ ] Remove one wheel → dashboard shows the kit HELD with `missing black_wheel`. That is milestone 1. Post a screenshot.
- [ ] Add the wheel back by hand → kit re-inspected → RELEASED. That is milestone 2.
- [ ] Set `VLM_URL` when Part 4 gives it to you → `VLM_VERIFICATION` events appear.
- [ ] Record 60 s of a clean run to `runs/golden.mp4` (phone screen-record or `ffmpeg -i rtsp://127.0.0.1:8554/line -t 60 -c copy runs/golden.mp4`). Replay: `SOURCE=runs/golden.mp4 REPLAY_LOOP=1`.
- Fallback if RTSP is a fight: Android "IP Webcam" app → `SOURCE=http://<phone>:8080/video`.

### Part 2 — Core (services/core)   owner: Graeme
See `docs/CORE.md` for how core behaves, what it promises the other parts, and how to debug it.
- [x] Read `main.py` orchestrator (`_after_inspection`, `_recovery_flow`) until you can draw it. Then own it.
- [x] Run `python scripts/synthetic_run.py --mode baseline --fast` and `--mode recovery --fast --auto-human` (with `ROBOT_ADAPTER=mock` for now). Metrics must match `services/core/tests`. — both match the goldens.
- [x] Harden the failure branches the synthetic run never reaches: kit identity across runs, mid-run restart, stalled kits, dropped background tasks, escape flag vs escape metric. 42 tests.
- [x] `python scripts/open_data_ai4i.py --download` (works without the LLM). — 10,000 rows, failure rate 0.0339.
- [ ] Once Super is up, run `open_data_ai4i.py` without `--download` and paste `runs/open_data_ai4i.md` into README.
- [ ] Add anything the dashboard needs (new endpoints), keep tests green.
- [ ] Watch `logs/core.log` during the first live kits; fix state-machine surprises here, not in perception.
- [ ] Own the 7:00 AM feature freeze: no metric formula changes after it.

### Part 3 — Models + agent (services/agent, services/core/llm.py)   owner: ______
- [ ] `bash scripts/serve_super.sh` (edit MODEL to your local checkpoint). Then `PYTHONPATH=. python -c "from services.core import llm; print(llm.health())"`.
- [ ] Prove structured output: `python - <<'PY'` … call `llm.propose_action(WorldState(...))` and `llm.generate_hypotheses` on `services/core/synthetic.run_events("baseline_01","baseline")`. If json_schema fails, `llm.py` already falls back to guided_json then free-form; if all three fail, set `LLM_THINK_MODE=tag` and retry.
- [ ] Tune `prompts.py` until hypotheses cite real event ids and name different stations. Keep outputs short.
- [ ] NemoClaw: follow `services/agent/README.md`. Checkpoint **1:00 AM**: sandbox agent can call vLLM and `GET /events`. If not → run `python -m services.agent.agent_loop --watch` on the host and move on.
- [ ] `--demo-denial` → three DENIED rows on the Containment tab. Screenshot for BOUNTIES.md.
- [ ] Memory checkpoint (~3 AM): `free -h`. If ≥25 GB free, `bash scripts/serve_lightning.sh` and set `LLM_FAST_MODEL=lightning LLM_FAST_BASE_URL=http://127.0.0.1:8002/v1` for core. Otherwise skip Lightning and say so.

### Part 4 — VSS / NVIDIA VLM + Spark story (perception/verify.py, docs/SPARK_STORY.md)   owner: ______
- [ ] Start the VSS DGX Spark playbook NOW (NGC key needed; pulls take hours). Alerts profile, `--use-remote-llm` → `http://<spark>:8000` model `super`.
- [ ] Checkpoint **1:00 AM**: VSS answers a question about a sample clip. If not → `bash scripts/serve_cosmos.sh` and give Part 1 `VLM_URL=http://127.0.0.1:8001/v1 VLM_MODEL=cosmos`. Either way an NVIDIA VLM verifies detections.
- [ ] If VSS is up: implement `vss_ask_video()` in `services/perception/verify.py`; register alerts ("kit placed in inspection zone", "hand in robot zone").
- [ ] Fill `docs/SPARK_STORY.md`: tokens/s, VLM verify latency, perception fps, `free -h`, kit-inspect-to-decision seconds. Run the wifi-off test and write down what still worked.
- [ ] Own `bash scripts/check_env.sh` every hour.

### Part 5 — Product + submission (dashboard, stations, physical set, video, README)   owner: ______
- [ ] Physical set: light matte tabletop, tape the zones, three bins, flat paper parts (red rectangle, black circles, blue roof), white index cards as trays, printed car outline for Bob. Phone mount overhead (tape to a lamp/box shelf).
- [ ] Station phones: `http://<spark>:8100/station/alice|bob|charlie`; recovery station laptop: `/station/recovery`. Test every button once.
- [ ] Dashboard polish only where the video will look: Now card, kit tickets, Findings, Containment.
- [ ] Draft `docs/DEMO_SCRIPT.md` shot list by 1 AM. Rehearse once with mock data (`synthetic_run.py`).
- [ ] Runs (needs everyone): baseline → recovery → improved (single-kit prep). 8 kits each, same duration. Alice induces batch-prep errors naturally: prepare 3 kits at once, no checklist. Say in the video how errors were induced.
- [ ] Record video takes at 7:30 and 8:30. Upload unlisted YouTube by 9:30. README + description by 10:00. Submit by 10:15.

## 2. Clock

| Time | Must be true | Owner check |
|---|---|---|
| 10:30 PM | Phone video on the Spark, Super answers a schema call, VSS + NemoClaw installs running, table built, repo pushed | all |
| 1:00 AM | Live counting; synthetic runs green; hypotheses on synthetic events; **VSS checkpoint**; **NemoClaw checkpoint** | 1,2,3,4 |
| 3:00 AM | Full loop live with HumanArm; dashboard live; baseline run #1 recorded (golden clip); **memory checkpoint** | all |
| 5:30 AM | Recovery + improved runs done; real hypotheses/experiment/verdict; denial demo; perf numbers | all |
| 7:00 AM | FEATURE FREEZE. Bugfixes only. | 2 |
| 7:30 / 8:30 AM | Video takes | 5 |
| 9:30 AM | Video uploaded; README done; data + clips copied OFF the GN100 | 5, 4 |
| 10:15 AM | Submitted | 5 |

Nap rotation: two people 1–3 AM, two people 3–5 AM. Whoever pitches at 11:30 sleeps.

## 3. What to cut, in order, if behind
1. Lightning (keep Super only). 2. VSS blueprint (keep direct Cosmos). 3. NemoClaw sandbox (keep host agent loop). 4. Improved run (keep baseline + recovery, verify with `intervention_reduction` explained as "not measured").
Never cut: live perception → hold → recovery → verify → release, the baseline vs recovery comparison, the video.
