# ForgeMind demo script (P5)

Target: 3:30; hard limit: 5:00. Replace every bracketed measurement only after the final real runs. Never narrate a number that is not visible in the shot.

| Time | Picture / operator | Narration |
|---|---|---|
| 0:00–0:20 | Wide shot: physical line, overhead phone and GB10 system. P5 speaks. | “This is ForgeMind, a local AI process scientist. It observes a production line, safely recovers a missing component, and tests the process change that prevents the problem.” |
| 0:20–0:48 | Baseline: Alice prepares three kits at once and one naturally misses a wheel. Keep inspection zone visible. | “For our baseline, Alice batch-prepares three kits without a checklist. We intentionally use this repeatable setup to create realistic preparation errors.” |
| 0:48–1:05 | Dashboard Now card and HELD ticket. | “Vision detects the incomplete kit before Bob receives it: one of two black wheels is missing. The kit is held, not silently passed downstream.” |
| 1:05–1:55 | Recovery page plus physical correction. P2 narrates. | “Nemotron Lightning 30B proposes a high-level recovery; it never produces motor commands. The deterministic governor checks the proposal. After approval, the fixed routine—or HumanArm fallback—adds one wheel. ForgeMind reinspects, and only a verified kit is released.” |
| 1:55–2:30 | Findings tab and baseline/improved comparison. P3 narrates, P5 drives. | “The leading hypothesis links preparation bursts to missing-part events using recorded event IDs. ForgeMind proposes a controlled one-kit-at-a-time checklist experiment. Across equal [duration] runs of eight kits, first-pass yield changed from [baseline] to [improved].” |
| 2:30–2:58 | Containment tab and denial command ready in terminal. | “Governance is observable. Raw joint commands, unverified release, and uncertain part removal are denied. These refusals are part of the product.” |
| 2:58–3:18 | P4 switches Wi-Fi off; retain the model and dashboard in frame. | “On the GB10 Grace Blackwell system, perception, the NVIDIA VLM path, and Nemotron reasoning run locally. With Wi-Fi off, [only list personally verified functions] kept working.” |
| 3:18–3:30 | Closing card: loop and team names. | “ForgeMind closes the loop: observe, measure, reason, act, verify and improve—without giving generative AI unchecked physical control.” |

## Recording rules

- Record two complete takes; keep rolling through small failures and explain them honestly.
- Show the induced-error method in the baseline shot.
- Keep the GN100, physical table and live dashboard in the same opening frame.
- Hide API keys, tokens, personal notifications, IP addresses and unrelated browser tabs.
- Do not claim “robot executed” when using HumanArm; say “human-executed recovery fallback.”
- Export at 1080p and verify audio, links, duration and unlisted visibility before submission.
