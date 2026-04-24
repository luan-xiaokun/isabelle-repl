from __future__ import annotations

import pytest

from isabelle_repair.model import ArtifactKind
from isabelle_repair.run import WorkingTheorySnapshot


def test_snapshot_anchor_is_monotonic():
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text="theory T")
    snapshot.set_anchor(
        state_id="s0",
        command_cursor=0,
        mode="THEORY",
        proof_level=0,
    )
    snapshot.set_anchor(
        state_id="s1",
        command_cursor=2,
        mode="PROOF",
        proof_level=1,
    )
    with pytest.raises(ValueError, match="monotonic"):
        snapshot.set_anchor(
            state_id="s-bad",
            command_cursor=1,
            mode="PROOF",
            proof_level=1,
        )


def test_snapshot_replacements_and_metadata():
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text="theory T")
    snapshot.set_anchor(
        state_id="s0",
        command_cursor=1,
        mode="PROOF",
        proof_level=1,
    )
    snapshot.set_last_failure_digest({"reason": "x"})
    snapshot.apply_artifact(
        ArtifactKind.REPAIR,
        "by simp",
        task_id="task-1",
        command_line=12,
        original_text="by auto",
    )
    assert snapshot.replacement_for_line(12) == "by simp"
    metadata = snapshot.to_metadata()
    assert metadata["anchor_state_id"] == "s0"
    assert metadata["command_cursor"] == 1
    assert metadata["applied_replacement_count"] == 1
    assert metadata["last_failure_digest"] == {"reason": "x"}


def test_snapshot_patch_exports_are_deterministic():
    source = 'theory T imports Main begin\nlemma t: "True"\nby auto\n'
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text=source)
    snapshot.apply_artifact(
        ArtifactKind.REPAIR,
        "by simp",
        task_id="task-1",
        command_line=3,
        original_text="by auto",
    )
    snapshot.attach_artifact_record_id(task_id="task-1", record_id="rec-1")
    diff_1 = snapshot.export_unified_diff()
    diff_2 = snapshot.export_unified_diff()
    assert diff_1 == diff_2
    assert "-by auto" in diff_1
    assert "+by simp" in diff_1

    patch_json = snapshot.export_json_patch()
    assert patch_json["entries"][0]["patch_entry_id"] == "pe-1"
    links = snapshot.export_patch_provenance_links()
    assert links[0]["artifact_record_id"] == "rec-1"


def test_snapshot_current_text_uses_same_replacements_as_patch_export():
    source = 'theory T imports Main begin\nlemma t: "True"\nby auto\n'
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text=source)

    snapshot.apply_artifact(
        ArtifactKind.REPAIR,
        "by simp",
        task_id="task-1",
        command_line=3,
        original_text="by auto",
    )

    assert snapshot.current_text == (
        'theory T imports Main begin\nlemma t: "True"\nby simp\n'
    )
    assert "(* applied:" not in snapshot.current_text
    assert snapshot.export_json_patch()["entries"][0]["replacement_text"] == "by simp"
    assert "+by simp" in snapshot.export_unified_diff()


def test_snapshot_rejects_artifact_without_command_line():
    snapshot = WorkingTheorySnapshot(theory_path="T.thy", original_text="theory T\n")

    with pytest.raises(ValueError, match="command_line"):
        snapshot.apply_artifact(
            ArtifactKind.REPAIR,
            "by simp",
            task_id="task-no-line",
        )

    assert snapshot.applied_artifacts == []
    assert snapshot.applied_replacements == []
    assert snapshot.current_text == "theory T\n"
