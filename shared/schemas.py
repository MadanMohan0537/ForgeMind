"""ForgeMind shared contracts.

Every service imports from here. If you change a schema, change it here and
grep for usages. Freeze these in the first 30 minutes and stop touching them.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Product spec (Section 3.1 of the project doc)
# --------------------------------------------------------------------------- #
PartName = Literal["red_body", "black_wheel", "blue_roof"]
REQUIRED_PARTS: dict[str, int] = {"red_body": 1, "black_wheel": 2, "blue_roof": 1}
PART_TO_BIN: dict[str, str] = {
    "red_body": "body_bin",
    "black_wheel": "wheel_bin",
    "blue_roof": "roof_bin",
}
INSPECTION_ZONE = "inspection_zone"


# --------------------------------------------------------------------------- #
# Events (the single source of truth; metrics are computed only from these)
# --------------------------------------------------------------------------- #
class EventType(str, Enum):
    # runs
    RUN_STARTED = "RUN_STARTED"
    RUN_ENDED = "RUN_ENDED"
    # kit lifecycle (station buttons + perception)
    KIT_STARTED = "KIT_STARTED"            # Alice taps "Start kit"
    KIT_SENT = "KIT_SENT"                  # Alice taps "Sent to inspection"
    KIT_ARRIVED = "KIT_ARRIVED"            # perception: something entered inspection zone and went still
    KIT_INSPECTED = "KIT_INSPECTED"        # perception: counted parts (payload: detected/missing/extra/confidence)
    KIT_HELD = "KIT_HELD"                  # core: kit blocked from moving to assembly
    KIT_RELEASED = "KIT_RELEASED"          # core: kit cleared for assembly
    KIT_RECEIVED = "KIT_RECEIVED"          # Bob taps "Received"
    CAR_DONE = "CAR_DONE"                  # Bob taps "Car done"
    QC_APPROVED = "QC_APPROVED"            # Charlie taps "Approve"
    QC_REJECTED = "QC_REJECTED"            # Charlie taps "Reject"
    # recovery loop
    RECOVERY_PROPOSED = "RECOVERY_PROPOSED"   # planner (LLM or rule) proposed an action
    RECOVERY_APPROVED = "RECOVERY_APPROVED"   # governor allowed it
    RECOVERY_DENIED = "RECOVERY_DENIED"       # governor blocked it (payload: reasons)
    RECOVERY_EXECUTED = "RECOVERY_EXECUTED"   # robot service says the routine finished
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"   # perception re-inspection confirms complete kit
    RECOVERY_FAILED = "RECOVERY_FAILED"       # re-inspection still incomplete
    HUMAN_REVIEW_REQUESTED = "HUMAN_REVIEW_REQUESTED"
    HUMAN_RESOLVED = "HUMAN_RESOLVED"         # payload may include rework_seconds
    # perception telemetry
    QUEUE_MEASURED = "QUEUE_MEASURED"         # payload: zone, count
    ZONE_STATUS = "ZONE_STATUS"               # payload: workspace_clear, fps ...
    VLM_VERIFICATION = "VLM_VERIFICATION"     # second-opinion result from Cosmos/VSS
    # analysis
    HYPOTHESES_GENERATED = "HYPOTHESES_GENERATED"
    EXPERIMENT_PROPOSED = "EXPERIMENT_PROPOSED"
    HYPOTHESIS_VERIFIED = "HYPOTHESIS_VERIFIED"
    # containment
    POLICY_DENIED = "POLICY_DENIED"           # OpenShell / sandbox blocked an agent action
    ROBOT_ERROR = "ROBOT_ERROR"


class Event(BaseModel):
    id: Optional[int] = None                 # assigned by core
    run_id: str
    ts: float = Field(default_factory=time.time)
    event: EventType
    kit_id: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    evidence_path: Optional[str] = None      # jpg or mp4 under runs/evidence
    source: str = "system"                   # perception|station|core|governor|robot|agent|vlm|replay


# --------------------------------------------------------------------------- #
# Kit state machine
# --------------------------------------------------------------------------- #
class KitState(str, Enum):
    PREPARING = "PREPARING"
    SENT = "SENT"
    ARRIVED = "ARRIVED"
    HELD = "HELD"
    RECOVERY_PROPOSED = "RECOVERY_PROPOSED"
    RECOVERING = "RECOVERING"          # robot/human actuator working
    REVERIFYING = "REVERIFYING"        # waiting for perception to re-inspect
    HUMAN_REVIEW = "HUMAN_REVIEW"
    RELEASED = "RELEASED"
    AT_ASSEMBLY = "AT_ASSEMBLY"
    ASSEMBLED = "ASSEMBLED"
    QC_PASS = "QC_PASS"
    QC_FAIL = "QC_FAIL"


class Kit(BaseModel):
    kit_id: str
    run_id: str
    state: KitState = KitState.PREPARING
    detected: dict[str, int] = Field(default_factory=dict)
    missing: dict[str, int] = Field(default_factory=dict)
    extra: dict[str, int] = Field(default_factory=dict)
    confidence: float = 0.0
    retry_count: int = 0
    perception_token: Optional[str] = None   # perception's local id for the physical presence
    started_ts: Optional[float] = None
    finished_ts: Optional[float] = None
    last_event: Optional[str] = None


# --------------------------------------------------------------------------- #
# Planner -> Governor -> Robot
# --------------------------------------------------------------------------- #
ActionName = Literal["ADD_PART", "HOLD_FOR_HUMAN", "RELEASE"]


class ActionProposal(BaseModel):
    """What the planner (LLM or rule) proposes. Never executed directly."""
    action: ActionName
    kit_id: str
    part: Optional[PartName] = None
    quantity: int = 0
    source_bin: Optional[str] = None
    target_zone: str = INSPECTION_ZONE
    rationale: str = ""
    proposed_by: str = "rule"               # "llm:<model>" or "rule"


class WorldState(BaseModel):
    """Everything the governor is allowed to look at. Filled by core from events."""
    kit_id: str
    kit_in_inspection_zone: bool
    workspace_clear: bool
    detection_confidence: float
    detected: dict[str, int]
    missing: dict[str, int]
    extra: dict[str, int]
    retry_count: int
    estop_available: bool = True
    robot_state: str = "idle"


class GovernorDecision(BaseModel):
    allowed: bool
    checks: dict[str, bool]
    reasons: list[str] = Field(default_factory=list)


class RobotRequest(BaseModel):
    kit_id: str
    part: PartName
    quantity: int = 1
    source_bin: str
    target_zone: str = INSPECTION_ZONE
    action_id: Optional[str] = None
    run_id: Optional[str] = None             # so the robot service can post events for the right run


class RobotStatus(BaseModel):
    state: Literal["idle", "moving", "waiting_human", "done", "error", "estopped"]
    adapter: str
    instruction: Optional[str] = None
    last_action: Optional[dict] = None
    action_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# Analyst / Planner / Verifier (LLM structured outputs)
# --------------------------------------------------------------------------- #
class Hypothesis(BaseModel):
    id: str = Field(description="short id like H1")
    title: str
    explanation: str = Field(description="plain language, one or two sentences")
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_event_ids: list[int] = Field(default_factory=list)
    contradicting_event_ids: list[int] = Field(default_factory=list)
    status: Literal["active", "supported", "rejected"] = "active"


class HypothesisSet(BaseModel):
    run_id: str
    summary: str
    hypotheses: list[Hypothesis]


class ExperimentPlan(BaseModel):
    change: str
    keep_unchanged: list[str]
    reason: str
    tests_hypothesis_id: str
    expected_observation: str
    metric_to_watch: str


class VerificationVerdict(BaseModel):
    hypothesis_id: str
    verdict: Literal["supported", "weakened", "inconclusive"]
    explanation: str
    before_value: Optional[float] = None
    after_value: Optional[float] = None


class RunMetrics(BaseModel):
    run_id: str
    duration_seconds: float = 0
    kits_started: int = 0
    kits_inspected: int = 0
    correct_products: int = 0
    rejected_products: int = 0
    unfinished_products: int = 0
    incomplete_kits_detected: int = 0
    escapes: int = 0
    escape_rate: Optional[float] = None
    recovery_attempts: int = 0
    verified_recoveries: int = 0
    recovery_success_rate: Optional[float] = None
    human_reviews: int = 0
    avg_cycle_seconds: Optional[float] = None
    assembly_idle_seconds: float = 0
    rework_seconds: float = 0
    max_queue: int = 0
    throughput_per_min: Optional[float] = None
    defect_rate: Optional[float] = None
    missing_part_histogram: dict[str, int] = Field(default_factory=dict)
    policy_denials: int = 0
