import pytest
from shared.schemas import EventType as E, KitState as S
from services.core.state_machine import IllegalTransition, is_escape, next_state


def test_happy_recovery_path():
    s = S.PREPARING
    for ev, expected in [(E.KIT_SENT, S.SENT), (E.KIT_ARRIVED, S.ARRIVED), (E.KIT_INSPECTED, S.ARRIVED),
                         (E.KIT_HELD, S.HELD), (E.RECOVERY_PROPOSED, S.RECOVERY_PROPOSED),
                         (E.RECOVERY_APPROVED, S.RECOVERING), (E.RECOVERY_EXECUTED, S.REVERIFYING),
                         (E.KIT_INSPECTED, S.REVERIFYING), (E.RECOVERY_VERIFIED, S.HELD), (E.KIT_RELEASED, S.RELEASED),
                         (E.KIT_RECEIVED, S.AT_ASSEMBLY), (E.CAR_DONE, S.ASSEMBLED), (E.QC_APPROVED, S.QC_PASS)]:
        s = next_state(s, ev)
        assert s == expected


def test_escape_detection():
    assert is_escape(S.HELD, E.KIT_RECEIVED)
    assert not is_escape(S.RELEASED, E.KIT_RECEIVED)


def test_illegal():
    with pytest.raises(IllegalTransition):
        next_state(S.QC_PASS, E.KIT_ARRIVED)
