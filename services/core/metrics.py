"""Deterministic metrics (Section 8). Pure functions over an ordered event list.

The LLM never computes a number. It only reads what this module produces.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Optional

from shared.schemas import Event, EventType as E, RunMetrics


def _ratio(n: float, d: float) -> Optional[float]:
    return round(n / d, 3) if d else None


def compute(run_id: str, events: list[Event]) -> RunMetrics:
    evs = sorted((e for e in events if e.run_id == run_id), key=lambda e: (e.ts, e.id or 0))
    m = RunMetrics(run_id=run_id)
    if not evs:
        return m

    starts = [e for e in evs if e.event == E.RUN_STARTED]
    ends = [e for e in evs if e.event == E.RUN_ENDED]
    t0 = starts[0].ts if starts else evs[0].ts
    t1 = ends[-1].ts if ends else evs[-1].ts
    m.duration_seconds = round(max(0.0, t1 - t0), 1)

    by_kit: dict[str, list[Event]] = defaultdict(list)
    for e in evs:
        if e.kit_id:
            by_kit[e.kit_id].append(e)

    kit_ids_started = {e.kit_id for e in evs if e.event in (E.KIT_STARTED, E.KIT_SENT, E.KIT_ARRIVED, E.KIT_INSPECTED) and e.kit_id}
    m.kits_started = len(kit_ids_started)
    m.kits_inspected = len({e.kit_id for e in evs if e.event == E.KIT_INSPECTED and e.kit_id})
    m.correct_products = sum(1 for e in evs if e.event == E.QC_APPROVED)
    m.rejected_products = sum(1 for e in evs if e.event == E.QC_REJECTED)
    m.unfinished_products = max(0, m.kits_started - m.correct_products - m.rejected_products)

    m.recovery_attempts = sum(1 for e in evs if e.event == E.RECOVERY_APPROVED)
    m.verified_recoveries = sum(1 for e in evs if e.event == E.RECOVERY_VERIFIED)
    m.recovery_success_rate = _ratio(m.verified_recoveries, m.recovery_attempts)
    m.human_reviews = sum(1 for e in evs if e.event == E.HUMAN_REVIEW_REQUESTED)
    m.policy_denials = sum(1 for e in evs if e.event == E.POLICY_DENIED)

    # incomplete kits, escapes, cycle time, missing histogram
    incomplete_kits = set()
    escapes = 0
    cycle_times: list[float] = []
    hist: dict[str, int] = defaultdict(int)
    for kit_id, kevs in by_kit.items():
        kit_ok: Optional[bool] = None       # None = never inspected
        first_inspection_seen = False
        start_ts = next((e.ts for e in kevs if e.event == E.KIT_STARTED), kevs[0].ts)
        end_ts = next((e.ts for e in kevs if e.event in (E.QC_APPROVED, E.QC_REJECTED)), None)
        if end_ts is not None:
            cycle_times.append(end_ts - start_ts)
        for e in kevs:
            if e.event == E.KIT_INSPECTED:
                missing = e.payload.get("missing") or {}
                extra = e.payload.get("extra") or {}
                complete = not missing and not extra
                if not first_inspection_seen:
                    first_inspection_seen = True
                    if not complete:
                        incomplete_kits.add(kit_id)
                        for part, n in missing.items():
                            hist[part] += int(n)
                kit_ok = complete
            elif e.event == E.RECOVERY_VERIFIED:
                kit_ok = True
            elif e.event == E.KIT_RECEIVED:
                if kit_ok is False:
                    escapes += 1
    m.incomplete_kits_detected = len(incomplete_kits)
    m.escapes = escapes
    m.escape_rate = _ratio(escapes, len(incomplete_kits))
    m.avg_cycle_seconds = round(mean(cycle_times), 1) if cycle_times else None
    m.missing_part_histogram = dict(hist)

    # assembly idle: Bob is ready but has nothing valid to work on
    idle = 0.0
    bob_free_since: Optional[float] = t0
    for e in evs:
        if e.event == E.KIT_RECEIVED and bob_free_since is not None:
            idle += max(0.0, e.ts - bob_free_since)
            bob_free_since = None
        elif e.event == E.CAR_DONE:
            bob_free_since = e.ts
    m.assembly_idle_seconds = round(idle, 1)

    m.rework_seconds = round(sum(float(e.payload.get("rework_seconds", 0) or 0) for e in evs), 1)
    m.max_queue = max((int(e.payload.get("count", 0)) for e in evs if e.event == E.QUEUE_MEASURED), default=0)
    dur_min = m.duration_seconds / 60.0
    m.throughput_per_min = _ratio(m.correct_products, dur_min) if dur_min else None
    m.defect_rate = _ratio(m.rejected_products, m.correct_products + m.rejected_products)
    return m


def compare(before: RunMetrics, after: RunMetrics) -> dict:
    """Before/after table (Section 7.3, 10.6) plus intervention reduction (8.8)."""
    fields = ["kits_started", "correct_products", "rejected_products", "incomplete_kits_detected", "escapes",
              "recovery_attempts", "verified_recoveries", "human_reviews", "avg_cycle_seconds",
              "assembly_idle_seconds", "rework_seconds", "max_queue", "throughput_per_min", "defect_rate"]
    rows = []
    for f in fields:
        b, a = getattr(before, f), getattr(after, f)
        delta = None if (a is None or b is None) else round(a - b, 3)
        rows.append({"metric": f, "before": b, "after": a, "delta": delta})
    ir = None
    if before.recovery_attempts:
        ir = round((before.recovery_attempts - after.recovery_attempts) / before.recovery_attempts, 3)
    return {"before_run": before.run_id, "after_run": after.run_id, "rows": rows, "intervention_reduction": ir}
