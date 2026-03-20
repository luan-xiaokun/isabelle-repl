from __future__ import annotations

import logging
from dataclasses import dataclass

import grpc

logger = logging.getLogger(__name__)

from . import repl_pb2 as pb2
from . import repl_pb2_grpc as pb2_grpc


# ── Result dataclasses ────────────────────────────────────────────────────────


@dataclass
class StateResult:
    state_id: str
    status: str  # "SUCCESS", "PROOF_COMPLETE", "ERROR", "TIMEOUT"
    error_msg: str
    proof_level: int
    mode: str  # "TOPLEVEL", "THEORY", "LOCAL_THEORY", "PROOF", "SKIPPED_PROOF"
    proof_state_text: str = ""  # populated only when include_text=True in the request

    def is_success(self) -> bool:
        return self.status in ("SUCCESS", "PROOF_COMPLETE")

    def is_timeout(self) -> bool:
        return self.status == "TIMEOUT"

    def proof_is_finished(self) -> bool:
        return self.status == "PROOF_COMPLETE"

    def logging_info(self) -> str:
        return f"mode={self.mode} level={self.proof_level}"


@dataclass
class StateInfo:
    state_id: str
    mode: str
    proof_level: int
    proof_state_text: str


@dataclass
class TheoryCommand:
    text: str
    kind: str
    line: int
    column: int


@dataclass
class InitStateError:
    """Returned by init_state when a command fails during replay."""

    failed_line: int
    error_msg: str
    last_success: StateResult | None  # None if the very first cmd failed


@dataclass
class InitStateResult:
    """Union result from init_state: exactly one of success/error is set."""

    success: StateResult | None
    error: InitStateError | None

    def is_success(self) -> bool:
        return self.success is not None

    # Convenience: raise if failed, return StateResult if ok
    def unwrap(self) -> StateResult:
        if self.success is not None:
            return self.success
        raise RuntimeError(
            f"init_state failed at line {self.error.failed_line}: {self.error.error_msg}"
        )


# ── Status/mode name helpers ──────────────────────────────────────────────────

_EXEC_STATUS_NAMES = {
    pb2.SUCCESS: "SUCCESS",
    pb2.PROOF_COMPLETE: "PROOF_COMPLETE",
    pb2.ERROR: "ERROR",
    pb2.TIMEOUT: "TIMEOUT",
}

_STATE_MODE_NAMES = {
    pb2.TOPLEVEL: "TOPLEVEL",
    pb2.THEORY: "THEORY",
    pb2.LOCAL_THEORY: "LOCAL_THEORY",
    pb2.PROOF: "PROOF",
    pb2.SKIPPED_PROOF: "SKIPPED_PROOF",
}


def _parse_state_result(r: pb2.StateResult) -> StateResult:
    return StateResult(
        state_id=r.state_id,
        status=_EXEC_STATUS_NAMES.get(r.status, str(r.status)),
        error_msg=r.error_msg,
        proof_level=r.proof_level,
        mode=_STATE_MODE_NAMES.get(r.mode, str(r.mode)),
        proof_state_text=r.proof_state_text,
    )


# ── Client ────────────────────────────────────────────────────────────────────


class IsaReplClient:
    """gRPC client for the IsabelleREPL service."""

    def __init__(self, host: str = "localhost", port: int = 50051):
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._stub = pb2_grpc.IsabelleREPLStub(self._channel)

    # ── Session ───────────────────────────────────────────────────────────────

    def create_session(
        self,
        isa_path: str,
        logic: str,
        working_directory: str,
        session_roots: list[str] | None = None,
    ) -> str:
        """Start an Isabelle process. Returns session_id."""
        logger.info("Creating session (logic=%s, isa_path=%s)", logic, isa_path)
        resp = self._stub.CreateSession(
            pb2.CreateSessionRequest(
                isa_path=str(isa_path),
                logic=logic,
                working_directory=str(working_directory),
                session_roots=session_roots or [],
            )
        )
        logger.info("Session created: %s", resp.session_id)
        return resp.session_id

    def destroy_session(self, session_id: str) -> None:
        logger.info("Destroying session: %s", session_id)
        self._stub.DestroySession(pb2.SessionRef(session_id=session_id))

    # ── Theory ────────────────────────────────────────────────────────────────

    def load_theory(self, session_id: str, theory_path: str) -> int:
        """Load (and cache) a theory file. Returns command count."""
        logger.info("Loading theory: %s", theory_path)
        resp = self._stub.LoadTheory(
            pb2.LoadTheoryRequest(
                session_id=session_id,
                theory_path=str(theory_path),
            )
        )
        logger.info("Theory loaded: %s (%d commands)", theory_path, resp.command_count)
        return resp.command_count

    def list_theory_commands(
        self,
        session_id: str,
        theory_path: str,
        only_proof_stmts: bool = False,
    ) -> list[TheoryCommand]:
        resp = self._stub.ListTheoryCommands(
            pb2.ListCommandsRequest(
                session_id=session_id,
                theory_path=str(theory_path),
                only_proof_stmts=only_proof_stmts,
            )
        )
        return [
            TheoryCommand(text=c.text, kind=c.kind, line=c.line, column=c.column)
            for c in resp.commands
        ]

    # ── ProofState lifecycle ──────────────────────────────────────────────────

    def init_state(
        self,
        session_id: str,
        theory_path: str,
        after_line: int | None = None,
        after_command: str | None = None,
        timeout_ms: int = 60000,
        include_text: bool = False,
    ) -> InitStateResult:
        """Replay transitions from TOPLEVEL up to the requested position.

        Exactly one of ``after_line`` or ``after_command`` should be given.
        If neither is given the entire theory is replayed (useful for
        whole-theory type-checking).

        Returns an :class:`InitStateResult` whose ``.success`` field is set on
        success, or whose ``.error`` field is set on failure.  The error
        contains the failing line number, error message, and the last state
        that was successfully reached (if any).
        """
        req = pb2.InitStateRequest(
            session_id=session_id,
            theory_path=str(theory_path),
            timeout_ms=timeout_ms,
            include_text=include_text,
        )
        if after_line is not None:
            req.after_line = after_line
        elif after_command is not None:
            req.after_command = after_command
        logger.debug(
            "InitState: %s (after_line=%s, after_command=%s)",
            theory_path,
            after_line,
            after_command,
        )
        resp = self._stub.InitState(req)
        which = resp.WhichOneof("result")
        if which == "success":
            return InitStateResult(
                success=_parse_state_result(resp.success), error=None
            )
        else:
            err = resp.error
            last = (
                _parse_state_result(err.last_success)
                if err.HasField("last_success")
                else None
            )
            logger.warning(
                "InitState failed at line %d: %s", err.failed_line, err.error_msg
            )
            return InitStateResult(
                success=None,
                error=InitStateError(
                    failed_line=err.failed_line,
                    error_msg=err.error_msg,
                    last_success=last,
                ),
            )

    def init_after_header(
        self,
        session_id: str,
        theory_path: str,
        timeout_ms: int = 60000,
        include_text: bool = False,
    ) -> InitStateResult:
        """Return the state after executing the 'theory ... imports ... begin'
        header — the minimal useful starting point for sequential execution.

        Looks up the theory command's actual source line via
        list_theory_commands so this works correctly even when the header is
        not at line 1 (e.g. copyright comment blocks above it).
        """
        cmds = self.list_theory_commands(session_id, theory_path)
        header = next((c for c in cmds if c.kind == "theory"), None)
        if header is None:
            raise ValueError(
                f"No 'theory' command found in {theory_path}; "
                "is the theory file valid?"
            )
        return self.init_state(
            session_id,
            theory_path,
            after_line=header.line,
            timeout_ms=timeout_ms,
            include_text=include_text,
        )

    def drop_state(self, state_ids: list[str]) -> None:
        self._stub.DropState(pb2.DropStateRequest(state_ids=state_ids))

    def drop_all_states(self, session_id: str) -> None:
        self._stub.DropAllStates(pb2.SessionRef(session_id=session_id))

    # ── Execution ─────────────────────────────────────────────────────────────

    def execute(
        self,
        source_state_id: str,
        tactic: str,
        timeout_ms: int = 30000,
        include_text: bool = False,
    ) -> StateResult:
        """Execute a tactic. Always returns a fresh state ID; source is preserved."""
        logger.debug("Execute: %r", tactic[:80])
        resp = self._stub.Execute(
            pb2.ExecuteRequest(
                source_state_id=source_state_id,
                tactic=tactic,
                timeout_ms=timeout_ms,
                include_text=include_text,
            )
        )
        result = _parse_state_result(resp)
        if not result.is_success():
            logger.warning(
                "Execute %r: %s — %s", tactic[:60], result.status, result.error_msg
            )
        return result

    def execute_many(
        self,
        source_state_id: str,
        tactics: list[str],
        timeout_ms: int = 30000,
        drop_failed: bool = False,
    ) -> list[StateResult]:
        """Execute multiple tactics in parallel. Returns results parallel to tactics."""
        logger.debug("ExecuteBatch: %d tactics", len(tactics))
        resp = self._stub.ExecuteBatch(
            pb2.ExecuteBatchRequest(
                source_state_id=source_state_id,
                tactics=tactics,
                timeout_ms=timeout_ms,
                drop_failed=drop_failed,
            )
        )
        results = [_parse_state_result(r) for r in resp.results]
        failed = [r for r in results if not r.is_success()]
        if failed:
            logger.warning(
                "ExecuteBatch: %d/%d tactics failed", len(failed), len(tactics)
            )
        return results

    # ── Sledgehammer ──────────────────────────────────────────────────────────

    def run_sledgehammer(
        self,
        source_state_id: str,
        timeout_ms: int = 30000,
        sledgehammer_timeout_ms: int = 30000,
    ):
        """Run Sledgehammer. Returns (found, tactic, state_result_or_None)."""
        logger.debug(
            "RunSledgehammer (timeout=%dms, sh_timeout=%dms)",
            timeout_ms,
            sledgehammer_timeout_ms,
        )
        resp = self._stub.RunSledgehammer(
            pb2.SledgehammerRequest(
                source_state_id=source_state_id,
                timeout_ms=timeout_ms,
                sledgehammer_timeout_ms=sledgehammer_timeout_ms,
            )
        )
        result = _parse_state_result(resp.result) if resp.HasField("result") else None
        if resp.found:
            logger.info("Sledgehammer found: %s", resp.tactic)
        else:
            logger.debug("Sledgehammer: no proof found")
        return resp.found, resp.tactic, result

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_state_info(
        self,
        state_id: str,
        include_text: bool = False,
    ) -> StateInfo:
        resp = self._stub.GetStateInfo(
            pb2.GetStateInfoRequest(
                state_id=state_id,
                include_text=include_text,
            )
        )
        return StateInfo(
            state_id=resp.state_id,
            mode=_STATE_MODE_NAMES.get(resp.mode, str(resp.mode)),
            proof_level=resp.proof_level,
            proof_state_text=resp.proof_state_text,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._channel.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
