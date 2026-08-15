"""Deterministic safety governor (Section 5.2). Pure function, no I/O, unit-tested.

The LLM proposes. This decides. Nothing else may call the robot service.
"""
from __future__ import annotations

import os

from shared.schemas import (
    INSPECTION_ZONE, PART_TO_BIN, REQUIRED_PARTS,
    ActionProposal, GovernorDecision, WorldState,
)

APPROVED_ACTIONS = {"ADD_PART", "HOLD_FOR_HUMAN", "RELEASE"}
MAX_QUANTITY = 1
CONF_THRESHOLD = float(os.environ.get("GOV_CONF_THRESHOLD", "0.85"))
MAX_RETRIES = int(os.environ.get("GOV_MAX_RETRIES", "1"))


def validate(p: ActionProposal, w: WorldState) -> GovernorDecision:
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    def check(name: str, ok: bool, why: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            reasons.append(why)

    check("kit_matches", p.kit_id == w.kit_id, "proposal is for a different kit than the world state")
    check("action_approved", p.action in APPROVED_ACTIONS, f"action {p.action} is not in the approved list")

    if p.action == "RELEASE":
        check("kit_complete", not w.missing and not w.extra, "cannot release: kit is not complete")
        check("confidence", w.detection_confidence >= CONF_THRESHOLD, "confidence below threshold for release")
        return GovernorDecision(allowed=all(checks.values()), checks=checks, reasons=reasons)

    if p.action == "HOLD_FOR_HUMAN":
        return GovernorDecision(allowed=True, checks=checks, reasons=reasons)

    # ---- ADD_PART -------------------------------------------------------------
    check("part_supported", p.part in REQUIRED_PARTS, f"unsupported part {p.part}")
    check("quantity_ok", 0 < p.quantity <= MAX_QUANTITY, f"quantity {p.quantity} exceeds max {MAX_QUANTITY}")
    check("part_actually_missing", bool(p.part) and w.missing.get(p.part or "", 0) >= max(p.quantity, 1),
          "proposed part is not missing according to detection")
    check("no_extra_parts", not w.extra, "kit has extra/incorrect parts; automatic recovery disabled (manual review)")
    check("bin_known", bool(p.part) and p.source_bin == PART_TO_BIN.get(p.part or ""),
          f"source bin {p.source_bin} is not the known bin for {p.part}")
    check("target_zone", p.target_zone == INSPECTION_ZONE, "target must be the inspection zone")
    check("kit_in_zone", w.kit_in_inspection_zone, "kit is not inside the inspection zone")
    check("workspace_clear", w.workspace_clear, "robot workspace is not clear")
    check("confidence", w.detection_confidence >= CONF_THRESHOLD,
          f"detection confidence {w.detection_confidence:.2f} < {CONF_THRESHOLD}")
    check("estop", w.estop_available, "emergency stop not available")
    check("retry_limit", w.retry_count <= MAX_RETRIES, f"retry limit exceeded ({w.retry_count} > {MAX_RETRIES})")
    check("robot_idle", w.robot_state in ("idle", "done"), f"robot is {w.robot_state}")

    return GovernorDecision(allowed=all(checks.values()), checks=checks, reasons=reasons)


def rule_planner(w: WorldState) -> ActionProposal:
    """Deterministic fallback planner (used if the LLM is down or times out)."""
    if not w.missing and not w.extra:
        return ActionProposal(action="RELEASE", kit_id=w.kit_id, rationale="kit complete", proposed_by="rule")
    if w.extra or len(w.missing) != 1 or list(w.missing.values())[0] != 1:
        return ActionProposal(action="HOLD_FOR_HUMAN", kit_id=w.kit_id,
                              rationale="extra parts or more than one missing part; outside supported recovery",
                              proposed_by="rule")
    part = next(iter(w.missing))
    return ActionProposal(action="ADD_PART", kit_id=w.kit_id, part=part, quantity=1,  # type: ignore[arg-type]
                          source_bin=PART_TO_BIN[part], target_zone=INSPECTION_ZONE,
                          rationale=f"exactly one {part} missing", proposed_by="rule")
