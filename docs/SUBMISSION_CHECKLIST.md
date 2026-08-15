# Submission checklist (P5)

## Before code freeze

- [ ] Replace all model references with NVIDIA Nemotron Lightning 30B.
- [ ] Confirm the exact model identifier with P3's server configuration.
- [ ] Test `/`, Alice, Bob, Charlie and Recovery pages on the demo device.
- [ ] Confirm P2's API path and payload; update README if it differs from `/api/station/actions`.
- [ ] Replace bracketed demo-script values with measured run results.
- [ ] Confirm every SPARK_STORY metric is measured, not estimated.

## Video

- [ ] Duration below 5:00 (target 3:30).
- [ ] Error-induction method stated clearly.
- [ ] No secrets, personal notifications or private IPs visible.
- [ ] Claims match visible dashboard values.
- [ ] HumanArm and physical robot behavior described accurately.
- [ ] Final upload plays at 1080p with clear audio and correct visibility.

## Suggested submission description

ForgeMind is a local AI process scientist that turns production-line video into evidence-linked events, safely recovers a missing kit component, and verifies whether a controlled process improvement works. Running on NVIDIA GB10 Grace Blackwell hardware, it combines computer vision and NVIDIA VLM verification with NVIDIA Nemotron Lightning 30B reasoning. Nemotron proposes only high-level actions; a deterministic governor validates every recovery, and vision must verify the corrected kit before release. Our miniature line demonstrates the full loop: Observe → Measure → Reason → Act → Verify → Improve.

## Final review

- [ ] README setup works from a clean machine.
- [ ] Repository contains no secrets, large recordings or generated cache files.
- [ ] Repository URL and unlisted video URL open in a logged-out browser.
- [ ] Track and bounty selections match features actually demonstrated.
- [ ] Submit with enough time to reopen the confirmation page and capture proof.
