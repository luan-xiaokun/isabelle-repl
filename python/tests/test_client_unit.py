from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from isa_repl import repl_pb2 as pb2
from isa_repl.client import (
    InitStateError,
    InitStateResult,
    IsaReplClient,
    StateResult,
    TheoryCommand,
    _parse_state_result,
)


@dataclass
class _FakeErrorField:
    failed_line: int
    error_msg: str
    last_success: pb2.StateResult | None = None
    code: int = pb2.INIT_STATE_ERROR_UNKNOWN
    candidate_lines: list[int] = field(default_factory=list)

    def HasField(self, name: str) -> bool:
        return name == "last_success" and self.last_success is not None


@dataclass
class _FakeInitStateResponse:
    success: pb2.StateResult | None = None
    error: _FakeErrorField | None = None

    def WhichOneof(self, name: str) -> str | None:
        assert name == "result"
        if self.success is not None:
            return "success"
        if self.error is not None:
            return "error"
        return None


class _RecordingStub:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []
        self.create_session_response = pb2.CreateSessionResponse(session_id="session-1")
        self.list_commands_response = pb2.ListCommandsResponse()
        self.init_state_response = _FakeInitStateResponse()
        self.execute_response = pb2.StateResult()
        self.execute_batch_response = pb2.ExecuteBatchResponse()
        self.sledgehammer_response = pb2.SledgehammerResponse(found=False, tactic="")
        self.state_info_response = pb2.StateInfo()

    def CreateSession(self, req):
        self.calls.append(("CreateSession", req))
        return self.create_session_response

    def DestroySession(self, req):
        self.calls.append(("DestroySession", req))
        return pb2.Empty()

    def LoadTheory(self, req):
        self.calls.append(("LoadTheory", req))
        return pb2.LoadTheoryResponse(command_count=7)

    def ListTheoryCommands(self, req):
        self.calls.append(("ListTheoryCommands", req))
        return self.list_commands_response

    def InitState(self, req):
        self.calls.append(("InitState", req))
        return self.init_state_response

    def DropState(self, req):
        self.calls.append(("DropState", req))
        return pb2.Empty()

    def DropAllStates(self, req):
        self.calls.append(("DropAllStates", req))
        return pb2.Empty()

    def Execute(self, req):
        self.calls.append(("Execute", req))
        return self.execute_response

    def ExecuteBatch(self, req):
        self.calls.append(("ExecuteBatch", req))
        return self.execute_batch_response

    def RunSledgehammer(self, req):
        self.calls.append(("RunSledgehammer", req))
        return self.sledgehammer_response

    def GetStateInfo(self, req):
        self.calls.append(("GetStateInfo", req))
        return self.state_info_response


class _FakeChannel:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def client_env(monkeypatch):
    channel = _FakeChannel()
    stub = _RecordingStub()

    monkeypatch.setattr("isa_repl.client.grpc.insecure_channel", lambda target: channel)
    monkeypatch.setattr("isa_repl.client.pb2_grpc.IsabelleREPLStub", lambda ch: stub)

    client = IsaReplClient(host="example.com", port=4242)
    return client, stub, channel


def test_parse_state_result_falls_back_to_numeric_values():
    parsed = _parse_state_result(
        pb2.StateResult(
            state_id="s1",
            status=999,
            error_msg="boom",
            proof_level=3,
            mode=777,
            proof_state_text="goal",
        )
    )

    assert parsed.state_id == "s1"
    assert parsed.status == "999"
    assert parsed.mode == "777"
    assert parsed.error_msg == "boom"
    assert parsed.proof_state_text == "goal"


def test_init_state_result_unwrap_raises_with_context():
    result = InitStateResult(
        success=None,
        error=InitStateError(
            failed_line=12,
            error_msg="bad replay",
            last_success=None,
            code="INIT_STATE_EXECUTION_FAILED",
            candidate_lines=[],
        ),
    )

    with pytest.raises(RuntimeError, match=r"line 12: bad replay"):
        result.unwrap()


def test_state_result_helper_methods_cover_success_timeout_and_logging():
    success = StateResult(
        state_id="ok",
        status="PROOF_COMPLETE",
        error_msg="",
        proof_level=0,
        mode="TOPLEVEL",
    )
    timeout = StateResult(
        state_id="slow",
        status="TIMEOUT",
        error_msg="Timeout",
        proof_level=1,
        mode="PROOF",
    )

    assert success.is_success()
    assert success.proof_is_finished()
    assert success.logging_info() == "mode=TOPLEVEL level=0"
    assert timeout.is_timeout()
    assert not timeout.is_success()


def test_create_session_uses_empty_roots_by_default(client_env):
    client, stub, _ = client_env

    session_id = client.create_session(
        isa_path="/isa",
        logic="HOL",
        working_directory="/work",
    )

    assert session_id == "session-1"
    _, request = stub.calls[-1]
    assert request.isa_path == "/isa"
    assert request.logic == "HOL"
    assert request.working_directory == "/work"
    assert list(request.session_roots) == []


def test_session_and_state_lifecycle_requests_use_expected_messages(client_env):
    client, stub, _ = client_env

    count = client.load_theory("session-1", "/tmp/Simple.thy")
    client.destroy_session("session-1")
    client.drop_state(["s1", "s2"])
    client.drop_all_states("session-1")

    assert count == 7
    assert [name for name, _ in stub.calls] == [
        "LoadTheory",
        "DestroySession",
        "DropState",
        "DropAllStates",
    ]
    assert stub.calls[0][1].theory_path == "/tmp/Simple.thy"
    assert stub.calls[1][1].session_id == "session-1"
    assert list(stub.calls[2][1].state_ids) == ["s1", "s2"]
    assert stub.calls[3][1].session_id == "session-1"


def test_list_theory_commands_maps_proto_messages(client_env):
    client, stub, _ = client_env
    stub.list_commands_response.commands.extend(
        [
            pb2.TheoryCommand(text="theory Simple", kind="theory", line=1),
            pb2.TheoryCommand(text='lemma trivial: "True"', kind="lemma", line=5),
        ]
    )

    commands = client.list_theory_commands("session", "/tmp/Simple.thy", True)

    assert commands == [
        TheoryCommand(text="theory Simple", kind="theory", line=1),
        TheoryCommand(text='lemma trivial: "True"', kind="lemma", line=5),
    ]
    _, request = stub.calls[-1]
    assert request.only_proof_stmts is True


def test_init_state_builds_request_from_after_line_and_returns_success(client_env):
    client, stub, _ = client_env
    stub.init_state_response = _FakeInitStateResponse(
        success=pb2.StateResult(
            state_id="state-1",
            status=pb2.SUCCESS,
            proof_level=1,
            mode=pb2.PROOF,
            proof_state_text="goal",
        )
    )

    result = client.init_state(
        "session-1",
        "/tmp/Simple.thy",
        after_line=5,
        timeout_ms=123,
        include_text=True,
    )

    assert result.is_success()
    assert result.unwrap().state_id == "state-1"
    _, request = stub.calls[-1]
    assert request.session_id == "session-1"
    assert request.theory_path == "/tmp/Simple.thy"
    assert request.after_line == 5
    assert request.after_command == ""
    assert request.timeout_ms == 123
    assert request.include_text is True


def test_init_state_builds_request_from_after_command_and_returns_error(client_env):
    client, stub, _ = client_env
    stub.init_state_response = _FakeInitStateResponse(
        error=_FakeErrorField(
            failed_line=9,
            error_msg="Failed",
            last_success=pb2.StateResult(
                state_id="state-0",
                status=pb2.SUCCESS,
                proof_level=1,
                mode=pb2.PROOF,
            ),
        )
    )

    result = client.init_state(
        "session-1",
        "/tmp/Simple.thy",
        after_command='lemma trivial: "True"',
    )

    assert not result.is_success()
    assert result.error.failed_line == 9
    assert result.error.last_success is not None
    assert result.error.last_success.state_id == "state-0"
    assert result.error.code == "INIT_STATE_ERROR_UNKNOWN"
    assert result.error.candidate_lines == []
    _, request = stub.calls[-1]
    assert request.after_line == 0
    assert request.after_command == 'lemma trivial: "True"'


def test_init_state_error_code_and_candidates_are_mapped(client_env):
    client, stub, _ = client_env
    stub.init_state_response = _FakeInitStateResponse(
        error=_FakeErrorField(
            failed_line=0,
            error_msg="ambiguous selector",
            code=pb2.INIT_STATE_AMBIGUOUS,
            candidate_lines=[10, 42],
        )
    )

    result = client.init_state(
        "session-1",
        "/tmp/Simple.thy",
        after_command="by simp",
    )

    assert not result.is_success()
    assert result.error is not None
    assert result.error.code == "INIT_STATE_AMBIGUOUS"
    assert result.error.candidate_lines == [10, 42]


def test_init_after_header_uses_theory_command_line(client_env, monkeypatch):
    client, _, _ = client_env
    seen = {}

    monkeypatch.setattr(
        client,
        "list_theory_commands",
        lambda session_id, theory_path: [
            TheoryCommand(text="comment", kind="text", line=1),
            TheoryCommand(text="theory Demo", kind="theory", line=4),
        ],
    )

    def fake_init_state(session_id, theory_path, **kwargs):
        seen["args"] = (session_id, theory_path, kwargs)
        return InitStateResult(
            success=_parse_state_result(
                pb2.StateResult(
                    state_id="state-4",
                    status=pb2.SUCCESS,
                    proof_level=0,
                    mode=pb2.THEORY,
                )
            ),
            error=None,
        )

    monkeypatch.setattr(client, "init_state", fake_init_state)

    result = client.init_after_header("session-1", "/tmp/Demo.thy", include_text=True)

    assert result.is_success()
    assert seen["args"] == (
        "session-1",
        "/tmp/Demo.thy",
        {"after_line": 4, "timeout_ms": 60000, "include_text": True},
    )


def test_init_after_header_raises_when_theory_command_missing(client_env, monkeypatch):
    client, _, _ = client_env
    monkeypatch.setattr(client, "list_theory_commands", lambda *args: [])

    with pytest.raises(ValueError, match="No 'theory' command found"):
        client.init_after_header("session-1", "/tmp/Bad.thy")


def test_execute_many_preserves_result_order_and_drop_failed_flag(client_env):
    client, stub, _ = client_env
    stub.execute_batch_response.results.extend(
        [
            pb2.StateResult(
                state_id="ok", status=pb2.PROOF_COMPLETE, mode=pb2.TOPLEVEL
            ),
            pb2.StateResult(
                state_id="bad",
                status=pb2.ERROR,
                mode=pb2.PROOF,
                error_msg="bad tactic",
            ),
        ]
    )

    results = client.execute_many("source", ["by simp", "by bad"], drop_failed=True)

    assert [r.state_id for r in results] == ["ok", "bad"]
    _, request = stub.calls[-1]
    assert request.source_state_id == "source"
    assert list(request.tactics) == ["by simp", "by bad"]
    assert request.drop_failed is True


def test_execute_returns_error_state_without_touching_source(client_env):
    client, stub, _ = client_env
    stub.execute_response = pb2.StateResult(
        state_id="failed",
        status=pb2.ERROR,
        error_msg="bad tactic",
        proof_level=1,
        mode=pb2.PROOF,
    )

    result = client.execute("source", "by bad", timeout_ms=77, include_text=True)

    assert result.status == "ERROR"
    assert result.error_msg == "bad tactic"
    _, request = stub.calls[-1]
    assert request.source_state_id == "source"
    assert request.timeout_ms == 77
    assert request.include_text is True


def test_run_sledgehammer_returns_tuple_with_optional_state(client_env):
    client, stub, _ = client_env
    stub.sledgehammer_response = pb2.SledgehammerResponse(
        found=True,
        tactic="by blast",
        result=pb2.StateResult(
            state_id="hammer",
            status=pb2.PROOF_COMPLETE,
            proof_level=0,
            mode=pb2.TOPLEVEL,
        ),
    )

    found, tactic, result = client.run_sledgehammer(
        "source",
        timeout_ms=1000,
        sledgehammer_timeout_ms=2000,
    )

    assert found is True
    assert tactic == "by blast"
    assert result is not None
    assert result.proof_is_finished()
    _, request = stub.calls[-1]
    assert request.timeout_ms == 1000
    assert request.sledgehammer_timeout_ms == 2000


def test_run_sledgehammer_without_result_returns_none(client_env):
    client, stub, _ = client_env
    stub.sledgehammer_response = pb2.SledgehammerResponse(found=False, tactic="")

    found, tactic, result = client.run_sledgehammer("source")

    assert found is False
    assert tactic == ""
    assert result is None


def test_get_state_info_maps_modes_and_context_manager_closes_channel(client_env):
    client, stub, channel = client_env
    stub.state_info_response = pb2.StateInfo(
        state_id="state-1",
        mode=pb2.LOCAL_THEORY,
        proof_level=2,
        proof_state_text="subgoal",
        local_theory_desc="locale x",
    )

    with client as managed:
        info = managed.get_state_info("state-1", include_text=True)

    assert info.state_id == "state-1"
    assert info.mode == "LOCAL_THEORY"
    assert info.local_theory_desc == "locale x"
    assert channel.closed is True
    _, request = stub.calls[-1]
    assert request.state_id == "state-1"
    assert request.include_text is True
