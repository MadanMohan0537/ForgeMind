# Bounty claim boundaries

Use only claims that the final recording verifies visibly.

## Best use of Nemotron

- Deployed model: `nemotron-3.5-lightning:latest`, Q4_K_M, 32.9B total / approximately 3B active MoE, local Ollama.
- Role: structured high-level action proposals plus evidence-grounded hypotheses, experiments, and verdicts.
- Safety: a deterministic governor validates every action; the model never emits joint commands or computes dashboard metrics.
- Measured model workload: 74.135 aggregate output tokens/s across 492 structured regulatory-extraction calls. This is a separate throughput benchmark and must not be presented as per-kit action latency.
- Measured ForgeMind analysis on the DGX: hypothesis generation 9.9 s and experiment generation 5.0 s in the documented P3 replay.

Do not claim NVFP4, speculative decoding, a 120B runtime, or an unmeasured per-kit median.

## NemoClaw / OpenShell

Do **not** select this bounty with the current build. ForgeMind uses the execution plan's host-agent fallback. The installed NemoClaw sandbox is an unrelated Qwen setup and is not part of ForgeMind.

Eligibility requires a dedicated ForgeMind sandbox, the applied `services/agent/openshell_policy.yaml`, and independent verification that robot access, internet access, and out-of-workspace writes were blocked with no side effect. A self-reported `POLICY_DENIED` event alone is not proof.

## Business answer

- Buyer: small assembly operations that already have cameras but lack a data-science team.
- Wedge: one camera and station screens expose escapes, rework, recovery, and cycle time without uploading factory video.
- Differentiation: ForgeMind proposes the next controlled process test, measures the result in code, and uses fewer interventions when prevention improves.
- Local value: private video, predictable latency, and governed operation even when cloud services are unavailable. Wi-Fi-off behavior still requires physical verification before that sentence is used in the video.
