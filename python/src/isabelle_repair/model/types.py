from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RunState(StrEnum):
    ACTIVE = "active"
    AWAITING_REVIEW = "awaiting_review"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FINISHED = "finished"


class RunMode(StrEnum):
    THEORY_WIDE = "theory_wide"
    TARGET_BOUNDARY = "target_boundary"


class ContinuationKind(StrEnum):
    CONTINUE = "continue"
    RERUN_THEN_CONTINUE = "rerun_then_continue"
    STOP = "stop"


class FailureKind(StrEnum):
    PROOF_BODY_FAILURE = "proof_body_failure"
    STATEMENT_FAILURE = "statement_failure"
    NON_PROOF_COMMAND_FAILURE = "non_proof_command_failure"
    THEORY_LOAD_OR_HEADER_FAILURE = "theory_load_or_header_failure"


class ArtifactKind(StrEnum):
    REPAIR = "repair_artifact"
    COMMITTED_PLACEHOLDER = "committed_placeholder_artifact"


class TaskOutcome(StrEnum):
    ACCEPTED = "accepted"
    FAILED = "failed"
    PLACEHOLDER = "placeholder"
    ESCALATED = "escalated"
    ABORTED = "aborted"


class ValidationStatus(StrEnum):
    PASSED = "passed"
    FAILED_EXECUTION = "failed_execution"
    FAILED_CONTRACT = "failed_contract"
    FAILED_TIMEOUT = "failed_timeout"
    INCONCLUSIVE = "inconclusive"


class PolicyDecisionKind(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_REVIEW = "requires_review"


class PolicyDecisionScope(StrEnum):
    ACTION_PERMISSION = "action_permission"
    ARTIFACT_ACCEPTANCE = "artifact_acceptance"
    CONTINUATION_GATING = "continuation_gating"


class HookTriggerSource(StrEnum):
    POLICY_TRIGGERED = "policy_triggered"
    TASK_TRIGGERED = "task_triggered"


class InterventionResponseKind(StrEnum):
    APPROVE_CURRENT_ARTIFACT = "approve_current_artifact"
    REJECT_CURRENT_ARTIFACT = "reject_current_artifact"
    PROVIDE_REPLACEMENT_ARTIFACT = "provide_replacement_artifact"
    REQUEST_COMMITTED_PLACEHOLDER = "request_committed_placeholder"
    REQUEST_STOP = "request_stop"


class RunRecordKind(StrEnum):
    RUN_METADATA = "run_metadata"
    TASK = "task"
    ARTIFACT = "artifact"
    POLICY = "policy_decision"
    INTERVENTION = "intervention"
    CONTINUATION = "continuation"
    PROVENANCE = "provenance_link"
    TERMINAL = "terminal"


class BlockContract(StrEnum):
    GOAL_CLOSED = "goal_closed"
    SUBPROOF_CLOSED = "subproof_closed"
    THEOREM_CLOSED = "theorem_closed"
    CONTEXT_UPDATED = "context_updated"


@dataclass(frozen=True)
class RepairBlockCandidate:
    block_kind: str
    block_contract: BlockContract
    origin: str = "primary"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalizedTask:
    task_id: str
    block_kind: str
    failure_kind: FailureKind
    block_text: str
    entry_checkpoint: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    fallback_candidates: list[RepairBlockCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class TaskSpec:
    theory_run_id: str
    task: LocalizedTask
    block_contract: BlockContract
    max_actions: int = 20
    max_validations: int = 10
    timeout_ms: int = 30_000


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    task_id: str
    outcome: TaskOutcome
    artifact_kind: ArtifactKind | None = None
    artifact_text: str | None = None
    requires_rerun: bool = False
    validation: ValidationResult | None = None
    trace_summary: str = ""
    trace_counts: dict[str, int] = field(default_factory=dict)
    attempted_candidates: list[str] = field(default_factory=list)
    selected_generator: str | None = None
    selected_block_kind: str | None = None
    fallback_depth: int = 0
    fallback_origin: str | None = None
    fallback_target_contract: BlockContract | None = None
    localization_confidence: str | None = None


@dataclass(frozen=True)
class PolicyContext:
    theory_run_id: str
    task_id: str
    failure_kind: FailureKind
    block_kind: str
    artifact_kind: ArtifactKind | None
    reason_code: str | None = None
    is_placeholder_request: bool = False
    fallback_depth: int = 0
    fallback_origin: str | None = None
    localization_confidence: str | None = None
    continuation_kind: ContinuationKind | None = None


@dataclass(frozen=True)
class PolicyDecision:
    kind: PolicyDecisionKind
    scope: PolicyDecisionScope
    triggered_rule_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InterventionContext:
    trigger_source: HookTriggerSource
    reason_code: str
    task_id: str
    current_artifact_text: str | None
    current_artifact_kind: ArtifactKind | None
    policy_decision: PolicyDecision | None
    validation: ValidationResult | None
    allowed_response_kinds: list[InterventionResponseKind]
    invalid_response_reason: str | None = None


@dataclass(frozen=True)
class InterventionResponse:
    kind: InterventionResponseKind
    replacement_artifact_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PendingReview:
    task_spec: TaskSpec
    task_result: TaskResult
    context: InterventionContext


@dataclass(frozen=True)
class ContinuationSelection:
    kind: ContinuationKind
    reason: str


@dataclass(frozen=True)
class RunRecord:
    schema_version: str
    record_id: str
    theory_run_id: str
    timestamp: str
    run_local_sequence_number: int
    task_id: str | None
    record_kind: RunRecordKind
    payload: dict[str, Any]

    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()
