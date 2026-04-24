from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from isabelle_repair.localization import (
    TERMINAL_PROOF_STEP_BLOCK,
    THEOREM_SHELL_BLOCK,
    TOP_LEVEL_COMMAND_BLOCK,
    WHOLE_PROOF_BODY_BLOCK,
)
from isabelle_repair.model import BlockContract, ValidationResult, ValidationStatus
from isabelle_repl.client import StateResult


@dataclass(frozen=True)
class ValidationContext:
    block_kind: str
    block_contract: BlockContract
    entry_mode: str
    entry_proof_level: int
    execution_result: StateResult


class ValidationAdapter(Protocol):
    def validate(self, context: ValidationContext) -> ValidationResult: ...


class TerminalProofStepAdapter:
    """Contract: goal_closed."""

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = context.execution_result
        goal_closed = result.proof_is_finished() or (
            result.is_success() and result.proof_level < context.entry_proof_level
        )
        if goal_closed:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                details={"contract": context.block_contract.value},
            )
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="goal_not_closed",
            details={"contract": context.block_contract.value},
        )


class WholeProofBodyAdapter:
    """Contract: subproof_closed."""

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = context.execution_result
        subproof_closed = result.is_success() and (
            result.proof_level < context.entry_proof_level
        )
        if subproof_closed:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                details={"contract": context.block_contract.value},
            )
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="subproof_not_closed",
            details={"contract": context.block_contract.value},
        )


class TheoremShellAdapter:
    """Contract: theorem_closed."""

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = context.execution_result
        theorem_closed = (
            result.proof_is_finished()
            and result.proof_level == 0
            and result.mode != "PROOF"
        )
        if theorem_closed:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                details={"contract": context.block_contract.value},
            )
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="theorem_not_closed",
            details={"contract": context.block_contract.value},
        )


class TopLevelCommandAdapter:
    """Contract: context_updated."""

    def validate(self, context: ValidationContext) -> ValidationResult:
        result = context.execution_result
        context_restored = (
            result.is_success() and result.mode != "PROOF" and result.proof_level == 0
        )
        if context_restored:
            return ValidationResult(
                status=ValidationStatus.PASSED,
                details={"contract": context.block_contract.value},
            )
        return ValidationResult(
            status=ValidationStatus.FAILED_CONTRACT,
            reason="theory_context_not_restored",
            details={"contract": context.block_contract.value},
        )


@dataclass
class ValidationAdapterRegistry:
    adapters: dict[str, ValidationAdapter]

    @classmethod
    def default(cls) -> ValidationAdapterRegistry:
        return cls(
            adapters={
                TERMINAL_PROOF_STEP_BLOCK: TerminalProofStepAdapter(),
                WHOLE_PROOF_BODY_BLOCK: WholeProofBodyAdapter(),
                THEOREM_SHELL_BLOCK: TheoremShellAdapter(),
                TOP_LEVEL_COMMAND_BLOCK: TopLevelCommandAdapter(),
            }
        )

    def validate(self, context: ValidationContext) -> ValidationResult:
        adapter = self.adapters.get(context.block_kind)
        if adapter is None:
            return ValidationResult(
                status=ValidationStatus.FAILED_CONTRACT,
                reason="unsupported_block_kind",
                details={"block_kind": context.block_kind},
            )
        return adapter.validate(context)
