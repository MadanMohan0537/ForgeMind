"""Deterministic three-station FactoryFlow demo scenarios."""
from __future__ import annotations

from shared.schemas import Event, EventType as E


def demo_events(run_id: str, t0: float = 1_000.0) -> list[Event]:
    def ev(offset: float, kind: E, cycle: str, station: str, **payload) -> Event:
        return Event(run_id=run_id, ts=t0 + offset, event=kind, kit_id=cycle,
                     payload={"cycle_id": cycle, "station": station, **payload}, source="factoryflow:simulation")

    events = [Event(run_id=run_id, ts=t0, event=E.RUN_STARTED,
                    payload={"mode": "factoryflow", "scenario": "normal_then_missing_wheel"},
                    source="factoryflow:simulation")]
    # Normal cycle establishes that Station B's ordinary processing time is 20 seconds.
    events += [
        ev(1, E.PARTS_PREPARATION_STARTED, "CAR-041", "station_a"),
        ev(13, E.PARTS_TRANSFERRED, "CAR-041", "station_a", status="ok", expected_parts=4, detected_parts=4),
        ev(21, E.ASSEMBLY_STARTED, "CAR-041", "station_b"),
        ev(41, E.ASSEMBLY_COMPLETED, "CAR-041", "station_b"),
        ev(49, E.INSPECTION_STARTED, "CAR-041", "station_c"),
        ev(74, E.INSPECTION_COMPLETED, "CAR-041", "station_c", status="approved"),
    ]
    # Failure cycle: the visible queue is at B, while the causal event is at A.
    events += [
        ev(80, E.PARTS_PREPARATION_STARTED, "CAR-042", "station_a"),
        ev(92, E.PARTS_TRANSFERRED, "CAR-042", "station_a", status="error",
           expected_parts=4, detected_parts=3, missing_component="front_right_wheel"),
        ev(100, E.ASSEMBLY_STARTED, "CAR-042", "station_b"),
        ev(101, E.ASSEMBLY_BLOCKED, "CAR-042", "station_b", reason="missing_component",
           missing_component="front_right_wheel"),
        ev(102, E.QUEUE_MEASURED, "CAR-042", "station_b", count=3),
        ev(102, E.STATION_IDLE_STARTED, "CAR-042", "station_c", reason="waiting_for_station_b"),
        ev(103, E.INTERVENTION_REQUESTED, "CAR-042", "recovery",
           action="supply_missing_component", component="front_right_wheel", destination="station_b",
           control_mode="human_teleoperation"),
        ev(106, E.OPERATOR_ACCEPTED, "CAR-042", "recovery", control_mode="human_teleoperation"),
        ev(107, E.TELEOP_STARTED, "CAR-042", "recovery", simulator="isaac_sim", arm="franka"),
        ev(115, E.TELEOP_COMPLETED, "CAR-042", "recovery", result="component_supplied"),
        ev(115, E.STATION_IDLE_ENDED, "CAR-042", "station_c", reason="station_b_resumed"),
        ev(134, E.ASSEMBLY_COMPLETED, "CAR-042", "station_b"),
        ev(142, E.INSPECTION_STARTED, "CAR-042", "station_c"),
        ev(167, E.INSPECTION_COMPLETED, "CAR-042", "station_c", status="approved"),
        Event(run_id=run_id, ts=t0 + 168, event=E.RUN_ENDED, source="factoryflow:simulation"),
    ]
    return sorted(events, key=lambda item: item.ts)
