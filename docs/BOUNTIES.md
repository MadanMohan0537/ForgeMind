# Bounty write-ups (paste real numbers before submitting)

## 1. Best Use of Nemotron (Lightning bounty — only if Lightning is running)
- What Lightning does: the per-kit action loop (propose ADD_PART / HOLD / RELEASE, JSON-only, thinking off) — latency ___ ms median. Super does offline hypotheses/experiments.
- Why Lightning there: the loop is latency-bound and runs on every kit; 30B-A3B with DSpark speculative decoding on the Spark gives ~___ tok/s so a decision arrives before the human finishes reading the hold.
- How optimized: NVFP4 checkpoint, DSpark draft model, prefix caching, structured JSON output, thinking disabled for the loop.
(If Lightning was cut: delete this section; the "Nemotron 3 Super" story lives in README.)

## 2. Best Use of NemoClaw + OpenShell ("capable agent worth containing")
- Agent: the ForgeMind analyst (`services/agent/agent_loop.py`) — reads the event log, calls Nemotron, submits hypotheses/experiments; runs always-on with `--watch`.
- Policy (`services/agent/openshell_policy.yaml` — paste the applied version): default-deny egress; allow inference + core read routes + analysis submit; robot service (port 8200) denied; evidence read-only.
- Demonstrated: `--demo-denial` attempts robot call / internet / write outside workspace → three POLICY_DENIED events on the Containment tab (screenshot: ___).
- Why it matters: only the deterministic governor can move the actuator; the model can never reach it even if it wanted to.

## 3. Champions Choice / Ascend — 30-second business answer
- Who buys: small manufacturers / assembly lines with cameras and no data science team.
- Wedge: retrofit one camera + one station screen; value in a day (escape rate, rework, cycle time), no cloud.
- Why local: video is confidential; latency; governance keeps working offline. Why now: 128 GB Sparks make a 120B reasoner + VLM + video buffer fit on a desk.
