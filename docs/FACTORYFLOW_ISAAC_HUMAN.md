# FactoryFlow AI: three-station simulation and human-controlled Isaac arm

## Demo claim

FactoryFlow does not judge the worker at the station with the largest visible queue. It reconstructs the event dependency chain and distinguishes the observed bottleneck from the originating process failure.

The canonical failure is:

```text
Station A transfers a kit without the front-right wheel
  -> Station B cannot complete assembly
  -> backlog becomes visible at Station B
  -> Station C is idle while waiting for B
  -> FactoryFlow attributes the cause to Station A
  -> an external operator supplies the wheel using an Isaac Sim arm
  -> assembly and inspection resume
```

## Run the event-first demo

Activate the repository environment and set `PYTHONPATH` as described in the main README, then start the services:

```bash
ROBOT_ADAPTER=isaac_human MODEL_RUNTIME=ollama REQUIRE_VLM=0 bash scripts/start_dgx.sh
```

Open:

- `http://<spark>:8100/factoryflow` for the process/root-cause view.
- `http://<spark>:8100/operator` for the external operator.
- `http://<spark>:8100/dashboard` for the append-only event history.

Press **Run demo scenario** on the FactoryFlow page. The same scenario can be loaded from a terminal with:

```bash
python scripts/factoryflow_demo.py
```

## Human authority boundary

`ROBOT_ADAPTER=isaac_human` does not send joint positions. It exposes an intervention session with four operator actions:

- Accept: claim the intervention and begin teleoperation.
- Complete: assert that the wheel was placed and the arm returned to a safe pose.
- Cancel: reject or abandon the intervention.
- Emergency stop: stop the actuator workflow immediately.

The operator controls the arm using Isaac Sim's configured keyboard, gamepad, SpaceMouse, or other controller. FactoryFlow supplies only the part, source bin, target zone, and safety-governed intent.

## Isaac Sim scene contract

The scene should provide:

- Franka Panda (or another configured manipulator) with a parallel gripper.
- Station A parts bins, including `wheel_bin`.
- Station B assembly/inspection target named `inspection_zone`.
- Station C inspection area.
- One red body, two black wheels, and one blue roof per complete product.
- A fixed virtual camera if the perception service will consume rendered frames.
- Joint/workspace limits and a reachable safe home pose.

The repository deliberately keeps the simulator connection behind the `IsaacHumanArm` adapter. Isaac Sim owns low-level motion and physics; FactoryFlow owns intervention intent, operator approval, verification, and audit history.

## Evidence and analysis

`GET /factoryflow/analysis/{run_id}` returns deterministic values for:

- observed bottleneck;
- root-cause station and failure type;
- affected downstream stations;
- Station B blocked duration;
- Station C dependency-idle duration;
- station processing and transfer time;
- maximum backlog; and
- supporting event identifiers.

Nemotron may translate those computed facts into a supervisor-friendly explanation, but it must not invent the measurements or directly control the arm.

## Honest boundary

The repository now contains the event model, causal analysis, dashboards, operator session, API, and adapter contract. A complete graphical Isaac Sim demonstration still requires installing/launching Isaac Sim and constructing or loading the USD workstation scene. That simulator-specific asset work is intentionally separate from the tested service logic.
