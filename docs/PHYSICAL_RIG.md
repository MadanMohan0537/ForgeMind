# Physical rig and rehearsal checklist (P5)

## Layout

- Matte tabletop with high contrast against red bodies, black wheels and blue roofs.
- Clearly taped zones: Alice, inspection, recovery/robot, Bob, Charlie, approved, rejected.
- Fixed spare bins labelled Body A, Wheel B and Roof C.
- Eight numbered trays plus a printed valid-kit reference: 1 body, 2 wheels, 1 roof.
- Overhead phone mount that cannot drift into the recovery zone.
- GB10 system and dashboard screen visible for the opening shot without blocking the table.

## Safety

- Mark the robot exclusion zone and keep hands outside it during automatic motion.
- Provide a reachable stop control and start every routine from the known home pose.
- Use fixed pick/drop positions only; never paste LLM-generated coordinates into a controller.
- Fall back to HumanArm when no supported robot is available. Label that fallback accurately.
- Automatic removal of extra or uncertain parts remains disabled.

## Three comparable runs

Use eight kits and the same duration/camera/lighting for each:

1. Baseline: Alice batch-prepares three kits at once without a checklist.
2. Recovery: same process, with governed single-part recovery enabled.
3. Improved: one-kit-at-a-time preparation with the visible checklist.

Log actual throughput, first-pass yield, held kits, recoveries, rejects and duration. Never backfill missing values with estimates.

## Rehearsal

- Test every button on all four station pages in demo mode.
- Repeat with `?api=<core-url>` after P2 exposes the station-action endpoint.
- Confirm the complete hold → proposal → approval → recovery → reinspection → release flow.
- Rehearse switching to recorded perception input if the live camera fails.
- Check framing under final lighting and lock exposure/focus where possible.
