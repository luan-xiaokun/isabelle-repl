from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from isabelle_repair.model import (
    BlockContract,
    FailureKind,
    LocalizedTask,
    RepairBlockCandidate,
)
from isabelle_repair.run.working_snapshot import WorkingTheorySnapshot
from isabelle_repl import IsabelleReplClient
from isabelle_repl.client import TheoryCommand

from .contracts import (
    TERMINAL_PROOF_STEP_BLOCK,
    THEOREM_SHELL_BLOCK,
    WHOLE_PROOF_BODY_BLOCK,
)


@dataclass
class ReplBlockLocalizer:
    """Incremental REPL-backed localizer with snapshot + drift fallback."""

    client: IsabelleReplClient
    session_id: str
    theory_path: str
    default_candidate_tactic: str = "by simp"
    allow_sledgehammer: bool = True
    timeout_ms: int = 30_000
    _commands: list[TheoryCommand] | None = None
    _header_index: int = -1
    _next_task_number: int = 0

    @classmethod
    def from_theory(
        cls,
        *,
        client: IsabelleReplClient,
        session_id: str,
        theory_path: str,
        default_candidate_tactic: str = "by simp",
        allow_sledgehammer: bool = True,
        timeout_ms: int = 30_000,
    ) -> ReplBlockLocalizer:
        return cls(
            client=client,
            session_id=session_id,
            theory_path=theory_path,
            default_candidate_tactic=default_candidate_tactic,
            allow_sledgehammer=allow_sledgehammer,
            timeout_ms=timeout_ms,
        )

    @classmethod
    def from_first_proof_statement(
        cls,
        *,
        client: IsabelleReplClient,
        session_id: str,
        theory_path: str,
        default_candidate_tactic: str = "by simp",
        allow_sledgehammer: bool = True,
        timeout_ms: int = 30_000,
    ) -> ReplBlockLocalizer:
        # Backward-compatible factory name.
        return cls.from_theory(
            client=client,
            session_id=session_id,
            theory_path=theory_path,
            default_candidate_tactic=default_candidate_tactic,
            allow_sledgehammer=allow_sledgehammer,
            timeout_ms=timeout_ms,
        )

    def next_task(
        self,
        theory_run_id: str,  # noqa: ARG002
        snapshot: Any | None = None,
    ) -> LocalizedTask | None:
        if not isinstance(snapshot, WorkingTheorySnapshot):
            return None

        self._ensure_commands_loaded()
        if not self._commands:
            return None
        if not self._ensure_anchor(snapshot):
            return None

        start_index = max(snapshot.command_cursor + 1, self._header_index + 1)
        for index in range(start_index, len(self._commands)):
            command = self._commands[index]
            effective_text = snapshot.replacement_for_line(command.line) or command.text
            source_state_id = snapshot.current_anchor_state_id
            if source_state_id is None:
                snapshot.set_last_failure_digest(
                    {
                        "reason": "missing_anchor_state",
                        "command_line": command.line,
                    }
                )
                return None

            execution = self.client.execute(
                source_state_id=source_state_id,
                tactic=effective_text,
                timeout_ms=self.timeout_ms,
                include_text=True,
            )
            if execution.is_success():
                snapshot.set_anchor(
                    state_id=execution.state_id,
                    command_cursor=index,
                    mode=execution.mode,
                    proof_level=execution.proof_level,
                )
                continue

            self._next_task_number += 1
            previous_digest = snapshot.last_failure_digest or {}
            drift_reason = previous_digest.get("drift_fallback_reason")
            fallback_candidates = self._default_fallback_candidates()
            fallback_chain = [candidate.block_kind for candidate in fallback_candidates]
            snapshot.set_last_failure_digest(
                {
                    "reason": "command_execution_failure",
                    "command_line": command.line,
                    "command_kind": command.kind,
                    "error_msg": execution.error_msg,
                    "entry_mode": snapshot.mode,
                    "entry_proof_level": snapshot.proof_level,
                    "drift_fallback_reason": drift_reason,
                }
            )
            return LocalizedTask(
                task_id=f"task-{self._next_task_number}",
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                failure_kind=self._classify_failure(
                    command_kind=command.kind,
                    entry_mode=str(snapshot.mode or ""),
                ),
                block_text=effective_text,
                entry_checkpoint={
                    "mode": snapshot.mode or "",
                    "proof_level": int(snapshot.proof_level or 0),
                },
                metadata={
                    "source_state_id": source_state_id,
                    "candidate_tactic": self.default_candidate_tactic,
                    "allow_sledgehammer": self.allow_sledgehammer,
                    "line": command.line,
                    "command_kind": command.kind,
                    "error_msg": execution.error_msg,
                    "fallback_chain": fallback_chain,
                    "fallback_origin": "terminal",
                    "drift_fallback_reason": drift_reason,
                },
                fallback_candidates=fallback_candidates,
            )
        return None

    def _ensure_commands_loaded(self) -> None:
        if self._commands is not None:
            return
        self._commands = self.client.list_theory_commands(
            session_id=self.session_id,
            theory_path=self.theory_path,
            only_proof_stmts=False,
        )
        self._header_index = next(
            (
                index
                for index, command in enumerate(self._commands)
                if command.kind == "theory"
            ),
            -1,
        )

    def _ensure_anchor(self, snapshot: WorkingTheorySnapshot) -> bool:
        if snapshot.current_anchor_state_id is None:
            return self._bootstrap_anchor(snapshot)

        drift_reason = self._detect_drift(snapshot)
        if drift_reason is None:
            return True

        snapshot.set_last_failure_digest(
            {
                "drift_fallback_reason": drift_reason,
                "anchor_state_id": snapshot.current_anchor_state_id,
                "command_cursor": snapshot.command_cursor,
            }
        )
        return self._rebuild_anchor_from_header(snapshot, drift_reason=drift_reason)

    def _bootstrap_anchor(self, snapshot: WorkingTheorySnapshot) -> bool:
        init_result = self.client.init_after_header(
            session_id=self.session_id,
            theory_path=self.theory_path,
            timeout_ms=self.timeout_ms,
            include_text=True,
        )
        if not init_result.is_success():
            snapshot.set_last_failure_digest(
                {
                    "reason": "init_after_header_failed",
                    "error": (
                        init_result.error.error_msg
                        if init_result.error is not None
                        else "unknown"
                    ),
                }
            )
            return False
        state = init_result.unwrap()
        snapshot.set_anchor(
            state_id=state.state_id,
            command_cursor=self._header_index,
            mode=state.mode,
            proof_level=state.proof_level,
        )
        snapshot.set_last_failure_digest(None)
        return True

    def _detect_drift(self, snapshot: WorkingTheorySnapshot) -> str | None:
        state_id = snapshot.current_anchor_state_id
        if state_id is None:
            return "missing_anchor_state"
        try:
            state_info = self.client.get_state_info(
                state_id=state_id,
                include_text=False,
            )
        except Exception:  # noqa: BLE001
            return "anchor_state_unavailable"
        if snapshot.mode and state_info.mode != snapshot.mode:
            return "mode_mismatch"
        if (
            snapshot.proof_level is not None
            and state_info.proof_level != snapshot.proof_level
        ):
            return "proof_level_mismatch"
        return None

    def _rebuild_anchor_from_header(
        self,
        snapshot: WorkingTheorySnapshot,
        *,
        drift_reason: str,
    ) -> bool:
        init_result = self.client.init_after_header(
            session_id=self.session_id,
            theory_path=self.theory_path,
            timeout_ms=self.timeout_ms,
            include_text=True,
        )
        if not init_result.is_success():
            return False
        anchor = init_result.unwrap()
        replay_upto = max(snapshot.command_cursor, self._header_index)
        for index in range(self._header_index + 1, replay_upto + 1):
            command = self._commands[index]
            effective_text = snapshot.replacement_for_line(command.line) or command.text
            replay = self.client.execute(
                source_state_id=anchor.state_id,
                tactic=effective_text,
                timeout_ms=self.timeout_ms,
                include_text=True,
            )
            if not replay.is_success():
                snapshot.set_last_failure_digest(
                    {
                        "drift_fallback_reason": drift_reason,
                        "reason": "rebuild_anchor_failed",
                        "command_line": command.line,
                        "command_kind": command.kind,
                        "error_msg": replay.error_msg,
                    }
                )
                return False
            anchor = replay
        snapshot.set_anchor(
            state_id=anchor.state_id,
            command_cursor=replay_upto,
            mode=anchor.mode,
            proof_level=anchor.proof_level,
        )
        snapshot.set_last_failure_digest(
            {
                "drift_fallback_reason": drift_reason,
                "reason": "rebuild_anchor_success",
                "command_cursor": replay_upto,
            }
        )
        return True

    @staticmethod
    def _default_fallback_candidates() -> list[RepairBlockCandidate]:
        return [
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=WHOLE_PROOF_BODY_BLOCK,
                block_contract=BlockContract.SUBPROOF_CLOSED,
                origin="fallback",
            ),
            RepairBlockCandidate(
                block_kind=THEOREM_SHELL_BLOCK,
                block_contract=BlockContract.THEOREM_CLOSED,
                origin="fallback",
            ),
        ]

    @staticmethod
    def _classify_failure(*, command_kind: str, entry_mode: str) -> FailureKind:
        if entry_mode == "PROOF" and command_kind in {"by", "proof", "qed"}:
            return FailureKind.PROOF_BODY_FAILURE
        if entry_mode == "PROOF":
            return FailureKind.STATEMENT_FAILURE
        if command_kind in {"lemma", "theorem", "have", "show", "hence", "thus"}:
            return FailureKind.STATEMENT_FAILURE
        return FailureKind.NON_PROOF_COMMAND_FAILURE
