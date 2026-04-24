from __future__ import annotations

import json

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
    LocalizedTask,
    RunRecordKind,
    RunState,
)
from isabelle_repair.policy import RuleBasedPolicyGate
from isabelle_repair.run import TheoryRepairRun


def test_single_theory_repair_success_path():
    tasks = [make_localized_task("task-1")]
    localizer = make_localizer(tasks)
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-1": RuleBasedTaskEngine.accepted_repair("task-1", "by simp"),
        }
    )
    run = TheoryRepairRun(
        theory_path="Simple.thy",
        theory_text='theory Simple imports Main begin\nlemma t: "True"\n',
        localizer=localizer,
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
    )

    final_state, records = run.execute()
    assert final_state == RunState.FINISHED
    assert records.list_records()[0].record_kind == RunRecordKind.RUN_METADATA
    assert records.list_records()[0].payload["theory_path"] == "Simple.thy"
    assert any(r.record_kind == RunRecordKind.ARTIFACT for r in records.list_records())


def test_committed_placeholder_path_when_review_requests_it():
    tasks = [
        make_localized_task(
            "task-2",
            failure_kind=FailureKind.NON_PROOF_COMMAND_FAILURE,
            block_text="definition x where ...",
        )
    ]
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-2": RuleBasedTaskEngine.accepted_repair(
                "task-2",
                "definition x where ...",
            ),
        }
    )
    hook = SequencedHook(
        responses=[
            InterventionResponse(
                kind=InterventionResponseKind.REQUEST_COMMITTED_PLACEHOLDER
            )
        ]
    )
    run = TheoryRepairRun(
        theory_path="T.thy",
        theory_text="theory T imports Main begin\n",
        localizer=make_localizer(tasks),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=hook,
    )

    final_state, records = run.execute()
    assert final_state == RunState.FINISHED
    artifact_records = [
        r for r in records.list_records() if r.record_kind == RunRecordKind.ARTIFACT
    ]
    assert artifact_records
    assert (
        artifact_records[-1].payload["artifact_kind"]
        == "committed_placeholder_artifact"
    )


def test_requires_review_replacement_then_revalidate():
    tasks = [
        make_localized_task(
            "task-3",
            failure_kind=FailureKind.STATEMENT_FAILURE,
            block_kind="TheoremShellBlock",
        )
    ]
    engine = RuleBasedTaskEngine(
        outcomes_by_task_id={
            "task-3": RuleBasedTaskEngine.accepted_repair("task-3", "bad replacement"),
        }
    )
    hook = SequencedHook(
        responses=[
            InterventionResponse(
                kind=InterventionResponseKind.PROVIDE_REPLACEMENT_ARTIFACT,
                replacement_artifact_text="by (simp add: foo)",
            )
        ]
    )
    run = TheoryRepairRun(
        theory_path="T.thy",
        theory_text="theory T imports Main begin\n",
        localizer=make_localizer(tasks),
        engine=engine,
        policy=RuleBasedPolicyGate(),
        hook=hook,
    )

    final_state, records = run.execute()
    assert final_state == RunState.FINISHED
    interventions = [
        r for r in records.list_records() if r.record_kind == RunRecordKind.INTERVENTION
    ]
    assert interventions
    artifacts = [
        r for r in records.list_records() if r.record_kind == RunRecordKind.ARTIFACT
    ]
    assert artifacts[-1].payload["artifact_text"] == "by (simp add: foo)"
    assert artifacts[-1].payload["selected_generator"] == "review_injected"
    assert artifacts[-1].payload["validation_status"] == "passed"


def test_records_jsonl_schema_is_v1_5(tmp_path):
    tasks = [make_localized_task("task-schema")]
    run = TheoryRepairRun(
        theory_path="Schema.thy",
        theory_text="theory Schema imports Main begin\n",
        localizer=make_localizer(tasks),
        engine=RuleBasedTaskEngine(
            outcomes_by_task_id={
                "task-schema": RuleBasedTaskEngine.accepted_repair(
                    "task-schema", "by simp"
                ),
            }
        ),
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
    )
    records_path = tmp_path / "schema.jsonl"
    run.execute(records_path=records_path)
    lines = records_path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert all(json.loads(line)["schema_version"] == "v1.5" for line in lines)


def test_patch_artifacts_written_with_provenance_links(tmp_path):
    tasks = [
        LocalizedTask(
            task_id="task-patch",
            block_kind="TerminalProofStepBlock",
            failure_kind=FailureKind.PROOF_BODY_FAILURE,
            block_text="by auto",
            metadata={"line": 3},
        )
    ]
    run_id = "run-patch"
    records_path = tmp_path / "run-patch.jsonl"
    run = TheoryRepairRun(
        theory_path="Patch.thy",
        theory_text='theory Patch imports Main begin\nlemma t: "True"\nby auto\n',
        localizer=make_localizer(tasks),
        engine=RuleBasedTaskEngine(
            outcomes_by_task_id={
                "task-patch": RuleBasedTaskEngine.accepted_repair(
                    "task-patch",
                    "by simp",
                ),
            }
        ),
        policy=RuleBasedPolicyGate(),
        hook=SequencedHook(),
    )
    final_state, records = run.execute(run_id=run_id, records_path=records_path)
    assert final_state == RunState.FINISHED
    patch_path = tmp_path / f"{run_id}.patch"
    patch_json_path = tmp_path / f"{run_id}.patch.json"
    assert patch_path.is_file()
    assert patch_json_path.is_file()
    assert "+by simp" in patch_path.read_text(encoding="utf-8")

    patch_json = json.loads(patch_json_path.read_text(encoding="utf-8"))
    assert patch_json["entries"]
    assert patch_json["entries"][0]["replacement_text"] == "by simp"

    provenance = [
        r
        for r in records.list_records()
        if r.record_kind == RunRecordKind.PROVENANCE
        and r.payload.get("linked_to") == "patch_entries"
    ]
    assert provenance
    assert provenance[-1].payload["entries"][0]["patch_entry_id"] == "pe-1"
