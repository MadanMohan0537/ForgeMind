"""Synthetic runs that look like real ones. Used by tests and scripts/synthetic_run.py.

Baseline: 12 kits, kits 3/7/11 missing one wheel, recovery disabled -> escapes, 2 rejects, rework.
Recovery: same errors, robot fixes all three, 0 escapes.
Improved: single-kit prep, only kit 8 incomplete, one recovery.
"""
from __future__ import annotations

from shared.schemas import Event, EventType as E, REQUIRED_PARTS


def _kit(i: int) -> str:
    return f"kit_{i:02d}"


def _detected(missing_wheel: bool) -> dict:
    d = dict(REQUIRED_PARTS)
    if missing_wheel:
        d["black_wheel"] = 1
    return d


def run_events(run_id: str, mode: str, t0: float = 1000.0, n_kits: int = 12) -> list[Event]:
    bad = {3, 7, 11} if mode in ("baseline", "recovery") else {8}
    ev: list[Event] = []
    t = t0
    ev.append(Event(run_id=run_id, ts=t, event=E.RUN_STARTED, payload={"mode": mode}))
    cycle = 12.0 if mode == "improved" else 10.0
    for i in range(1, n_kits + 1):
        k = _kit(i)
        start = t0 + 2 + (i - 1) * cycle
        missing = i in bad
        ev.append(Event(run_id=run_id, ts=start, event=E.KIT_STARTED, kit_id=k, source="station:alice"))
        ev.append(Event(run_id=run_id, ts=start + 4, event=E.KIT_SENT, kit_id=k, source="station:alice"))
        ev.append(Event(run_id=run_id, ts=start + 6, event=E.KIT_ARRIVED, kit_id=k, source="perception"))
        det = _detected(missing)
        ev.append(Event(run_id=run_id, ts=start + 7, event=E.KIT_INSPECTED, kit_id=k, source="perception",
                        payload={"detected": det, "missing": {"black_wheel": 1} if missing else {}, "extra": {},
                                 "confidence": 0.97}))
        recv = start + 9
        if missing and mode != "baseline":
            ev.append(Event(run_id=run_id, ts=start + 7.2, event=E.KIT_HELD, kit_id=k))
            ev.append(Event(run_id=run_id, ts=start + 8, event=E.RECOVERY_PROPOSED, kit_id=k, source="planner",
                            payload={"action": "ADD_PART", "part": "black_wheel"}))
            ev.append(Event(run_id=run_id, ts=start + 8.2, event=E.RECOVERY_APPROVED, kit_id=k, source="governor"))
            ev.append(Event(run_id=run_id, ts=start + 12, event=E.RECOVERY_EXECUTED, kit_id=k, source="robot"))
            ev.append(Event(run_id=run_id, ts=start + 13, event=E.KIT_INSPECTED, kit_id=k, source="perception",
                            payload={"detected": dict(REQUIRED_PARTS), "missing": {}, "extra": {}, "confidence": 0.96,
                                     "reinspection": True}))
            ev.append(Event(run_id=run_id, ts=start + 13.1, event=E.RECOVERY_VERIFIED, kit_id=k))
            ev.append(Event(run_id=run_id, ts=start + 13.2, event=E.KIT_RELEASED, kit_id=k))
            recv = start + 15
        elif not missing and mode != "baseline":
            ev.append(Event(run_id=run_id, ts=start + 7.2, event=E.KIT_RELEASED, kit_id=k))
        ev.append(Event(run_id=run_id, ts=recv, event=E.KIT_RECEIVED, kit_id=k, source="station:bob",
                        payload={"escape": True} if (missing and mode == "baseline") else {}))
        assemble = 20 if not (missing and mode == "baseline") else 34   # Bob loses time on a bad kit
        ev.append(Event(run_id=run_id, ts=recv + assemble, event=E.CAR_DONE, kit_id=k, source="station:bob",
                        payload={"rework_seconds": 14} if (missing and mode == "baseline") else {}))
        if missing and mode == "baseline" and i != 11:
            ev.append(Event(run_id=run_id, ts=recv + assemble + 5, event=E.QC_REJECTED, kit_id=k, source="station:charlie"))
        else:
            ev.append(Event(run_id=run_id, ts=recv + assemble + 5, event=E.QC_APPROVED, kit_id=k, source="station:charlie"))
        ev.append(Event(run_id=run_id, ts=start + 8, event=E.QUEUE_MEASURED, source="perception",
                        payload={"zone": "assembly_queue", "count": min(4, (i % 5))}))
        t = recv + assemble + 5
    ev.append(Event(run_id=run_id, ts=t + 2, event=E.RUN_ENDED))
    ev.sort(key=lambda e: e.ts)
    for i, e in enumerate(ev, start=1):
        e.id = i
    return ev
