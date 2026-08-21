"""Deterministic FactoryFlow dependency and root-cause analysis.

The model may narrate this result, but it never invents timing or causality.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable, Optional

from shared.schemas import Event, EventType as E, FactoryFlowRootCause


def _duration_pairs(events: list[Event], start: E, end: E, station: Optional[str] = None) -> float:
    opened: dict[str, float] = {}
    total = 0.0
    for event in events:
        if station and event.payload.get("station") != station:
            continue
        key = event.kit_id or event.payload.get("cycle_id") or "line"
        if event.event == start:
            opened[key] = event.ts
        elif event.event == end and key in opened:
            total += max(0.0, event.ts - opened.pop(key))
    return round(total, 1)


def analyze(run_id: str, source: Iterable[Event]) -> FactoryFlowRootCause:
    events = sorted((e for e in source if e.run_id == run_id), key=lambda e: (e.ts, e.id or 0))
    result = FactoryFlowRootCause(run_id=run_id)
    if not events:
        return result

    processing = {
        "station_a": _duration_pairs(events, E.PARTS_PREPARATION_STARTED, E.PARTS_TRANSFERRED, "station_a"),
        "station_b": _duration_pairs(events, E.ASSEMBLY_STARTED, E.ASSEMBLY_COMPLETED, "station_b"),
        "station_c": _duration_pairs(events, E.INSPECTION_STARTED, E.INSPECTION_COMPLETED, "station_c"),
    }
    result.station_processing_seconds = processing
    by_cycle: dict[str, dict[E, Event]] = defaultdict(dict)
    for event in events:
        if event.kit_id:
            by_cycle[event.kit_id][event.event] = event
    transfers: dict[str, float] = defaultdict(float)
    for cycle in by_cycle.values():
        if E.PARTS_TRANSFERRED in cycle and E.ASSEMBLY_STARTED in cycle:
            transfers["station_a_to_b"] += max(0.0, cycle[E.ASSEMBLY_STARTED].ts - cycle[E.PARTS_TRANSFERRED].ts)
        if E.ASSEMBLY_COMPLETED in cycle and E.INSPECTION_STARTED in cycle:
            transfers["station_b_to_c"] += max(0.0, cycle[E.INSPECTION_STARTED].ts - cycle[E.ASSEMBLY_COMPLETED].ts)
    result.transfer_seconds = {key: round(value, 1) for key, value in transfers.items()}
    result.assembly_blocked_seconds = _duration_pairs(events, E.ASSEMBLY_BLOCKED, E.TELEOP_COMPLETED)
    result.dependency_idle_seconds = _duration_pairs(events, E.STATION_IDLE_STARTED, E.STATION_IDLE_ENDED, "station_c")

    queue_max: Counter[str] = Counter()
    for event in events:
        if event.event == E.QUEUE_MEASURED:
            station = event.payload.get("station") or event.payload.get("zone", "station_b")
            queue_max[station] = max(queue_max[station], int(event.payload.get("count", 0)))
    result.backlog_by_station = dict(queue_max)
    if queue_max:
        result.observed_bottleneck = max(queue_max, key=queue_max.get)

    failures = [e for e in events if e.event == E.PARTS_TRANSFERRED and
                (e.payload.get("missing_component") or e.payload.get("status") == "error")]
    blocked = [e for e in events if e.event == E.ASSEMBLY_BLOCKED]
    idle = [e for e in events if e.event == E.STATION_IDLE_STARTED]
    evidence = failures + blocked + idle
    if failures:
        cause = failures[0]
        result.root_cause_station = cause.payload.get("station", "station_a")
        result.root_cause = "incomplete_component_transfer"
        result.missing_component = cause.payload.get("missing_component")
        result.affected_stations = ["station_b"] + (["station_c"] if idle else [])
        result.recommendation = (
            f"Verify kits at Station A and supply {result.missing_component or 'the missing component'} "
            "to Station B through a human-controlled intervention before changing Station B staffing."
        )
    elif processing["station_b"] and processing["station_b"] == max(processing.values()):
        result.root_cause_station = "station_b"
        result.root_cause = "local_assembly_time"
        result.affected_stations = ["station_c"] if idle else []
        result.recommendation = "Investigate Station B assembly time against its established baseline."
    result.supporting_event_ids = [e.id for e in evidence if e.id is not None]
    return result


def supervisor_summary(result: FactoryFlowRootCause) -> str:
    if not result.root_cause:
        return "No dependency-chain anomaly was found in this run."
    visible = (result.observed_bottleneck or "unknown station").replace("_", " ").title()
    origin = (result.root_cause_station or "unknown station").replace("_", " ").title()
    return (
        f"The visible bottleneck is {visible}, but the root cause originated at {origin}: "
        f"{result.root_cause.replace('_', ' ')}. "
        f"Station B was blocked for {result.assembly_blocked_seconds:.1f} seconds and downstream "
        f"dependency-driven idle time was {result.dependency_idle_seconds:.1f} seconds. "
        f"{result.recommendation}"
    )
