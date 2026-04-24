from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from isabelle_repair.hooks import StaticReviewHook
from isabelle_repair.model import (
    ArtifactKind,
    BlockContract,
    FailureKind,
    InterventionContext,
    InterventionResponse,
    InterventionResponseKind,
    LocalizedTask,
    RepairBlockCandidate,
    TaskOutcome,
    TaskResult,
    TaskSpec,
    ValidationResult,
    ValidationStatus,
)
from isabelle_repair.policy import RuleBasedPolicyGate
from isabelle_repair.policy.config import (
    PlaceholderPolicyConfig,
    PlaceholderPolicyMode,
    PolicyConfig,
)


@dataclass
class QueueLocalizer:
    """Test-only localizer that yields a fixed task queue."""

    tasks: list[LocalizedTask] = field(default_factory=list)

    def next_task(
        self,
        theory_run_id: str,  # noqa: ARG002
        snapshot=None,  # noqa: ANN001, ARG002
    ) -> LocalizedTask | None:
        if not self.tasks:
            return None
        return self.tasks.pop(0)


@dataclass
class RuleBasedTaskEngine:
    """Deterministic test-only engine for repair orchestrator suites."""

    outcomes_by_task_id: dict[str, TaskResult] = field(default_factory=dict)
    default_outcome: TaskResult = field(
        default_factory=lambda: TaskResult(
            task_id="default-task",
            outcome=TaskOutcome.FAILED,
            validation=ValidationResult(
                status=ValidationStatus.FAILED_CONTRACT,
                reason="no_result_configured",
            ),
        )
    )
    replacement_accept_prefix: str = "by "

    def run(self, task_spec: TaskSpec) -> TaskResult:
        configured = self.outcomes_by_task_id.get(task_spec.task.task_id)
        if configured is None:
            configured = self.default_outcome
        return TaskResult(
            task_id=task_spec.task.task_id,
            outcome=configured.outcome,
            artifact_kind=configured.artifact_kind,
            artifact_text=configured.artifact_text,
            requires_rerun=configured.requires_rerun,
            validation=configured.validation,
            trace_summary=configured.trace_summary,
            trace_counts=dict(configured.trace_counts),
            attempted_candidates=list(configured.attempted_candidates),
            selected_generator=configured.selected_generator,
            selected_block_kind=configured.selected_block_kind,
            fallback_depth=configured.fallback_depth,
            fallback_origin=configured.fallback_origin,
            fallback_target_contract=configured.fallback_target_contract,
            localization_confidence=configured.localization_confidence,
        )

    def validate_candidate(
        self,
        task_spec: TaskSpec,  # noqa: ARG002
        candidate_text: str,
    ) -> ValidationResult:
        if candidate_text.strip().startswith(self.replacement_accept_prefix):
            return ValidationResult(status=ValidationStatus.PASSED)
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="replacement_candidate_rejected",
        )

    @staticmethod
    def accepted_repair(
        task_id: str,
        text: str,
        requires_rerun: bool = False,
        selected_block_kind: str | None = None,
        fallback_depth: int = 0,
        fallback_origin: str | None = None,
        fallback_target_contract: BlockContract | None = None,
        localization_confidence: str | None = None,
    ) -> TaskResult:
        return TaskResult(
            task_id=task_id,
            outcome=TaskOutcome.ACCEPTED,
            artifact_kind=ArtifactKind.REPAIR,
            artifact_text=text,
            requires_rerun=requires_rerun,
            validation=ValidationResult(status=ValidationStatus.PASSED),
            selected_block_kind=selected_block_kind,
            fallback_depth=fallback_depth,
            fallback_origin=fallback_origin,
            fallback_target_contract=fallback_target_contract,
            localization_confidence=localization_confidence,
        )


def make_localized_task(
    task_id: str,
    *,
    block_kind: str = "TerminalProofStepBlock",
    failure_kind: FailureKind = FailureKind.PROOF_BODY_FAILURE,
    block_text: str = "by simp",
    fallback_candidates: list[RepairBlockCandidate] | None = None,
    metadata: dict[str, Any] | None = None,
) -> LocalizedTask:
    return LocalizedTask(
        task_id=task_id,
        block_kind=block_kind,
        failure_kind=failure_kind,
        block_text=block_text,
        fallback_candidates=list(fallback_candidates or []),
        metadata={"line": 1, **(metadata or {})},
    )


def make_localizer(tasks: list[LocalizedTask]) -> QueueLocalizer:
    return QueueLocalizer(tasks=list(tasks))


def make_engine(outcomes_by_task_id):
    return RuleBasedTaskEngine(outcomes_by_task_id=outcomes_by_task_id)


def make_policy(*, allow_placeholders: bool = True) -> RuleBasedPolicyGate:
    mode = (
        PlaceholderPolicyMode.ALLOW
        if allow_placeholders
        else PlaceholderPolicyMode.DENY
    )
    return RuleBasedPolicyGate(
        config=PolicyConfig(placeholder=PlaceholderPolicyConfig(mode=mode))
    )


@dataclass
class SequencedHook:
    responses: list[InterventionResponse] = field(default_factory=list)

    def handle(self, context: InterventionContext) -> InterventionResponse:  # noqa: ARG002
        if not self.responses:
            return InterventionResponse(
                kind=InterventionResponseKind.REJECT_CURRENT_ARTIFACT
            )
        return self.responses.pop(0)


def make_static_hook(kind: InterventionResponseKind) -> StaticReviewHook:
    return StaticReviewHook(response_factory=InterventionResponse(kind=kind))
