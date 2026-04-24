from __future__ import annotations

from dataclasses import dataclass

from isabelle_repair.localization import contract_for_block_kind
from isabelle_repair.model import (
    ArtifactKind,
    BlockContract,
    TaskOutcome,
    TaskResult,
    TaskSpec,
    ValidationResult,
    ValidationStatus,
)
from isabelle_repl import IsabelleReplClient

from .adapters import ValidationAdapterRegistry, ValidationContext
from .candidate_source import (
    AutoCandidateSource,
    CandidateSource,
    ReviewCandidateSource,
)
from .generator import RuleFirstGenerator


@dataclass
class DeterministicTaskController:
    client: IsabelleReplClient
    generator: RuleFirstGenerator
    adapters: ValidationAdapterRegistry
    timeout_ms: int = 30_000

    def run(self, task_spec: TaskSpec) -> TaskResult:
        candidate_source = AutoCandidateSource(
            generator=self.generator,
            allow_sledgehammer=bool(
                task_spec.task.metadata.get("allow_sledgehammer", True)
            ),
        )
        return self.run_with_source(task_spec, candidate_source)

    def run_with_source(
        self,
        task_spec: TaskSpec,
        candidate_source: CandidateSource,
    ) -> TaskResult:
        source_state_id = str(task_spec.task.metadata.get("source_state_id", ""))
        if not source_state_id:
            return TaskResult(
                task_id=task_spec.task.task_id,
                outcome=TaskOutcome.FAILED,
                validation=ValidationResult(
                    status=ValidationStatus.FAILED_CONTRACT,
                    reason="missing_source_state",
                ),
                trace_summary=(
                    "inspect=0 propose=0 validate=0 reason=missing_source_state"
                ),
                trace_counts={"inspect": 0, "propose": 0, "validate": 0},
            )

        inspect_count = 1
        propose_count = 0
        validate_count = 0
        attempted_candidates: list[str] = []

        source_metadata = candidate_source.source_metadata(task_spec)
        candidates = candidate_source.candidates(task_spec)
        if not candidates:
            return TaskResult(
                task_id=task_spec.task.task_id,
                outcome=TaskOutcome.FAILED,
                validation=ValidationResult(
                    status=ValidationStatus.FAILED_CONTRACT,
                    reason="no_candidate_generated",
                ),
                attempted_candidates=[],
                selected_generator=candidate_source.source_name,
                trace_summary=(
                    f"inspect={inspect_count} propose={propose_count} "
                    f"validate={validate_count} reason=no_candidate_generated "
                    f"source={candidate_source.source_name}"
                ),
                trace_counts={
                    "inspect": inspect_count,
                    "propose": propose_count,
                    "validate": validate_count,
                },
            )

        entry_mode = str(task_spec.task.entry_checkpoint.get("mode", ""))
        entry_proof_level = int(task_spec.task.entry_checkpoint.get("proof_level", 0))
        for candidate in candidates:
            if validate_count >= task_spec.max_validations:
                return TaskResult(
                    task_id=task_spec.task.task_id,
                    outcome=TaskOutcome.FAILED,
                    validation=self._annotate_validation(
                        ValidationResult(
                            status=ValidationStatus.INCONCLUSIVE,
                            reason="validation_budget_exhausted",
                        ),
                        source_name=candidate_source.source_name,
                        source_metadata=source_metadata,
                    ),
                    attempted_candidates=attempted_candidates,
                    selected_generator=candidate_source.source_name,
                    trace_summary=(
                        f"inspect={inspect_count} propose={propose_count} "
                        f"validate={validate_count} "
                        f"reason=validation_budget_exhausted "
                        f"source={candidate_source.source_name}"
                    ),
                    trace_counts={
                        "inspect": inspect_count,
                        "propose": propose_count,
                        "validate": validate_count,
                    },
                )
            propose_count += 1
            attempted_candidates.append(candidate)
            execution = self.client.execute(
                source_state_id=source_state_id,
                tactic=candidate,
                timeout_ms=self.timeout_ms,
                include_text=True,
            )
            validate_count += 1
            validation = self._validate_execution(
                task_spec=task_spec,
                execution_status=execution.status,
                execution_error=execution.error_msg,
                block_kind=task_spec.task.block_kind,
                block_contract=task_spec.block_contract,
                entry_mode=entry_mode,
                entry_proof_level=entry_proof_level,
                execution_result=execution,
            )
            validation = self._annotate_validation(
                validation,
                source_name=candidate_source.source_name,
                candidate_text=candidate,
                source_metadata=source_metadata,
            )
            if validation.status == ValidationStatus.PASSED:
                return TaskResult(
                    task_id=task_spec.task.task_id,
                    outcome=TaskOutcome.ACCEPTED,
                    artifact_kind=ArtifactKind.REPAIR,
                    artifact_text=candidate,
                    validation=validation,
                    attempted_candidates=attempted_candidates,
                    selected_generator=candidate_source.source_name,
                    trace_summary=(
                        f"inspect={inspect_count} propose={propose_count} "
                        f"validate={validate_count} selected={candidate} "
                        f"source={candidate_source.source_name}"
                    ),
                    trace_counts={
                        "inspect": inspect_count,
                        "propose": propose_count,
                        "validate": validate_count,
                    },
                )

        return TaskResult(
            task_id=task_spec.task.task_id,
            outcome=TaskOutcome.FAILED,
            validation=self._annotate_validation(
                ValidationResult(
                    status=ValidationStatus.FAILED_CONTRACT,
                    reason="all_candidates_rejected",
                ),
                source_name=candidate_source.source_name,
                source_metadata=source_metadata,
            ),
            attempted_candidates=attempted_candidates,
            selected_generator=candidate_source.source_name,
            trace_summary=(
                f"inspect={inspect_count} propose={propose_count} "
                f"validate={validate_count} reason=all_candidates_rejected "
                f"source={candidate_source.source_name}"
            ),
            trace_counts={
                "inspect": inspect_count,
                "propose": propose_count,
                "validate": validate_count,
            },
        )

    def validate_candidate(
        self,
        task_spec: TaskSpec,
        candidate_text: str,
    ) -> ValidationResult:
        result = self.run_with_source(
            task_spec,
            ReviewCandidateSource(candidate_text=candidate_text),
        )
        if result.validation is None:
            return ValidationResult(
                status=ValidationStatus.FAILED_CONTRACT,
                reason="missing_validation_result",
            )
        return result.validation

    def _validate_execution(
        self,
        *,
        task_spec: TaskSpec,  # noqa: ARG002
        execution_status: str,
        execution_error: str,
        block_kind: str,
        block_contract: BlockContract,
        entry_mode: str,
        entry_proof_level: int,
        execution_result,
    ) -> ValidationResult:
        if execution_status == "TIMEOUT":
            return ValidationResult(
                status=ValidationStatus.FAILED_TIMEOUT,
                reason=execution_error or "timeout",
            )
        if execution_status not in ("SUCCESS", "PROOF_COMPLETE"):
            return ValidationResult(
                status=ValidationStatus.FAILED_EXECUTION,
                reason=execution_error or "execution_failed",
            )
        return self.adapters.validate(
            ValidationContext(
                block_kind=block_kind,
                block_contract=block_contract,
                entry_mode=entry_mode,
                entry_proof_level=entry_proof_level,
                execution_result=execution_result,
            )
        )

    @staticmethod
    def _annotate_validation(
        validation: ValidationResult,
        *,
        source_name: str,
        candidate_text: str | None = None,
        source_metadata: dict[str, object] | None = None,
    ) -> ValidationResult:
        details = dict(validation.details)
        details["candidate_source"] = source_name
        if candidate_text is not None:
            details["candidate_text"] = candidate_text
        if source_metadata:
            details["candidate_source_metadata"] = dict(source_metadata)
        return ValidationResult(
            status=validation.status,
            reason=validation.reason,
            details=details,
        )


def resolve_block_contract(task_spec: TaskSpec) -> BlockContract:
    contract = contract_for_block_kind(task_spec.task.block_kind)
    if contract is None:
        return task_spec.block_contract
    return contract
