from __future__ import annotations

from dataclasses import dataclass

from isabelle_repair.localization import (
    TERMINAL_PROOF_STEP_BLOCK,
    THEOREM_SHELL_BLOCK,
    TOP_LEVEL_COMMAND_BLOCK,
    WHOLE_PROOF_BODY_BLOCK,
)
from isabelle_repair.model import TaskSpec
from isabelle_repl import IsabelleReplClient


@dataclass
class RuleFirstGenerator:
    client: IsabelleReplClient
    timeout_ms: int = 30_000

    def generate_candidates(
        self,
        task_spec: TaskSpec,
        *,
        allow_sledgehammer: bool = True,
    ) -> list[str]:
        block_kind = task_spec.task.block_kind
        rules = self._rules_for_block(block_kind)
        if rules:
            return rules

        if block_kind == TOP_LEVEL_COMMAND_BLOCK:
            return []

        if not allow_sledgehammer:
            return []
        source_state_id = str(task_spec.task.metadata.get("source_state_id", ""))
        if not source_state_id:
            return []
        found, tactic, _ = self.client.run_sledgehammer(
            source_state_id=source_state_id,
            timeout_ms=self.timeout_ms,
            sledgehammer_timeout_ms=self.timeout_ms,
        )
        return [tactic] if found and tactic else []

    def _rules_for_block(self, block_kind: str) -> list[str]:
        if block_kind == TERMINAL_PROOF_STEP_BLOCK:
            return ["by simp", "by auto", "by blast"]
        if block_kind == WHOLE_PROOF_BODY_BLOCK:
            return ["by auto", "by blast", "by simp"]
        if block_kind == THEOREM_SHELL_BLOCK:
            return ["by auto", "by simp"]
        return []
