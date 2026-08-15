# Agent (NemoClaw + OpenShell)

Goal for the bounty slide: "a capable agent worth containing, then contain it."
The capable agent = the analyst loop (reads the event log, calls Nemotron, submits hypotheses/experiments).
The containment = OpenShell policy that lets it read + think + submit, and nothing else.

## Steps (Part 3 owner)
1. Playbook: build.nvidia.com/spark/nemoclaw  ("Run NemoClaw with a Local LLM"). Install, then `nemoclaw onboard`.
   - Provider: local vLLM at http://<spark>:8000/v1, model name = your `--served-model-name` (e.g. `super`).
   - Agent: OpenClaw (default) is fine; or "bring your own harness" if the wizard offers it.
   - Policy tier: strictest network preset, then add the allow rules from `openshell_policy.yaml`.
2. Inside the sandbox: `git clone <repo> /workspace/repo && cd /workspace/repo && pip install -r requirements.txt`
   `CORE_URL=http://host.docker.internal:8100 python -m services.agent.agent_loop --demo-denial`
   -> three POLICY_DENIED events appear in the dashboard containment log. Screenshot that.
3. `python -m services.agent.agent_loop --watch` and leave it running: every finished run gets analyzed automatically.
4. Write docs/BOUNTIES.md section 2 from what you actually configured (paste the real policy).

## Fallback (if `nemoclaw onboard` isn't talking to vLLM by the checkpoint)
Run the same loop on the host: `python -m services.agent.agent_loop --watch`. You keep the multi-step agent;
you drop the containment bounty. Say in the README that OpenShell is the production path.
