# Demo video — 3:30 target (hard max 5:00), one continuous system, no slides

Record the dashboard with laptop screen-capture; use one phone for table b-roll (repurpose the close-up phone). Show the GN100 in frame once.

| t | Shot | Say (short) | Rubric hit |
|---|---|---|---|
| 0:00 | Table + GN100 + phones | "ForgeMind: a local AI process scientist. One phone camera, three workers, one recovery station, everything runs on this DGX Spark." | Spark story |
| 0:20 | Dashboard, Start baseline; Alice batch-preps kits | "Baseline: recovery off. The camera counts every kit; the system only watches." | Completeness |
| 0:45 | Bob takes an incomplete kit; Charlie rejects a car | "Incomplete kit escaped to assembly → reject. Every event is logged with evidence clips." | Perception accuracy |
| 1:05 | Start recovery; kit held (Now card red) | "Recovery on. One wheel missing, 97% confidence, kit held. Nemotron proposes ADD_PART; the deterministic governor checks nine conditions; approved." | Multi-step agent, branching |
| 1:30 | Recovery station phone shows instruction; human places wheel; taps DONE; camera re-inspects → released | "The actuator is a person today and an arm tomorrow — same command, same verification. Nothing is trusted until the camera confirms it." | Do + See |
| 2:00 | Findings tab: Generate hypotheses (pre-generated to save time), experiment card | "After the run, Nemotron 3 Super proposes competing explanations citing event ids, and recommends one controlled experiment: single-kit prep." | Innovation |
| 2:25 | Improved run montage (10 s) → Compare table + intervention reduction | "We ran it. Fewer missing wheels, fewer interventions. One run is weak evidence — the verifier says so." | Value, honesty |
| 2:50 | Containment tab; run `--demo-denial` live | "The analyst runs inside NemoClaw/OpenShell: it can read and think, but the robot route and the internet are denied by policy." | NVIDIA stack |
| 3:05 | Wi-Fi off; hold a kit; recovery still works | "Wi-Fi off. 120B reasoner, VLM, video buffer and the whole log in one 128 GB pool. Factory video never leaves the room." | Spark story, performance |
| 3:20 | Open-data table (AI4I) | "Same analyst on the UCI AI4I dataset: hypotheses as predicates, tested by code." | Open data |
| 3:30 | Card: repo · what's real · what's next | | |

Rules: no re-takes inside a shot; if something breaks, keep rolling and say what happened. Record take 1 at 7:30, fix, take 2 at 8:30.
