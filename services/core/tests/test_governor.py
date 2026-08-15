from shared.schemas import ActionProposal, WorldState
from services.core import governor as G


def world(**kw):
    base = dict(kit_id="kit_04", kit_in_inspection_zone=True, workspace_clear=True, detection_confidence=0.97,
                detected={"red_body": 1, "black_wheel": 1, "blue_roof": 1}, missing={"black_wheel": 1}, extra={},
                retry_count=0, estop_available=True, robot_state="idle")
    base.update(kw)
    return WorldState(**base)


def add_wheel(**kw):
    p = dict(action="ADD_PART", kit_id="kit_04", part="black_wheel", quantity=1, source_bin="wheel_bin",
             target_zone="inspection_zone", rationale="one wheel missing")
    p.update(kw)
    return ActionProposal(**p)


def test_happy_path_allowed():
    d = G.validate(add_wheel(), world())
    assert d.allowed, d.reasons


def test_blocks_when_workspace_not_clear():
    d = G.validate(add_wheel(), world(workspace_clear=False))
    assert not d.allowed and any("workspace" in r for r in d.reasons)


def test_blocks_low_confidence():
    assert not G.validate(add_wheel(), world(detection_confidence=0.5)).allowed


def test_blocks_wrong_bin_and_quantity():
    assert not G.validate(add_wheel(source_bin="body_bin"), world()).allowed
    assert not G.validate(add_wheel(quantity=2), world()).allowed


def test_blocks_part_not_missing():
    assert not G.validate(add_wheel(part="blue_roof", source_bin="roof_bin"), world()).allowed


def test_blocks_extra_parts():
    assert not G.validate(add_wheel(), world(extra={"blue_roof": 1})).allowed


def test_blocks_retry_limit_and_busy_robot():
    assert not G.validate(add_wheel(), world(retry_count=5)).allowed
    assert not G.validate(add_wheel(), world(robot_state="moving")).allowed


def test_release_requires_complete_kit():
    rel = ActionProposal(action="RELEASE", kit_id="kit_04", rationale="x")
    assert not G.validate(rel, world()).allowed
    assert G.validate(rel, world(missing={}, detected={"red_body": 1, "black_wheel": 2, "blue_roof": 1})).allowed


def test_rule_planner():
    assert G.rule_planner(world()).action == "ADD_PART"
    assert G.rule_planner(world(missing={"black_wheel": 2})).action == "HOLD_FOR_HUMAN"
    assert G.rule_planner(world(missing={}, extra={})).action == "RELEASE"
