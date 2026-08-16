# ForgeMind demo script (P5)

Target: 3:40; hard limit: 5:00. Use one continuous system, not slides. Replace bracketed values only after the final physical runs; never narrate a number that is not visible.

| Time | Picture | Narration |
|---|---|---|
| 0:00-0:20 | Wide shot: line, overhead phone, station screens, and DGX Spark. | "ForgeMind is a local AI process scientist. It observes a production line, safely recovers a missing component, and tests the process change intended to prevent the error." |
| 0:20-0:48 | Start baseline; Alice prepares three kits at once without a checklist. | "We induce realistic preparation errors with a repeatable batch-preparation setup. Baseline observes the process but does not recover defects." |
| 0:48-1:05 | Incomplete kit reaches Bob; Charlie rejects it; show evidence event. | "A missing wheel escaped to assembly in the baseline. The detection, evidence, downstream rejection, and rework remain in the event log." |
| 1:05-1:50 | Start recovery; Now card turns red; recovery station displays the instruction. | "With recovery enabled, vision detects one missing wheel and holds the kit. Local Nemotron 3.5 Lightning proposes only ADD_PART. A deterministic governor checks the world state before the HumanArm recovery is allowed." |
| 1:50-2:10 | Human places the wheel and taps Done; camera reinspects; ticket becomes released. | "The actuator is a person in this build. Nothing is trusted until the camera sees a complete kit and releases it." |
| 2:10-2:42 | Findings, controlled experiment, baseline/improved comparison. | "Nemotron proposes competing explanations grounded in recorded event IDs and recommends single-kit preparation. Across equal eight-kit runs, [visible measured comparison]. One short run is weak evidence, so the verdict is presented with that limitation." |
| 2:42-3:02 | AI4I card in Findings. | "On 10,000 open-data rows, the model proposed four predicates. Code rejected two, supported high tool wear at 3.06 times lift, and marked one inconclusive because it selected no rows." |
| 3:02-3:22 | Cosmos response and Spark measurements; show system in frame. | "Cosmos Reason2 verifies visual evidence locally. Nemotron, Cosmos, the video buffer, and the event history share the GB10 unified-memory system." |
| 3:22-3:40 | Closing view of dashboard and line. | "ForgeMind closes the loop: observe, measure, reason, act, verify, and improve, without giving a generative model unchecked physical control." |

## Optional claims only after physical verification

- Wi-Fi off: state only the functions personally observed while disconnected.
- NemoClaw/OpenShell: the current ForgeMind analyst is the approved host fallback, not a containment demonstration. Include the containment shot only after a dedicated sandbox blocks all attempts with no side effects.
- Robot: `HumanArm` means a human executes the instruction; `MockArm` is simulation; `RealArm` is not implemented.

## Recording rules

- Record two complete takes and keep rolling through small failures.
- Keep the induced-error method visible.
- Hide keys, tokens, notifications, IP addresses, and unrelated tabs.
- Capture the dashboard at 1080p and verify the final unlisted video while logged out.
