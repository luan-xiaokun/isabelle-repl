from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExecStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SUCCESS: _ClassVar[ExecStatus]
    PROOF_COMPLETE: _ClassVar[ExecStatus]
    ERROR: _ClassVar[ExecStatus]
    TIMEOUT: _ClassVar[ExecStatus]

class StateMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TOPLEVEL: _ClassVar[StateMode]
    THEORY: _ClassVar[StateMode]
    LOCAL_THEORY: _ClassVar[StateMode]
    PROOF: _ClassVar[StateMode]
    SKIPPED_PROOF: _ClassVar[StateMode]
SUCCESS: ExecStatus
PROOF_COMPLETE: ExecStatus
ERROR: ExecStatus
TIMEOUT: ExecStatus
TOPLEVEL: StateMode
THEORY: StateMode
LOCAL_THEORY: StateMode
PROOF: StateMode
SKIPPED_PROOF: StateMode

class SessionRef(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class CreateSessionRequest(_message.Message):
    __slots__ = ("isa_path", "logic", "working_directory", "session_roots")
    ISA_PATH_FIELD_NUMBER: _ClassVar[int]
    LOGIC_FIELD_NUMBER: _ClassVar[int]
    WORKING_DIRECTORY_FIELD_NUMBER: _ClassVar[int]
    SESSION_ROOTS_FIELD_NUMBER: _ClassVar[int]
    isa_path: str
    logic: str
    working_directory: str
    session_roots: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, isa_path: _Optional[str] = ..., logic: _Optional[str] = ..., working_directory: _Optional[str] = ..., session_roots: _Optional[_Iterable[str]] = ...) -> None: ...

class CreateSessionResponse(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class LoadTheoryRequest(_message.Message):
    __slots__ = ("session_id", "theory_path")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    THEORY_PATH_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    theory_path: str
    def __init__(self, session_id: _Optional[str] = ..., theory_path: _Optional[str] = ...) -> None: ...

class LoadTheoryResponse(_message.Message):
    __slots__ = ("theory_path", "command_count")
    THEORY_PATH_FIELD_NUMBER: _ClassVar[int]
    COMMAND_COUNT_FIELD_NUMBER: _ClassVar[int]
    theory_path: str
    command_count: int
    def __init__(self, theory_path: _Optional[str] = ..., command_count: _Optional[int] = ...) -> None: ...

class ListCommandsRequest(_message.Message):
    __slots__ = ("session_id", "theory_path", "only_proof_stmts")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    THEORY_PATH_FIELD_NUMBER: _ClassVar[int]
    ONLY_PROOF_STMTS_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    theory_path: str
    only_proof_stmts: bool
    def __init__(self, session_id: _Optional[str] = ..., theory_path: _Optional[str] = ..., only_proof_stmts: bool = ...) -> None: ...

class TheoryCommand(_message.Message):
    __slots__ = ("text", "kind", "line")
    TEXT_FIELD_NUMBER: _ClassVar[int]
    KIND_FIELD_NUMBER: _ClassVar[int]
    LINE_FIELD_NUMBER: _ClassVar[int]
    text: str
    kind: str
    line: int
    def __init__(self, text: _Optional[str] = ..., kind: _Optional[str] = ..., line: _Optional[int] = ...) -> None: ...

class ListCommandsResponse(_message.Message):
    __slots__ = ("commands",)
    COMMANDS_FIELD_NUMBER: _ClassVar[int]
    commands: _containers.RepeatedCompositeFieldContainer[TheoryCommand]
    def __init__(self, commands: _Optional[_Iterable[_Union[TheoryCommand, _Mapping]]] = ...) -> None: ...

class StateRef(_message.Message):
    __slots__ = ("state_id",)
    STATE_ID_FIELD_NUMBER: _ClassVar[int]
    state_id: str
    def __init__(self, state_id: _Optional[str] = ...) -> None: ...

class InitStateRequest(_message.Message):
    __slots__ = ("session_id", "theory_path", "after_line", "after_command", "timeout_ms", "include_text")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    THEORY_PATH_FIELD_NUMBER: _ClassVar[int]
    AFTER_LINE_FIELD_NUMBER: _ClassVar[int]
    AFTER_COMMAND_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TEXT_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    theory_path: str
    after_line: int
    after_command: str
    timeout_ms: int
    include_text: bool
    def __init__(self, session_id: _Optional[str] = ..., theory_path: _Optional[str] = ..., after_line: _Optional[int] = ..., after_command: _Optional[str] = ..., timeout_ms: _Optional[int] = ..., include_text: bool = ...) -> None: ...

class InitStateResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: StateResult
    error: InitStateError
    def __init__(self, success: _Optional[_Union[StateResult, _Mapping]] = ..., error: _Optional[_Union[InitStateError, _Mapping]] = ...) -> None: ...

class InitStateError(_message.Message):
    __slots__ = ("failed_line", "error_msg", "last_success")
    FAILED_LINE_FIELD_NUMBER: _ClassVar[int]
    ERROR_MSG_FIELD_NUMBER: _ClassVar[int]
    LAST_SUCCESS_FIELD_NUMBER: _ClassVar[int]
    failed_line: int
    error_msg: str
    last_success: StateResult
    def __init__(self, failed_line: _Optional[int] = ..., error_msg: _Optional[str] = ..., last_success: _Optional[_Union[StateResult, _Mapping]] = ...) -> None: ...

class DropStateRequest(_message.Message):
    __slots__ = ("state_ids",)
    STATE_IDS_FIELD_NUMBER: _ClassVar[int]
    state_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, state_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class ExecuteRequest(_message.Message):
    __slots__ = ("source_state_id", "tactic", "timeout_ms", "include_text")
    SOURCE_STATE_ID_FIELD_NUMBER: _ClassVar[int]
    TACTIC_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TEXT_FIELD_NUMBER: _ClassVar[int]
    source_state_id: str
    tactic: str
    timeout_ms: int
    include_text: bool
    def __init__(self, source_state_id: _Optional[str] = ..., tactic: _Optional[str] = ..., timeout_ms: _Optional[int] = ..., include_text: bool = ...) -> None: ...

class StateResult(_message.Message):
    __slots__ = ("state_id", "status", "error_msg", "proof_level", "mode", "proof_state_text")
    STATE_ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MSG_FIELD_NUMBER: _ClassVar[int]
    PROOF_LEVEL_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    PROOF_STATE_TEXT_FIELD_NUMBER: _ClassVar[int]
    state_id: str
    status: ExecStatus
    error_msg: str
    proof_level: int
    mode: StateMode
    proof_state_text: str
    def __init__(self, state_id: _Optional[str] = ..., status: _Optional[_Union[ExecStatus, str]] = ..., error_msg: _Optional[str] = ..., proof_level: _Optional[int] = ..., mode: _Optional[_Union[StateMode, str]] = ..., proof_state_text: _Optional[str] = ...) -> None: ...

class ExecuteBatchRequest(_message.Message):
    __slots__ = ("source_state_id", "tactics", "timeout_ms", "drop_failed")
    SOURCE_STATE_ID_FIELD_NUMBER: _ClassVar[int]
    TACTICS_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    DROP_FAILED_FIELD_NUMBER: _ClassVar[int]
    source_state_id: str
    tactics: _containers.RepeatedScalarFieldContainer[str]
    timeout_ms: int
    drop_failed: bool
    def __init__(self, source_state_id: _Optional[str] = ..., tactics: _Optional[_Iterable[str]] = ..., timeout_ms: _Optional[int] = ..., drop_failed: bool = ...) -> None: ...

class ExecuteBatchResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[StateResult]
    def __init__(self, results: _Optional[_Iterable[_Union[StateResult, _Mapping]]] = ...) -> None: ...

class SledgehammerRequest(_message.Message):
    __slots__ = ("source_state_id", "timeout_ms", "sledgehammer_timeout_ms")
    SOURCE_STATE_ID_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    SLEDGEHAMMER_TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    source_state_id: str
    timeout_ms: int
    sledgehammer_timeout_ms: int
    def __init__(self, source_state_id: _Optional[str] = ..., timeout_ms: _Optional[int] = ..., sledgehammer_timeout_ms: _Optional[int] = ...) -> None: ...

class SledgehammerResponse(_message.Message):
    __slots__ = ("found", "tactic", "result")
    FOUND_FIELD_NUMBER: _ClassVar[int]
    TACTIC_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    found: bool
    tactic: str
    result: StateResult
    def __init__(self, found: bool = ..., tactic: _Optional[str] = ..., result: _Optional[_Union[StateResult, _Mapping]] = ...) -> None: ...

class GetStateInfoRequest(_message.Message):
    __slots__ = ("state_id", "include_text")
    STATE_ID_FIELD_NUMBER: _ClassVar[int]
    INCLUDE_TEXT_FIELD_NUMBER: _ClassVar[int]
    state_id: str
    include_text: bool
    def __init__(self, state_id: _Optional[str] = ..., include_text: bool = ...) -> None: ...

class StateInfo(_message.Message):
    __slots__ = ("state_id", "mode", "proof_level", "proof_state_text", "local_theory_desc")
    STATE_ID_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    PROOF_LEVEL_FIELD_NUMBER: _ClassVar[int]
    PROOF_STATE_TEXT_FIELD_NUMBER: _ClassVar[int]
    LOCAL_THEORY_DESC_FIELD_NUMBER: _ClassVar[int]
    state_id: str
    mode: StateMode
    proof_level: int
    proof_state_text: str
    local_theory_desc: str
    def __init__(self, state_id: _Optional[str] = ..., mode: _Optional[_Union[StateMode, str]] = ..., proof_level: _Optional[int] = ..., proof_state_text: _Optional[str] = ..., local_theory_desc: _Optional[str] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
