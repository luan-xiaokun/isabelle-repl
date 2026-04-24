from __future__ import annotations

import io
import json
from dataclasses import dataclass

import pytest
from shared.repair_fakes import (
    RuleBasedTaskEngine,
    SequencedHook,
    make_localized_task,
    make_localizer,
)

from isabelle_repair.model import (
    FailureKind,
    InterventionResponse,
    InterventionResponseKind,
    RunMode,
    RunRecordKind,
    RunState,
)
from isabelle_repair.policy import RuleBasedPolicyGate
from isabelle_repair.policy.config import (
    PlaceholderPolicyConfig,
    PlaceholderPolicyMode,
    PolicyConfig,
)
from isabelle_repair.records import InMemoryRecordStore, RunRecordFactory
from isabelle_repair.run import (
    TheoryRepairOrchestrator,
    TheoryRepairRun,
    WorkingTheorySnapshot,
)
from isabelle_repair.run.observability import JsonEventLogger, MultiEventLogger

pytestmark = [pytest.mark.acceptance_gate]


@dataclass(frozen=True)
class AcceptanceCase:
    name: str
    failure_kind: FailureKind
    responses: tuple[InterventionResponse, ...]
    placeholder_mode: PlaceholderPolicyMode = PlaceholderPolicyMode.ALLOW
    expected_state: RunState = RunState.FINISHED
    expected_artifact_kind: str | None = "repair_artifact"
    expected_invalid_reason: bool = False
    expected_policy_reason_codes: tuple[str, ...] = ("task_artifact_evaluation",)
    expected_intervention_reason_codes: tuple[str, ...] = ("policy_requires_review",)


@pytest.mark.parametrize(
    "case",
    [
        AcceptanceCase(
            name="high-risk-approve",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
            ),
            expected_policy_reason_codes=("task_artifact_evaluation",),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
        AcceptanceCase(
            name="high-risk-replacement-valid",
            failure_kind=FailureKind.STATEMENT_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
                    replacement_artifact_text="by (simp add: foo)",
                ),
            ),
            expected_policy_reason_codes=("task_artifact_evaluation",),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
        AcceptanceCase(
            name="high-risk-replacement-invalid",
            failure_kind=FailureKind.STATEMENT_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT
                ),
            ),
            expected_artifact_kind=None,
            expected_invalid_reason=True,
            expected_policy_reason_codes=("task_artifact_evaluation",),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
        AcceptanceCase(
            name="high-risk-placeholder-allow",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER
                ),
            ),
            placeholder_mode=PlaceholderPolicyMode.ALLOW,
            expected_artifact_kind="committed_placeholder_artifact",
            expected_policy_reason_codes=(
                "task_artifact_evaluation",
                "review_placeholder_request",
            ),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
        AcceptanceCase(
            name="high-risk-placeholder-deny",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER
                ),
            ),
            placeholder_mode=PlaceholderPolicyMode.DENY,
            expected_artifact_kind=None,
            expected_policy_reason_codes=(
                "task_artifact_evaluation",
                "review_placeholder_request",
            ),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
        AcceptanceCase(
            name="high-risk-placeholder-requires-review",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            responses=(
                InterventionResponse(
                    kind=InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER
                ),
                InterventionResponse(
                    kind=InterventionResponseKind.APPROVE_CURRENT_ARTIFACT
                ),
            ),
            placeholder_mode=PlaceholderPolicyMode.REQUIRES_REVIEW,
            expected_artifact_kind="committed_placeholder_artifact",
            expected_policy_reason_codes=(
                "task_artifact_evaluation",
                "review_placeholder_request",
            ),
            expected_intervention_reason_codes=(
                "policy_requires_review",
                "placeholder_policy_requires_review",
            ),
        ),
        AcceptanceCase(
            name="high-risk-request-stop",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            responses=(
                InterventionResponse(kind=InterventionResponseKind.REQUEST_STOP),
            ),
            expected_state=RunState.STOPPED,
            expected_artifact_kind=None,
            expected_policy_reason_codes=("task_artifact_evaluation",),
            expected_intervention_reason_codes=("policy_requires_review",),
        ),
    ],
    ids=lambda case: case.name,
)
def test_repair_acceptance_matrix(case: AcceptanceCase):
    run_id = f"matrix-{case.name}"
    task = make_localized_task(
        "task-1",
        failure_kind=case.failure_kind,
        block_kind="TheoremShellBlock",
        block_text='lemma t: "True"',
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-1": RuleBasedTaskEngine.accepted_repair(
                "task-1",
                "by simp",
            ),
        }
    )
    stream = io.StringIO()
    logger = MultiEventLogger(loggers=[JsonEventLogger(run_id=run_id, stream=stream)])
    policy = RuleBasedPolicyGate(
        config=PolicyConfig(
            placeholder=PlaceholderPolicyConfig(mode=case.placeholder_mode)
        )
    )
    run = TheoryRepairRun(
        theory_path="T.thy",
        theory_text="theory T imports Main begin\n",
        localizer=make_localizer([task]),
        engine=engine,
        policy=policy,
        hook=SequencedHook(responses=list(case.responses)),
    )
    final_state, records = run.execute(run_id=run_id, logger=logger)

    assert final_state == case.expected_state
    record_list = records.list_records()
    artifact_records = [
        r for r in record_list if r.record_kind == RunRecordKind.ARTIFACT
    ]
    if case.expected_artifact_kind is None:
        assert not artifact_records
    else:
        assert artifact_records
        assert (
            artifact_records[-1].payload["artifact_kind"] == case.expected_artifact_kind
        )

    policy_records = [r for r in record_list if r.record_kind == RunRecordKind.POLICY]
    assert (
        tuple(rec.payload["reason_code"] for rec in policy_records)
        == case.expected_policy_reason_codes
    )

    intervention_records = [
        r for r in record_list if r.record_kind == RunRecordKind.INTERVENTION
    ]
    if case.expected_intervention_reason_codes:
        assert intervention_records
        resolved = [
            rec
            for rec in intervention_records
            if rec.payload["response_kind"] is not None
        ]
        assert (
            tuple(rec.payload["reason_code"] for rec in resolved)
            == case.expected_intervention_reason_codes
        )
        assert intervention_records[0].payload["allowed_response_kinds"]
    if case.expected_invalid_reason:
        assert intervention_records[-1].payload["invalid_response_reason"] is not None

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    event_names = [row["event"] for row in events]
    assert event_names[0] == "run_started"
    assert event_names[-1] == "run_finished"
    assert all(row["run_id"] == run_id for row in events)
    run_finished = [row for row in events if row["event"] == "run_finished"]
    assert run_finished
    assert run_finished[-1]["payload"]["terminal_reason"] is not None

    terminal_records = [
        r for r in record_list if r.record_kind == RunRecordKind.TERMINAL
    ]
    assert len(terminal_records) == 1
    assert terminal_records[0].payload["final_state"] == final_state.value
    assert terminal_records[0].payload["terminal_reason"] is not None


def test_awaiting_review_resume_acceptance_chain():
    run_id = "matrix-awaiting-resume"
    stream = io.StringIO()
    logger = MultiEventLogger(loggers=[JsonEventLogger(run_id=run_id, stream=stream)])
    record_store = InMemoryRecordStore()
    task = make_localized_task(
        "task-await",
        failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
    )
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-await": RuleBasedTaskEngine.accepted_repair("task-await", "by simp")
        }
    )
    orchestrator = TheoryRepairOrchestrator(
        theory_run_id=run_id,
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
        record_store=record_store,
        record_factory=RunRecordFactory(theory_run_id=run_id),
        snapshot=WorkingTheorySnapshot(theory_path="T.thy", original_text="theory T"),
        logger=logger,
        auto_resolve_review=False,
    )

    first_state = orchestrator.run_until_terminal(max_steps=5)
    assert first_state == RunState.AWAITING_REVIEW
    assert orchestrator.pending_review is not None

    resumed = orchestrator.resume_from_review()
    assert resumed
    assert orchestrator.state == RunState.ACTIVE

    final_state = orchestrator.run_until_terminal(max_steps=5)
    assert final_state == RunState.FINISHED

    intervention_records = [
        r
        for r in record_store.list_records()
        if r.record_kind == RunRecordKind.INTERVENTION
    ]
    assert len(intervention_records) == 2
    assert intervention_records[0].payload["response_kind"] is None
    assert (
        intervention_records[1].payload["response_kind"]
        == InterventionResponseKind.APPROVE_CURRENT_ARTIFACT.value
    )

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    event_names = [row["event"] for row in events]
    assert "review_entered" in event_names
    assert "review_resolved" in event_names


def test_theory_wide_vs_target_boundary_terminal_modes():
    task = make_localized_task("task-mode")
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-mode": RuleBasedTaskEngine.accepted_repair("task-mode", "by simp")
        }
    )
    run = TheoryRepairRun(
        theory_path="Mode.thy",
        theory_text="theory Mode imports Main begin\n",
        localizer=make_localizer([task]),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
    )
    theory_wide_state, _ = run.execute(run_id="mode-theory-wide")
    target_state, target_records = run.execute(
        run_id="mode-target-boundary",
        run_mode=RunMode.TARGET_BOUNDARY,
        target_max_tasks=1,
    )
    assert theory_wide_state == RunState.FINISHED
    assert target_state == RunState.COMPLETED
    terminal = [
        r
        for r in target_records.list_records()
        if r.record_kind == RunRecordKind.TERMINAL
    ]
    assert terminal
    assert terminal[-1].payload["terminal_reason"] == "target_boundary_completed"
