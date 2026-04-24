from __future__ import annotations

from isabelle_repair.model import BlockContract

TERMINAL_PROOF_STEP_BLOCK = "TerminalProofStepBlock"
WHOLE_PROOF_BODY_BLOCK = "WholeProofBodyBlock"
THEOREM_SHELL_BLOCK = "TheoremShellBlock"
TOP_LEVEL_COMMAND_BLOCK = "TopLevelCommandBlock"


def contract_for_block_kind(block_kind: str) -> BlockContract | None:
    if block_kind == TERMINAL_PROOF_STEP_BLOCK:
        return BlockContract.GOAL_CLOSED
    if block_kind == WHOLE_PROOF_BODY_BLOCK:
        return BlockContract.SUBPROOF_CLOSED
    if block_kind == THEOREM_SHELL_BLOCK:
        return BlockContract.THEOREM_CLOSED
    if block_kind == TOP_LEVEL_COMMAND_BLOCK:
        return BlockContract.CONTEXT_UPDATED
    return None
