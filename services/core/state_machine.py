"""Kit lifecycle. Pure function: (state, event) -> new state, or raise IllegalTransition.

The orchestrator in main.py decides WHICH events to emit; this module only says
which transitions are legal. Keep the table small and boring.
"""
from __future__ import annotations

from typing import Optional

from shared.schemas import EventType as E, KitState as S


class IllegalTransition(Exception):
    pass


# (current_state, event) -> next_state
TRANSITIONS: dict[tuple[S, E], S] = {
    (S.PREPARING, E.KIT_SENT): S.SENT,
    (S.PREPARING, E.KIT_ARRIVED): S.ARRIVED,          # Alice forgot to tap "sent"; camera saw it anyway
    (S.SENT, E.KIT_ARRIVED): S.ARRIVED,
    (S.SENT, E.KIT_INSPECTED): S.ARRIVED,             # arrival + inspection in one event
    (S.ARRIVED, E.KIT_INSPECTED): S.ARRIVED,          # counted; core then emits HELD or RELEASED
    (S.ARRIVED, E.KIT_RELEASED): S.RELEASED,
    (S.ARRIVED, E.KIT_HELD): S.HELD,
    (S.HELD, E.RECOVERY_PROPOSED): S.RECOVERY_PROPOSED,
    (S.HELD, E.HUMAN_REVIEW_REQUESTED): S.HUMAN_REVIEW,
    (S.RECOVERY_PROPOSED, E.RECOVERY_APPROVED): S.RECOVERING,
    (S.RECOVERY_PROPOSED, E.RECOVERY_DENIED): S.HELD,
    (S.HELD, E.KIT_RELEASED): S.RELEASED,             # human fixed it and re-inspection was clean
    (S.RECOVERING, E.RECOVERY_EXECUTED): S.REVERIFYING,
    (S.RECOVERING, E.ROBOT_ERROR): S.HELD,
    (S.REVERIFYING, E.KIT_INSPECTED): S.REVERIFYING,  # re-inspection result arrives; core emits VERIFIED/FAILED
    (S.REVERIFYING, E.RECOVERY_VERIFIED): S.HELD,     # then immediately KIT_RELEASED
    (S.REVERIFYING, E.RECOVERY_FAILED): S.HELD,
    (S.HUMAN_REVIEW, E.HUMAN_RESOLVED): S.HELD,       # human says fixed; next inspection decides
    (S.HUMAN_REVIEW, E.KIT_INSPECTED): S.HUMAN_REVIEW,
    # A kit can stall mid-recovery (perception restarted, robot never answered). The core
    # watchdog escalates it to a human rather than leaving it parked in a transient state.
    (S.RECOVERY_PROPOSED, E.HUMAN_REVIEW_REQUESTED): S.HUMAN_REVIEW,
    (S.RECOVERING, E.HUMAN_REVIEW_REQUESTED): S.HUMAN_REVIEW,
    (S.REVERIFYING, E.HUMAN_REVIEW_REQUESTED): S.HUMAN_REVIEW,
    (S.HELD, E.KIT_INSPECTED): S.HELD,                # any re-inspection while held
    (S.RELEASED, E.KIT_INSPECTED): S.RELEASED,        # kit still sitting in the zone after release; ignore
    (S.RELEASED, E.KIT_RECEIVED): S.AT_ASSEMBLY,
    (S.HELD, E.KIT_RECEIVED): S.AT_ASSEMBLY,          # ESCAPE: Bob took an incomplete kit anyway (baseline run)
    (S.ARRIVED, E.KIT_RECEIVED): S.AT_ASSEMBLY,       # escape before decision
    (S.HUMAN_REVIEW, E.KIT_RECEIVED): S.AT_ASSEMBLY,  # escape
    (S.RECOVERY_PROPOSED, E.KIT_RECEIVED): S.AT_ASSEMBLY,
    (S.REVERIFYING, E.KIT_RECEIVED): S.AT_ASSEMBLY,
    (S.RECOVERING, E.KIT_RECEIVED): S.AT_ASSEMBLY,
    (S.SENT, E.KIT_RECEIVED): S.AT_ASSEMBLY,          # never went through inspection at all
    (S.PREPARING, E.KIT_RECEIVED): S.AT_ASSEMBLY,
    (S.AT_ASSEMBLY, E.CAR_DONE): S.ASSEMBLED,
    (S.ASSEMBLED, E.QC_APPROVED): S.QC_PASS,
    (S.ASSEMBLED, E.QC_REJECTED): S.QC_FAIL,
    (S.AT_ASSEMBLY, E.QC_APPROVED): S.QC_PASS,        # Bob forgot "car done"
    (S.AT_ASSEMBLY, E.QC_REJECTED): S.QC_FAIL,
}

# Events that carry no state change but are legal anywhere for a kit.
NEUTRAL_EVENTS = {
    E.KIT_STARTED, E.VLM_VERIFICATION,
    E.PARTS_PREPARATION_STARTED, E.PARTS_TRANSFERRED, E.ASSEMBLY_STARTED,
    E.ASSEMBLY_BLOCKED, E.ASSEMBLY_COMPLETED, E.INSPECTION_STARTED,
    E.INSPECTION_COMPLETED, E.STATION_IDLE_STARTED, E.STATION_IDLE_ENDED,
    E.INTERVENTION_REQUESTED, E.OPERATOR_ACCEPTED, E.TELEOP_STARTED,
    E.TELEOP_COMPLETED, E.OPERATOR_CANCELLED,
}

BLOCKING_STATES = {S.HELD, S.RECOVERY_PROPOSED, S.RECOVERING, S.REVERIFYING, S.HUMAN_REVIEW}


def next_state(state: S, event: E) -> S:
    if event in NEUTRAL_EVENTS:
        return state
    try:
        return TRANSITIONS[(state, event)]
    except KeyError:
        raise IllegalTransition(f"{event.value} not allowed from {state.value}")


def is_escape(prev_state: S, event: E, kit_incomplete: Optional[bool] = None) -> bool:
    """An escape = a kit KNOWN to be incomplete reached Bob.

    This must agree with `metrics.compute`, which counts an escape when the last
    inspection before KIT_RECEIVED showed a defect and no recovery was verified after
    it. The dashboard stamps events with this flag, so a looser definition here shows
    the operator a different number than the metrics tab.

    A kit that was never inspected (SENT/PREPARING, camera missed it) is not counted:
    nothing established it was defective. That gap is visible as
    `kits_started - kits_inspected`.

    Args:
        prev_state: kit state immediately before the event was applied.
        event: the event being applied.
        kit_incomplete: whether the latest inspection found parts missing or extra.
            Required to judge an ARRIVED kit, where core has not yet decided.
            None means "not known", and an ARRIVED kit is then not counted.
    """
    if event != E.KIT_RECEIVED:
        return False
    if prev_state in BLOCKING_STATES:          # held/recovering: core already knows it is bad
        return True
    if prev_state == S.ARRIVED:                # inspected, decision not emitted yet (baseline mode)
        return bool(kit_incomplete)
    return False
