from __future__ import annotations

import io
import json

from shared.repair_fakes import (
    RuleBasedTaskEngine,
    SequencedHook,
    make_localized_task,
    make_localizer,
)

from isabelle_repair.model import (
    ArtifactKind,
    ContinuationKind,
    FailureKind,
    InterventionResponse,
    InterventionResponseKind,
    RunMode,
    RunRecordKind,
    RunState,
    TaskOutcome,
    TaskResult,
    ValidationResult,
    ValidationStatus,
)
from isabelle_repair.policy import RuleBasedPolicyGate
from isabelle_repair.policy.config import (
    PlaceholderPolicyConfig,
    PlaceholderPolicyMode,
    PolicyConfig,
)
from isabelle_repair.records import InMemoryRecordStore, RunRecordFactory
from isabelle_repair.run import TheoryRepairOrchestrator, WorkingTheorySnapshot
from isabelle_repair.run.observability import JsonEventLogger, MultiEventLogger


def _build_orchestrator(
    *, run_id: str, **kwargs
) -> tuple[TheoryRepairOrchestrator, io.StringIO, InMemoryRecordStore]:
    stream = io.StringIO()
    record_store = InMemoryRecordStore()
    logger = MultiEventLogger(loggers=[JsonEventLogger(run_id=run_id, stream=stream)])
    orch = TheoryRepairOrchestrator(
        theory_run_id=run_id,
        record_store=record_store,
        record_factory=RunRecordFactory(theory_run_id=run_id),
        logger=logger,
        snapshot=WorkingTheorySnapshot(theory_path="T.thy", original_text="theory T"),
        **kwargs,
    )
    return orch, stream, record_store


def test_finished_when_no_more_localized_tasks():
    orchestrator, stream, _ = _build_orchestrator(
        run_id="run-1",
        localizer=make_localizer([]),
        engine=RuleBasedTaskEngine(),
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
    )

    final_state = orchestrator.run_until_terminal()
    assert final_state == RunState.FINISHED

    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert rows[0]["event"] == "run_started"
    assert rows[-1]["event"] == "run_finished"
    assert rows[-1]["run_id"] == "run-1"
    assert rows[-1]["payload"]["terminal_reason"] == "theory_wide_finished"


def test_requires_review_then_stop_from_hook():
    task = make_localized_task(
        "task-1",
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-1": RuleBasedTaskEngine.accepted_repair("task-1", "definition x"),
        }
    )
    hook = SequencedHook(
        responses=[
            InterventionResponse(kind=InterventionResponseKind.REQUEST_STOP),
        ]
    )
    orchestrator, stream, record_store = _build_orchestrator(
        run_id="run-2",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=hook,
    )
    final_state = orchestrator.run_until_terminal()

    assert final_state == RunState.STOPPED
    continuation = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.CONTINUATION
    ]
    assert continuation[-1].payload["continuation_kind"] == ContinuationKind.STOP.value

    rows = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert any(row["event"] == "review_entered" for row in rows)
    assert any(row["event"] == "review_resolved" for row in rows)


def test_accepted_artifact_can_choose_rerun_then_continue():
    task = make_localized_task("task-3")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-3": RuleBasedTaskEngine.accepted_repair(
                "task-3",
                "by simp",
                requires_rerun=True,
            ),
        }
    )
    from isabelle_repair.hooks import StaticReviewHook
    from isabelle_repair.model import InterventionResponse

    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-3",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=StaticReviewHook(
            response_factory=lambda ctx: InterventionResponse(  # noqa: ARG005
                kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
            )
        ),
    )

    final_state = orchestrator.run_until_terminal()
    assert final_state == RunState.FINISHED
    continuation = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.CONTINUATION
    ]
    assert (
        continuation[-1].payload["continuation_kind"]
        == ContinuationKind.RERUN_THEN_CONTINUE.value
    )
    evidence_order = [
        record.record_kind
        for record in record_store.list_records()
        if record.task_id == "task-3"
        and record.record_kind
        in {
            RunRecordKind.TASK,
            RunRecordKind.POLICY,
            RunRecordKind.ARTIFACT,
            RunRecordKind.CONTINUATION,
            RunRecordKind.PROVENANCE,
        }
    ]
    assert evidence_order[-5:] == [
        RunRecordKind.TASK,
        RunRecordKind.POLICY,
        RunRecordKind.ARTIFACT,
        RunRecordKind.CONTINUATION,
        RunRecordKind.PROVENANCE,
    ]


def test_requires_review_enters_awaiting_review_until_resume():
    task = make_localized_task(
        "task-4",
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-4": RuleBasedTaskEngine.accepted_repair("task-4", "by simp"),
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-4",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                )
            ]
        ),
        auto_resolve_review=False,
    )

    paused_state = orchestrator.run_until_terminal(max_steps=5)
    assert paused_state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None

    resumed = orchestrator.resume_from_review()
    assert resumed
    assert orchestrator.state == RunState.ACTIVE
    assert orchestrator.snapshot.applied_artifacts == [(ArtifactKind.REPAIR, "by simp")]
    artifact_records = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.ARTIFACT
    ]
    assert len(artifact_records) == 1

    final_state = orchestrator.run_until_terminal(max_steps=5)
    assert final_state == RunState.FINISHED
    intervention_records = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.INTERVENTION
    ]
    assert len(intervention_records) >= 2
    assert intervention_records[0].payload["response_kind"] is None
    assert (
        intervention_records[1].payload["response_kind"]
        == InterventionResponseKind.APPROVE_CURRENT_ARTIFACT.value
    )


def test_invalid_review_response_is_rejected_safely():
    task = make_localized_task(
        "task-5",
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-5": RuleBasedTaskEngine.accepted_repair("task-5", "by simp"),
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-5",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(kind=InterventionResponseKind.REQUEST_STOP),
            ]
        ),
        auto_resolve_review=False,
    )

    paused_state = orchestrator.run_until_terminal(max_steps=5)
    assert paused_state == RunState.AWAITING_REVIEW
    resumed = orchestrator.resume_from_review(
        InterventionResponse(kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT)
    )
    assert not resumed
    assert orchestrator.state == RunState.ACTIVE

    intervention_records = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.INTERVENTION
    ]
    assert intervention_records
    assert intervention_records[-1].payload["invalid_response_reason"] is not None


def test_placeholder_policy_can_deny_review_requested_placeholder():
    task = make_localized_task(
        "task-6",
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
        block_text='definition x where "x = 0"',
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-6": RuleBasedTaskEngine.accepted_repair(
                "task-6", 'definition x where "x = 0"'
            ),
        }
    )
    policy = RuleBasedPolicyGate(
        config=PolicyConfig(
            placeholder=PlaceholderPolicyConfig(mode=PlaceholderPolicyMode.DENY)
        )
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-6",
        localizer=make_localizer([task]),
        engine=engine,
        policy=policy,
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER
                )
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)
    assert final_state == RunState.FINISHED
    artifacts = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.ARTIFACT
    ]
    assert not artifacts


def test_target_boundary_mode_completes_with_terminal_reason():
    task = make_localized_task("task-boundary")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-boundary": RuleBasedTaskEngine.accepted_repair(
                "task-boundary", "by simp"
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-boundary",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
        run_mode=RunMode.TARGET_BOUNDARY,
        target_max_tasks=1,
    )
    final_state = orchestrator.run_until_terminal(max_steps=5)
    assert final_state == RunState.COMPLETED
    terminal = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.TERMINAL
    ]
    assert terminal
    assert terminal[-1].payload["terminal_reason"] == "target_boundary_completed"


def test_orchestrator_sends_fallback_metadata_to_policy():
    task = make_localized_task("task-fallback-policy")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-fallback-policy": RuleBasedTaskEngine.accepted_repair(
                "task-fallback-policy",
                "by simp",
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-fallback-policy",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                )
            ]
        ),
        auto_resolve_review=False,
    )

    paused_state = orchestrator.run_until_terminal(max_steps=5)

    assert paused_state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None
    policy_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.POLICY
    ]
    assert policy_records[0].payload["triggered_rule_ids"] == [
        "fallback_acceptance_requires_review"
    ]
    task_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.TASK
    ]
    assert task_records[0].payload["selected_block_kind"] == "TheoremShellBlock"
    assert task_records[0].payload["fallback_depth"] == 1
    assert task_records[0].payload["fallback_origin"] == "fallback"


def test_orchestrator_records_fallback_metadata_for_auto_approved_artifact():
    task = make_localized_task("task-fallback-audit")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-fallback-audit": RuleBasedTaskEngine.accepted_repair(
                "task-fallback-audit",
                "by simp",
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-fallback-audit",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                )
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)

    assert final_state == RunState.FINISHED
    task_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.TASK
    ]
    artifact_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.ARTIFACT
    ]
    assert task_records[0].payload["selected_block_kind"] == "TheoremShellBlock"
    assert task_records[0].payload["fallback_depth"] == 1
    assert task_records[0].payload["fallback_origin"] == "fallback"
    assert artifact_records[0].payload["selected_block_kind"] == "TheoremShellBlock"
    assert artifact_records[0].payload["fallback_depth"] == 1
    assert artifact_records[0].payload["fallback_origin"] == "fallback"


def test_escalated_task_enters_review_without_applying_artifact():
    task = make_localized_task(
        "task-escalated",
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-escalated": TaskResult(
                task_id="task-escalated",
                outcome=TaskOutcome.ESCALATED,
                artifact_kind=ArtifactKind.REPAIR,
                artifact_text="by sorry",
                validation=ValidationResult(
                    status=ValidationStatus.INCONCLUSIVE,
                    reason="auto_candidates_exhausted_promote_review",
                ),
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-escalated",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
        auto_resolve_review=False,
    )

    state = orchestrator.run_until_terminal(max_steps=5)

    assert state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None
    assert (
        orchestrator.pending_review.context.reason_code
        == "task_escalated_requires_review"
    )
    assert orchestrator.pending_review.context.allowed_response_kinds == [
        InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
        InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER,
        InterventionResponseKind.REQUEST_STOP,
    ]
    artifacts = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.ARTIFACT
    ]
    assert not artifacts
    assert orchestrator.snapshot.applied_artifacts == []


def test_escalated_task_applies_only_review_replacement_without_gate():
    class FailingPolicyGate:
        def decide(self, context):  # noqa: ANN001, ARG002
            raise AssertionError("_gate_or_review should not run for escalated tasks")

    task = make_localized_task(
        "task-escalated-reviewed",
        failure_kind=FailureKind.PROOF_BODY_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-escalated-reviewed": TaskResult(
                task_id="task-escalated-reviewed",
                outcome=TaskOutcome.ESCALATED,
                artifact_kind=ArtifactKind.REPAIR,
                artifact_text="by sorry",
                validation=ValidationResult(
                    status=ValidationStatus.INCONCLUSIVE,
                    reason="auto_candidates_exhausted_promote_review",
                ),
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-escalated-reviewed",
        localizer=make_localizer([task]),
        engine=engine,
        policy=FailingPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
                    replacement_artifact_text="by reviewed",
                )
            ]
        ),
    )

    state = orchestrator.run_until_terminal(max_steps=5)

    assert state == RunState.FINISHED
    assert orchestrator.snapshot.applied_artifacts == [
        (ArtifactKind.REPAIR, "by reviewed")
    ]
    artifact_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.ARTIFACT
    ]
    assert len(artifact_records) == 1
    assert artifact_records[0].payload["artifact_text"] == "by reviewed"


def test_fallback_rerun_continuation_requires_review_before_continue():
    task = make_localized_task("task-continuation-gate")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-continuation-gate": RuleBasedTaskEngine.accepted_repair(
                "task-continuation-gate",
                "by simp",
                requires_rerun=True,
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-continuation-gate",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)

    assert final_state == RunState.FINISHED
    policy_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.POLICY
    ]
    assert any(
        record.payload["reason_code"] == "continuation_gating"
        and record.payload["scope"] == "continuation_gating"
        and record.payload["triggered_rule_ids"]
        == ["fallback_continuation_requires_review"]
        for record in policy_records
    )
    continuation_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.CONTINUATION
    ]
    assert continuation_records[-1].payload["continuation_kind"] == (
        ContinuationKind.RERUN_THEN_CONTINUE.value
    )


def test_fallback_rerun_continuation_pause_writes_no_continuation_before_review():
    class ContinuationOnlyPolicy:
        def decide(self, context):  # noqa: ANN001
            from isabelle_repair.model import (
                PolicyDecision,
                PolicyDecisionKind,
                PolicyDecisionScope,
            )

            if context.reason_code == "continuation_gating":
                assert context.continuation_kind == ContinuationKind.RERUN_THEN_CONTINUE
                assert context.fallback_depth == 1
                assert context.fallback_origin == "fallback"
                assert context.block_kind == "TheoremShellBlock"
                assert context.artifact_kind == ArtifactKind.REPAIR
                assert context.failure_kind == FailureKind.PROOF_BODY_FAILURE
                return PolicyDecision(
                    kind=PolicyDecisionKind.REQUIRES_REVIEW,
                    scope=PolicyDecisionScope.CONTINUATION_GATING,
                    triggered_rule_ids=["fallback_continuation_requires_review"],
                )
            return PolicyDecision(
                kind=PolicyDecisionKind.ALLOW,
                scope=PolicyDecisionScope.ARTIFACT_ACCEPTANCE,
                triggered_rule_ids=["default_allow"],
            )

    task = make_localized_task("task-continuation-pause")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-continuation-pause": RuleBasedTaskEngine.accepted_repair(
                "task-continuation-pause",
                "by simp",
                requires_rerun=True,
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-continuation-pause",
        localizer=make_localizer([task]),
        engine=engine,
        policy=ContinuationOnlyPolicy(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                )
            ]
        ),
        auto_resolve_review=False,
    )

    paused_state = orchestrator.run_until_terminal(max_steps=5)

    assert paused_state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None
    assert (
        orchestrator.pending_review.context.reason_code
        == "continuation_policy_requires_review"
    )
    continuation_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.CONTINUATION
    ]
    assert continuation_records == []

    resumed = orchestrator.resume_from_review()

    assert resumed
    continuation_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.CONTINUATION
    ]
    assert continuation_records[-1].payload["continuation_kind"] == (
        ContinuationKind.RERUN_THEN_CONTINUE.value
    )


def test_continuation_review_stop_does_not_finalize_deferred_continuation():
    task = make_localized_task("task-continuation-stop")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-continuation-stop": RuleBasedTaskEngine.accepted_repair(
                "task-continuation-stop",
                "by simp",
                requires_rerun=True,
                selected_block_kind="TheoremShellBlock",
                fallback_depth=1,
                fallback_origin="fallback",
            )
        }
    )
    orchestrator, _, record_store = _build_orchestrator(
        run_id="run-continuation-stop",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(
            responses=[
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
                InterventionResponse(kind=InterventionResponseKind.REQUEST_STOP),
            ]
        ),
    )

    final_state = orchestrator.run_until_terminal(max_steps=5)

    assert final_state == RunState.STOPPED
    continuation_records = [
        record
        for record in record_store.list_records()
        if record.record_kind == RunRecordKind.CONTINUATION
    ]
    assert [record.payload["continuation_kind"] for record in continuation_records] == [
        ContinuationKind.STOP.value
    ]
