from __future__ import annotations

from dataclasses import dataclass

from isabelle_repair.engine import (
    DeterministicTaskController,
    RuleFirstGenerator,
    ValidationAdapterRegistry,
)
from isabelle_repair.localization import ReplBlockLocalizer, contract_for_block_kind
from isabelle_repair.model import (
    ArtifactKind,
    LocalizedTask,
    RepairBlockCandidate,
    TaskOutcome,
    TaskResult,
    TaskSpec,
    ValidationResult,
    ValidationStatus,
)
from isabelle_repl import IsabelleReplClient


@dataclass
class ReplDeterministicTaskEngine:
    client: IsabelleReplClient
    timeout_ms: int = 30_000
    promote_failed_block_for_review: bool = False

    def __post_init__(self) -> None:
        self._controller = DeterministicTaskController(
            client=self.client,
            generator=RuleFirstGenerator(
                client=self.client,
                timeout_ms=self.timeout_ms,
            ),
            adapters=ValidationAdapterRegistry.default(),
            timeout_ms=self.timeout_ms,
        )

    @staticmethod
    def _fallback_candidates(task_spec: TaskSpec) -> list[RepairBlockCandidate]:
        if task_spec.task.fallback_candidates:
            return list(task_spec.task.fallback_candidates)
        fallback_chain = list(task_spec.task.metadata.get("fallback_chain", []))
        if not fallback_chain:
            fallback_chain = [task_spec.task.block_kind]
        candidates: list[RepairBlockCandidate] = []
        for index, block_kind in enumerate(fallback_chain):
            contract = contract_for_block_kind(block_kind)
            if contract is None:
                continue
            candidates.append(
                RepairBlockCandidate(
                    block_kind=block_kind,
                    block_contract=contract,
                    origin="primary" if index == 0 else "fallback",
                )
            )
        return candidates

    def run(self, task_spec: TaskSpec) -> TaskResult:
        fallback_candidates = self._fallback_candidates(task_spec)
        attempted_candidates: list[str] = []
        trace_parts: list[str] = []
        selected_generator: str | None = None
        validation_count = 0
        aggregate_trace_counts = {"inspect": 0, "propose": 0, "validate": 0}

        def add_trace_counts(result: TaskResult) -> None:
            for key in aggregate_trace_counts:
                aggregate_trace_counts[key] += int(result.trace_counts.get(key, 0))

        for index, candidate in enumerate(fallback_candidates):
            block_kind = candidate.block_kind
            remaining_validations = max(
                task_spec.max_validations - validation_count,
                0,
            )
            effective_task = LocalizedTask(
                task_id=f"{task_spec.task.task_id}-k{index}",
                block_kind=block_kind,
                failure_kind=task_spec.task.failure_kind,
                block_text=task_spec.task.block_text,
                entry_checkpoint=task_spec.task.entry_checkpoint,
                metadata={
                    **task_spec.task.metadata,
                    "fallback_origin": task_spec.task.block_kind,
                    "active_block_kind": block_kind,
                },
            )
            effective_spec = TaskSpec(
                theory_run_id=task_spec.theory_run_id,
                task=effective_task,
                block_contract=candidate.block_contract,
                max_actions=task_spec.max_actions,
                max_validations=remaining_validations,
                timeout_ms=task_spec.timeout_ms,
            )
            result = self._controller.run(effective_spec)
            add_trace_counts(result)
            attempted_candidates.extend(result.attempted_candidates)
            validation_count += len(result.attempted_candidates)
            selected_generator = result.selected_generator or selected_generator
            trace_part = f"{block_kind}:{result.outcome.value}"
            if result.trace_summary:
                trace_part = f"{trace_part}({result.trace_summary})"
            trace_parts.append(trace_part)
            if result.outcome == TaskOutcome.ACCEPTED:
                is_fallback = index > 0 or candidate.origin != "primary"
                localization_confidence = candidate.metadata.get(
                    "localization_confidence",
                    task_spec.task.metadata.get("localization_confidence"),
                )
                return TaskResult(
                    task_id=task_spec.task.task_id,
                    outcome=TaskOutcome.ACCEPTED,
                    artifact_kind=result.artifact_kind,
                    artifact_text=result.artifact_text,
                    requires_rerun=result.requires_rerun,
                    validation=result.validation,
                    trace_summary=" | ".join(trace_parts),
                    trace_counts=dict(aggregate_trace_counts),
                    attempted_candidates=attempted_candidates,
                    selected_generator=selected_generator,
                    selected_block_kind=block_kind,
                    fallback_depth=index if is_fallback else 0,
                    fallback_origin=candidate.origin if is_fallback else None,
                    fallback_target_contract=(
                        candidate.block_contract if is_fallback else None
                    ),
                    localization_confidence=(
                        str(localization_confidence)
                        if is_fallback and localization_confidence is not None
                        else None
                    ),
                )
            if (
                result.validation is not None
                and result.validation.reason == "validation_budget_exhausted"
            ):
                return TaskResult(
                    task_id=task_spec.task.task_id,
                    outcome=TaskOutcome.FAILED,
                    validation=result.validation,
                    trace_summary=" | ".join(trace_parts),
                    trace_counts=dict(aggregate_trace_counts),
                    attempted_candidates=attempted_candidates,
                    selected_generator=selected_generator,
                    selected_block_kind=None,
                    fallback_depth=0,
                    fallback_origin=None,
                    fallback_target_contract=None,
                    localization_confidence=None,
                )

        if self.promote_failed_block_for_review:
            return TaskResult(
                task_id=task_spec.task.task_id,
                outcome=TaskOutcome.ESCALATED,
                artifact_kind=ArtifactKind.REPAIR,
                artifact_text=task_spec.task.block_text,
                validation=ValidationResult(
                    status=ValidationStatus.INCONCLUSIVE,
                    reason="auto_candidates_exhausted_promote_review",
                    details={
                        "candidate_source": "review_fallback",
                        "fallback_chain": [
                            candidate.block_kind for candidate in fallback_candidates
                        ],
                    },
                ),
                trace_summary=" | ".join(trace_parts + ["review_fallback:escalated"]),
                trace_counts=dict(aggregate_trace_counts),
                attempted_candidates=attempted_candidates,
                selected_generator="review_fallback",
                selected_block_kind=None,
                fallback_depth=0,
                fallback_origin=None,
                fallback_target_contract=None,
                localization_confidence=None,
            )

        return TaskResult(
            task_id=task_spec.task.task_id,
            outcome=TaskOutcome.FAILED,
            validation=ValidationResult(
                status=ValidationStatus.FAILED_CONTRACT,
                reason="all_block_kinds_failed",
            ),
            trace_summary=" | ".join(trace_parts),
            trace_counts=dict(aggregate_trace_counts),
            attempted_candidates=attempted_candidates,
            selected_generator=selected_generator or "rule_first",
            selected_block_kind=None,
            fallback_depth=0,
            fallback_origin=None,
            fallback_target_contract=None,
            localization_confidence=None,
        )

    def validate_candidate(
        self,
        task_spec: TaskSpec,
        candidate_text: str,
    ) -> ValidationResult:
        contract = task_spec.block_contract
        if contract is None:
            inferred = contract_for_block_kind(task_spec.task.block_kind)
            if inferred is None:
                return ValidationResult(
                    status=ValidationStatus.FAILED_CONTRACT,
                    reason="unsupported_block_kind",
                )
            contract = inferred
        effective_spec = TaskSpec(
            theory_run_id=task_spec.theory_run_id,
            task=task_spec.task,
            block_contract=contract,
            max_actions=task_spec.max_actions,
            max_validations=task_spec.max_validations,
            timeout_ms=task_spec.timeout_ms,
        )
        return self._controller.validate_candidate(effective_spec, candidate_text)


__all__ = ["ReplBlockLocalizer", "ReplDeterministicTaskEngine"]
