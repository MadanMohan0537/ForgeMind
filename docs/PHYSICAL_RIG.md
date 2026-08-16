# Physical rig and rehearsal (P5)

## Table layout

- Use a matte, light tabletop with high contrast against red bodies, black wheels, and blue roofs.
- Tape and label the Alice, inspection, recovery, Bob, Charlie, approved, and rejected zones.
- Label the fixed spare bins Body, Wheel, and Roof.
- Prepare eight numbered white trays and a reference card: 1 body, 2 wheels, 1 roof.
- Fix the phone overhead so it cannot drift into the recovery zone; lock focus, exposure, and white balance.
- Keep the DGX Spark and live dashboard visible in the opening shot without blocking the line.

## Safety and claim boundaries

- Mark the recovery exclusion zone and keep hands outside it during any automatic motion.
- Keep the stop control reachable and start fixed routines from their known home pose.
- Never feed model-generated coordinates or raw joint commands to an actuator.
- The tested build uses `HumanArm` or `MockArm`; describe it exactly. `RealArm` remains a stub.
- Extra or uncertain parts go to human review. Automatic removal is not supported.

## Comparable physical runs

Use eight kits and the same camera, lighting, duration, kit mix, and QC criteria:

1. Baseline: Alice prepares three kits at once without a checklist; recovery is disabled.
2. Recovery: repeat the same preparation method with governed one-part recovery enabled.
3. Improved: prepare one kit at a time using the visible checklist.

Record actual duration, correct products, incomplete kits, escapes, recoveries, rejects, and throughput. Never replace an unavailable measurement with an estimate.

## Rehearsal order

1. Open `/dashboard` and all four `/station/*` pages on the final devices.
2. Test every station button against Core and confirm rejected taps show a visible error.
3. Rehearse hold -> proposal -> governor -> HumanArm -> reinspection -> release.
4. Rehearse the recorded-video fallback if the phone stream fails.
5. Run `bash scripts/check_env.sh`, hide secrets/notifications, and record two full takes.
