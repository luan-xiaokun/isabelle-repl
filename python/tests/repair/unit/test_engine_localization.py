from __future__ import annotations

from dataclasses import dataclass, field

from isabelle_repair.engine import DeterministicTaskController, RuleFirstGenerator
from isabelle_repair.engine.adapters import ValidationAdapterRegistry, ValidationContext
from isabelle_repair.localization import (
    TERMINAL_PROOF_STEP_BLOCK,
    THEOREM_SHELL_BLOCK,
    TOP_LEVEL_COMMAND_BLOCK,
    WHOLE_PROOF_BODY_BLOCK,
    ReplBlockLocalizer,
)
from isabelle_repair.model import (
    BlockContract,
    FailureKind,
    LocalizedTask,
    RepairBlockCandidate,
    TaskOutcome,
    TaskSpec,
    ValidationStatus,
)
from isabelle_repair.repl import ReplDeterministicTaskEngine
from isabelle_repair.run import WorkingTheorySnapshot
from isabelle_repl.client import InitStateResult, StateResult, TheoryCommand


@dataclass
class _FakeClient:
    list_commands: list[TheoryCommand]
    init_state_result: InitStateResult
    execute_results: list[StateResult]
    sledgehammer: tuple[bool, str, StateResult | None] = (False, "", None)
    get_state_info_mode: str = "PROOF"
    get_state_info_level: int = 1
    init_after_header_calls: int = 0
    execute_calls: list[dict[str, object]] = field(default_factory=list)

    def list_theory_commands(self, session_id, theory_path, only_proof_stmts=False):  # noqa: ANN001, ARG002
        return self.list_commands

    def init_state(self, **kwargs):  # noqa: ANN003
        return self.init_state_result

    def init_after_header(self, **kwargs):  # noqa: ANN003
        self.init_after_header_calls += 1
        return self.init_state_result

    def execute(self, **kwargs):  # noqa: ANN003
        self.execute_calls.append(dict(kwargs))
        if not self.execute_results:
            raise RuntimeError("no execute result queued")
        return self.execute_results.pop(0)

    def run_sledgehammer(self, **kwargs):  # noqa: ANN003
        return self.sledgehammer

    def get_state_info(self, **kwargs):  # noqa: ANN003
        @dataclass
        class _StateInfo:
            state_id: str = "s"
            mode: str = "PROOF"
            proof_level: int = 1

        return _StateInfo(
            mode=self.get_state_info_mode,
            proof_level=self.get_state_info_level,
        )


def _state(
    *,
    state_id: str = "s",
    status: str = "SUCCESS",
    mode: str = "PROOF",
    proof_level: int = 1,
    error_msg: str = "",
) -> StateResult:
    return StateResult(
        state_id=state_id,
        status=status,
        error_msg=error_msg,
        proof_level=proof_level,
        mode=mode,
        proof_state_text="",
    )


def test_localizer_has_terminal_to_whole_to_theorem_fallback_chain():
    client = _FakeClient(
        list_commands=[
            TheoryCommand(text="theory T imports Main begin", kind="theory", line=1),
            TheoryCommand(text='lemma t: "True"', kind="lemma", line=5),
        ],
        init_state_result=InitStateResult(success=_state(state_id="s0"), error=None),
        execute_results=[_state(status="ERROR", error_msg="boom", proof_level=1)],
    )
    localizer = ReplBlockLocalizer.from_theory(
        client=client,
        session_id="sess",
        theory_path="/tmp/T.thy",
    )
    snapshot = WorkingTheorySnapshot(
        theory_path="/tmp/T.thy",
        original_text="theory T imports Main begin",
    )
    task = localizer.next_task("run-x", snapshot)
    assert task is not None
    assert task.block_kind == TERMINAL_PROOF_STEP_BLOCK
    assert task.metadata["source_state_id"] == "s0"
    assert task.metadata["fallback_chain"] == [
        TERMINAL_PROOF_STEP_BLOCK,
        WHOLE_PROOF_BODY_BLOCK,
        THEOREM_SHELL_BLOCK,
    ]
    assert [candidate.block_kind for candidate in task.fallback_candidates] == [
        TERMINAL_PROOF_STEP_BLOCK,
        WHOLE_PROOF_BODY_BLOCK,
        THEOREM_SHELL_BLOCK,
    ]
    assert task.metadata["fallback_chain"] == [
        candidate.block_kind for candidate in task.fallback_candidates
    ]
    assert [candidate.block_contract for candidate in task.fallback_candidates] == [
        BlockContract.GOAL_CLOSED,
        BlockContract.SUBPROOF_CLOSED,
        BlockContract.THEOREM_CLOSED,
    ]
    assert [candidate.origin for candidate in task.fallback_candidates] == [
        "primary",
        "fallback",
        "fallback",
    ]


def test_localized_task_exposes_structured_fallback_candidates():
    task = LocalizedTask(
        task_id="task-structured",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by auto",
        fallback_candidates=[
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
        ],
    )

    assert [candidate.block_kind for candidate in task.fallback_candidates] == [
        TERMINAL_PROOF_STEP_BLOCK,
        WHOLE_PROOF_BODY_BLOCK,
    ]
    assert task.fallback_candidates[0].block_contract == BlockContract.GOAL_CLOSED


def test_localizer_uses_snapshot_cursor_and_records_drift_reason():
    client = _FakeClient(
        list_commands=[
            TheoryCommand(text="theory T imports Main begin", kind="theory", line=1),
            TheoryCommand(text='lemma t: "True"', kind="lemma", line=5),
            TheoryCommand(text="by simp", kind="by", line=6),
        ],
        init_state_result=InitStateResult(success=_state(state_id="s0"), error=None),
        execute_results=[
            _state(state_id="s1", status="SUCCESS", mode="PROOF", proof_level=1),
            _state(state_id="s2", status="ERROR", error_msg="first-failure"),
            _state(
                state_id="s1-rebuilt",
                status="SUCCESS",
                mode="PROOF",
                proof_level=1,
            ),
            _state(state_id="s2-failure", status="ERROR", error_msg="second-failure"),
        ],
        get_state_info_mode="THEORY",
        get_state_info_level=0,
    )
    localizer = ReplBlockLocalizer.from_theory(
        client=client,
        session_id="sess",
        theory_path="/tmp/T.thy",
    )
    snapshot = WorkingTheorySnapshot(
        theory_path="/tmp/T.thy",
        original_text="theory T imports Main begin",
    )

    first = localizer.next_task("run-x", snapshot)
    assert first is not None
    assert first.metadata["line"] == 6
    assert snapshot.command_cursor == 1

    second = localizer.next_task("run-x", snapshot)
    assert second is not None
    assert second.metadata["drift_fallback_reason"] == "mode_mismatch"


def test_localizer_nominal_path_does_not_replay_header_per_task():
    client = _FakeClient(
        list_commands=[
            TheoryCommand(text="theory T imports Main begin", kind="theory", line=1),
            TheoryCommand(text='lemma t: "True"', kind="lemma", line=5),
            TheoryCommand(text="by simp", kind="by", line=6),
        ],
        init_state_result=InitStateResult(success=_state(state_id="s0"), error=None),
        execute_results=[
            _state(state_id="s1", status="SUCCESS", mode="PROOF", proof_level=1),
            _state(state_id="s2", status="ERROR", error_msg="first-failure"),
            _state(state_id="s3", status="ERROR", error_msg="second-failure"),
        ],
    )
    localizer = ReplBlockLocalizer.from_theory(
        client=client,
        session_id="sess",
        theory_path="/tmp/T.thy",
    )
    snapshot = WorkingTheorySnapshot(
        theory_path="/tmp/T.thy",
        original_text="theory T imports Main begin",
    )
    first = localizer.next_task("run-x", snapshot)
    second = localizer.next_task("run-x", snapshot)
    assert first is not None
    assert second is not None
    assert client.init_after_header_calls == 1


def test_rule_generator_prefers_rules_then_sledgehammer():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[],
        sledgehammer=(True, "by metis", _state(status="PROOF_COMPLETE", proof_level=0)),
    )
    generator = RuleFirstGenerator(client=client)
    task = LocalizedTask(
        task_id="task-1",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by simp",
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-1",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    assert generator.generate_candidates(spec)[:2] == ["by simp", "by auto"]

    unknown = LocalizedTask(
        task_id="task-2",
        block_kind="UnknownBlock",
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="x",
        metadata={"source_state_id": "s0"},
    )
    unknown_spec = TaskSpec(
        theory_run_id="run-1",
        task=unknown,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    assert generator.generate_candidates(unknown_spec) == ["by metis"]


def test_controller_inspect_propose_validate_loop_and_contract_check():
    # First candidate executes but does not close goal; second closes goal.
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    controller = DeterministicTaskController(
        client=client,
        generator=RuleFirstGenerator(client=client),
        adapters=ValidationAdapterRegistry.default(),
    )
    task = LocalizedTask(
        task_id="task-3",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by simp",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-1",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    result = controller.run(spec)
    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.attempted_candidates[:2] == ["by simp", "by auto"]
    assert result.selected_generator == "auto_rule_first"
    assert result.validation is not None
    assert result.validation.details["candidate_source"] == "auto_rule_first"
    assert "inspect=1" in result.trace_summary
    assert "validate=2" in result.trace_summary


def test_controller_returns_action_count_trace_details_and_selected_source():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    controller = DeterministicTaskController(
        client=client,
        generator=RuleFirstGenerator(client=client),
        adapters=ValidationAdapterRegistry.default(),
    )
    task = LocalizedTask(
        task_id="task-trace-details",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-trace-details",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = controller.run(spec)

    assert result.trace_counts == {
        "inspect": 1,
        "propose": 1,
        "validate": 1,
    }
    assert "inspect=1 propose=1 validate=1" in result.trace_summary
    assert "selected=by simp" in result.trace_summary
    assert "source=auto_rule_first" in result.trace_summary


def test_controller_trace_summary_includes_counts_for_non_acceptance_paths():
    missing_source = LocalizedTask(
        task_id="task-missing-source",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
    )
    top_level = LocalizedTask(
        task_id="task-no-candidate",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        entry_checkpoint={"mode": "THEORY", "proof_level": 0},
        metadata={"source_state_id": "s0"},
    )
    rejected = LocalizedTask(
        task_id="task-rejected",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    budget = LocalizedTask(
        task_id="task-budget-controller",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    scenarios = [
        (
            missing_source,
            BlockContract.GOAL_CLOSED,
            [],
            10,
            "inspect=0 propose=0 validate=0 reason=missing_source_state",
            {"inspect": 0, "propose": 0, "validate": 0},
        ),
        (
            top_level,
            BlockContract.CONTEXT_UPDATED,
            [],
            10,
            "inspect=1 propose=0 validate=0 reason=no_candidate_generated",
            {"inspect": 1, "propose": 0, "validate": 0},
        ),
        (
            rejected,
            BlockContract.GOAL_CLOSED,
            [
                _state(status="SUCCESS", mode="PROOF", proof_level=1),
                _state(status="SUCCESS", mode="PROOF", proof_level=1),
                _state(status="SUCCESS", mode="PROOF", proof_level=1),
            ],
            10,
            "inspect=1 propose=3 validate=3 reason=all_candidates_rejected",
            {"inspect": 1, "propose": 3, "validate": 3},
        ),
        (
            budget,
            BlockContract.GOAL_CLOSED,
            [_state(status="SUCCESS", mode="PROOF", proof_level=1)],
            1,
            "inspect=1 propose=1 validate=1 reason=validation_budget_exhausted",
            {"inspect": 1, "propose": 1, "validate": 1},
        ),
    ]

    for task, contract, execute_results, max_validations, summary, counts in scenarios:
        client = _FakeClient(
            list_commands=[],
            init_state_result=InitStateResult(success=None, error=None),
            execute_results=list(execute_results),
        )
        controller = DeterministicTaskController(
            client=client,
            generator=RuleFirstGenerator(client=client),
            adapters=ValidationAdapterRegistry.default(),
        )
        spec = TaskSpec(
            theory_run_id=f"run-{task.task_id}",
            task=task,
            block_contract=contract,
            max_validations=max_validations,
        )

        result = controller.run(spec)

        assert summary in result.trace_summary
        assert result.trace_counts == counts


def test_adapters_strict_contracts():
    registry = ValidationAdapterRegistry.default()
    # Terminal: execution success but goal not closed -> failed_contract
    r1 = registry.validate(
        ValidationContext(
            block_kind=TERMINAL_PROOF_STEP_BLOCK,
            block_contract=BlockContract.GOAL_CLOSED,
            entry_mode="PROOF",
            entry_proof_level=1,
            execution_result=_state(status="SUCCESS", mode="PROOF", proof_level=1),
        )
    )
    assert r1.status == ValidationStatus.FAILED_CONTRACT

    # Whole proof: proof level decreased -> passed
    r2 = registry.validate(
        ValidationContext(
            block_kind=WHOLE_PROOF_BODY_BLOCK,
            block_contract=BlockContract.SUBPROOF_CLOSED,
            entry_mode="PROOF",
            entry_proof_level=2,
            execution_result=_state(status="SUCCESS", mode="PROOF", proof_level=1),
        )
    )
    assert r2.status == ValidationStatus.PASSED

    # Theorem shell: requires PROOF_COMPLETE + proof_level 0 + non-PROOF mode
    r3 = registry.validate(
        ValidationContext(
            block_kind=THEOREM_SHELL_BLOCK,
            block_contract=BlockContract.THEOREM_CLOSED,
            entry_mode="PROOF",
            entry_proof_level=1,
            execution_result=_state(
                status="PROOF_COMPLETE",
                mode="THEORY",
                proof_level=0,
            ),
        )
    )
    assert r3.status == ValidationStatus.PASSED


def test_top_level_command_contract_is_context_updated():
    from isabelle_repair.localization import contract_for_block_kind

    assert (
        contract_for_block_kind(TOP_LEVEL_COMMAND_BLOCK)
        == BlockContract.CONTEXT_UPDATED
    )


def test_top_level_command_adapter_accepts_theory_context_success():
    registry = ValidationAdapterRegistry.default()
    validation = registry.validate(
        ValidationContext(
            block_kind=TOP_LEVEL_COMMAND_BLOCK,
            block_contract=BlockContract.CONTEXT_UPDATED,
            entry_mode="THEORY",
            entry_proof_level=0,
            execution_result=_state(
                status="SUCCESS",
                mode="THEORY",
                proof_level=0,
            ),
        )
    )

    assert validation.status == ValidationStatus.PASSED


def test_top_level_command_adapter_rejects_proof_mode_leak():
    registry = ValidationAdapterRegistry.default()
    validation = registry.validate(
        ValidationContext(
            block_kind=TOP_LEVEL_COMMAND_BLOCK,
            block_contract=BlockContract.CONTEXT_UPDATED,
            entry_mode="THEORY",
            entry_proof_level=0,
            execution_result=_state(
                status="SUCCESS",
                mode="PROOF",
                proof_level=1,
            ),
        )
    )

    assert validation.status == ValidationStatus.FAILED_CONTRACT
    assert validation.reason == "theory_context_not_restored"


def test_rule_generator_does_not_auto_rewrite_top_level_command():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[],
    )
    generator = RuleFirstGenerator(client=client)
    task = LocalizedTask(
        task_id="task-top-level",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-top-level",
        task=task,
        block_contract=BlockContract.CONTEXT_UPDATED,
    )

    assert generator.generate_candidates(spec, allow_sledgehammer=False) == []


def test_rule_generator_skips_sledgehammer_for_top_level_command():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[],
        sledgehammer=(True, "by metis", _state(status="PROOF_COMPLETE", proof_level=0)),
    )
    generator = RuleFirstGenerator(client=client)
    task = LocalizedTask(
        task_id="task-top-level-sledgehammer",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-top-level-sledgehammer",
        task=task,
        block_contract=BlockContract.CONTEXT_UPDATED,
    )

    assert generator.generate_candidates(spec) == []


def test_repl_engine_can_validate_reviewed_top_level_replacement():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[_state(status="SUCCESS", mode="THEORY", proof_level=0)],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-review-top-level",
        block_kind=TOP_LEVEL_COMMAND_BLOCK,
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
        entry_checkpoint={"mode": "THEORY", "proof_level": 0},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-review-top-level",
        task=task,
        block_contract=BlockContract.CONTEXT_UPDATED,
    )

    validation = engine.validate_candidate(spec, 'definition x where "x = 1"')

    assert validation.status == ValidationStatus.PASSED


def test_repl_engine_fallback_to_next_block_kind():
    # Terminal block candidates all fail execution; fallback whole-proof succeeds.
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="ERROR", error_msg="bad1"),
            _state(status="ERROR", error_msg="bad2"),
            _state(status="ERROR", error_msg="bad3"),
            _state(status="SUCCESS", mode="PROOF", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-4",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by simp",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [
                TERMINAL_PROOF_STEP_BLOCK,
                WHOLE_PROOF_BODY_BLOCK,
            ],
        },
    )
    spec = TaskSpec(
        theory_run_id="run-1",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    result = engine.run(spec)
    assert result.outcome == TaskOutcome.ACCEPTED
    assert "TerminalProofStepBlock:failed" in result.trace_summary
    assert "WholeProofBodyBlock:accepted" in result.trace_summary


def test_repl_engine_fallback_aggregates_trace_counts_and_block_summaries():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="ERROR", error_msg="bad1"),
            _state(status="ERROR", error_msg="bad2"),
            _state(status="ERROR", error_msg="bad3"),
            _state(status="SUCCESS", mode="PROOF", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-fallback-trace",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [
                TERMINAL_PROOF_STEP_BLOCK,
                WHOLE_PROOF_BODY_BLOCK,
            ],
        },
    )
    spec = TaskSpec(
        theory_run_id="run-fallback-trace",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.trace_counts == {"inspect": 2, "propose": 4, "validate": 4}
    assert (
        "TerminalProofStepBlock:failed("
        "inspect=1 propose=3 validate=3 reason=all_candidates_rejected"
    ) in result.trace_summary
    assert (
        "WholeProofBodyBlock:accepted("
        "inspect=1 propose=1 validate=1 selected=by auto source=auto_rule_first"
    ) in result.trace_summary


def test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-structured-engine",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by auto",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [THEOREM_SHELL_BLOCK],
        },
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=THEOREM_SHELL_BLOCK,
                block_contract=BlockContract.THEOREM_CLOSED,
                origin="fallback",
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-structured-engine",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert (
        "TerminalProofStepBlock:failed("
        "inspect=1 propose=3 validate=3 reason=all_candidates_rejected"
    ) in result.trace_summary
    assert (
        "TheoremShellBlock:accepted("
        "inspect=1 propose=1 validate=1 selected=by auto source=auto_rule_first"
    ) in result.trace_summary
    assert result.trace_counts == {"inspect": 2, "propose": 4, "validate": 4}


def test_repl_task_engine_does_not_append_metadata_when_structured_candidates_exist():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-structured-only-engine",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by auto",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [THEOREM_SHELL_BLOCK],
        },
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-structured-only-engine",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.FAILED
    assert "TerminalProofStepBlock:failed" in result.trace_summary
    assert "TheoremShellBlock" not in result.trace_summary


def test_repl_task_engine_structured_candidates_still_use_auto_generator():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-structured-auto",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [THEOREM_SHELL_BLOCK],
        },
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-structured-auto",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.artifact_text == "by simp"
    assert result.selected_generator == "auto_rule_first"
    assert result.attempted_candidates == ["by simp"]
    assert client.execute_calls[0]["tactic"] == "by simp"
    assert result.validation is not None
    assert result.validation.details["candidate_source"] == "auto_rule_first"


def test_repl_engine_primary_path_has_default_fallback_metadata():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-primary-metadata",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "localization_confidence": "high",
        },
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-primary-metadata",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.selected_block_kind == TERMINAL_PROOF_STEP_BLOCK
    assert result.fallback_depth == 0
    assert result.fallback_origin is None
    assert result.fallback_target_contract is None
    assert result.localization_confidence is None


def test_repl_engine_records_selected_fallback_metadata():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="ERROR", error_msg="bad1"),
            _state(status="ERROR", error_msg="bad2"),
            _state(status="ERROR", error_msg="bad3"),
            _state(status="PROOF_COMPLETE", mode="THEORY", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-fallback-metadata",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
        fallback_candidates=[
            RepairBlockCandidate(
                block_kind=TERMINAL_PROOF_STEP_BLOCK,
                block_contract=BlockContract.GOAL_CLOSED,
                origin="primary",
            ),
            RepairBlockCandidate(
                block_kind=THEOREM_SHELL_BLOCK,
                block_contract=BlockContract.THEOREM_CLOSED,
                origin="fallback",
                metadata={"localization_confidence": "medium"},
            ),
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-fallback-metadata",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.selected_block_kind == THEOREM_SHELL_BLOCK
    assert result.fallback_depth == 1
    assert result.fallback_origin == "fallback"
    assert result.fallback_target_contract == BlockContract.THEOREM_CLOSED
    assert result.localization_confidence == "medium"


def test_repl_engine_records_legacy_fallback_metadata():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="ERROR", error_msg="bad1"),
            _state(status="ERROR", error_msg="bad2"),
            _state(status="ERROR", error_msg="bad3"),
            _state(status="SUCCESS", mode="PROOF", proof_level=0),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-legacy-fallback-metadata",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={
            "source_state_id": "s0",
            "fallback_chain": [
                TERMINAL_PROOF_STEP_BLOCK,
                WHOLE_PROOF_BODY_BLOCK,
            ],
            "localization_confidence": "low",
        },
    )
    spec = TaskSpec(
        theory_run_id="run-legacy-fallback-metadata",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.ACCEPTED
    assert result.selected_block_kind == WHOLE_PROOF_BODY_BLOCK
    assert result.fallback_depth == 1
    assert result.fallback_origin == "fallback"
    assert result.fallback_target_contract == BlockContract.SUBPROOF_CLOSED
    assert result.localization_confidence == "low"


def test_repl_engine_stops_when_validation_budget_is_exhausted():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-budget",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="bad original tactic",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
        fallback_candidates=[
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
        ],
    )
    spec = TaskSpec(
        theory_run_id="run-budget",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
        max_validations=1,
    )

    result = engine.run(spec)

    assert result.outcome == TaskOutcome.FAILED
    assert result.validation is not None
    assert result.validation.status == ValidationStatus.INCONCLUSIVE
    assert result.validation.reason == "validation_budget_exhausted"
    assert "validate=1" in result.trace_summary
    assert "validation_budget_exhausted" in result.trace_summary
    assert len(client.execute_calls) == 1
    assert client.execute_calls[0]["tactic"] == "by simp"


def test_repl_engine_validate_candidate_uses_block_adapter():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="SUCCESS", mode="PROOF", proof_level=1),
        ],
    )
    engine = ReplDeterministicTaskEngine(client=client)
    task = LocalizedTask(
        task_id="task-5",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
        block_text="by simp",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-1",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    validation = engine.validate_candidate(spec, "by simp")
    assert validation.status == ValidationStatus.FAILED_CONTRACT
    assert validation.details["candidate_source"] == "review_injected"


def test_repl_engine_can_promote_failed_block_to_review_artifact():
    client = _FakeClient(
        list_commands=[],
        init_state_result=InitStateResult(success=None, error=None),
        execute_results=[
            _state(status="ERROR", error_msg="bad1"),
            _state(status="ERROR", error_msg="bad2"),
            _state(status="ERROR", error_msg="bad3"),
        ],
    )
    engine = ReplDeterministicTaskEngine(
        client=client,
        promote_failed_block_for_review=True,
    )
    task = LocalizedTask(
        task_id="task-promote",
        block_kind=TERMINAL_PROOF_STEP_BLOCK,
        failure_kind=FailureKind.STATEMENT_FAILURE,
        block_text="hence ...",
        entry_checkpoint={"mode": "PROOF", "proof_level": 1},
        metadata={"source_state_id": "s0"},
    )
    spec = TaskSpec(
        theory_run_id="run-1",
        task=task,
        block_contract=BlockContract.GOAL_CLOSED,
    )
    result = engine.run(spec)
    assert result.outcome == TaskOutcome.ESCALATED
    assert result.artifact_text == "hence ..."
    assert result.selected_generator == "review_fallback"
