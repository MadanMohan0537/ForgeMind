# Submission checklist (P5)

## Product freeze

- [x] Dashboard and four station pages use the real Core API; no fabricated demo data.
- [x] Dashboard displays live connection state, failures, kits, metrics, findings, AI4I results, and reported denials.
- [x] README uses the deployed model: `nemotron-3.5-lightning:latest` through local Ollama.
- [x] Automated suite covers Core, stations, model contracts, perception verification, and AI4I dashboard retrieval.
- [ ] Run the three eight-kit physical trials under the same conditions.
- [ ] Replace bracketed video narration only with visible measured results.
- [ ] Physically verify Wi-Fi-off behavior; do not infer this over SSH.

## Video

- [ ] 3-5 minutes, 1080p, clear audio, unlisted link opens while logged out.
- [ ] Show the induced-error method and the live hold/recovery/reinspection sequence.
- [ ] Show actual comparison metrics and explain that one short run is weak evidence.
- [ ] Call HumanArm a human-executed recovery, not a robot action.
- [ ] Do not claim OpenShell containment unless a dedicated ForgeMind sandbox was tested independently.
- [ ] Hide keys, tokens, private IPs, personal notifications, and unrelated browser tabs.

## Suggested submission description

ForgeMind is a local AI process scientist that turns production-line video into evidence-linked events, safely recovers a missing kit component, and tests whether a controlled process change works. On an NVIDIA GB10 Grace Blackwell system, deterministic OpenCV perception and Cosmos Reason2 verification feed a replayable event log. Nemotron 3.5 Lightning proposes high-level actions and evidence-grounded hypotheses, while a deterministic governor remains between the model and every recovery. The miniature line demonstrates Observe -> Measure -> Reason -> Act -> Verify -> Improve without giving generative AI unchecked physical control.

## Final delivery

- [ ] Repository contains no secrets, generated caches, or large recordings.
- [ ] GitHub and video links open while logged out.
- [ ] Track and bounty selections match only features actually demonstrated.
- [ ] Copy the database, evidence, measurements, and video off the DGX Spark.
- [ ] Submit early enough to reopen the confirmation page and save proof.
