from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    next_heading = rest.find("\n## ")
    if next_heading == -1:
        return rest
    return rest[:next_heading]


def test_top_level_prd_declares_v1_5_current_baseline():
    text = (ROOT / "docs/proof-repair-agent-prd.md").read_text(encoding="utf-8")
    assert "Current implementation baseline: v1.5" in text
    assert "v1 module PRDs remain design context" in text


def test_v1_5_readme_declares_authoritative_runtime_baseline():
    text = (ROOT / "docs/v1_5/README.md").read_text(encoding="utf-8")
    assert "authoritative runtime baseline" in text
    assert "implemented subset" in text


def test_traceability_matrix_tracks_foundation_alignment():
    text = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert "Working snapshot text/patch consistency" in text
    assert "Structured localization fallback" in text


def test_localization_prd_declares_implemented_v1_5_subset():
    text = (
        ROOT / "docs/modules/failure-classification-and-localization-prd.md"
    ).read_text(encoding="utf-8")
    section = _section(text, "## Implemented v1.5 Subset")
    assert "TerminalProofStepBlock" in section
    assert "WholeProofBodyBlock" in section
    assert "TheoremShellBlock" in section
    assert "TopLevelCommandBlock" in section
    assert "context_updated" in section
    assert "Autonomous generation remains conservative" in section


def test_repair_engine_prd_declares_implemented_v1_5_subset():
    text = (ROOT / "docs/modules/repair-task-engine-prd.md").read_text(encoding="utf-8")
    section = _section(text, "## Implemented v1.5 Subset")
    assert "deterministic inspect/propose/validate loop" in section
    assert "rule-first generator" in section
    assert "review-injected candidates" in section
    assert "block-kind-aware validation adapters" in section
    assert "compact task trace summaries" in section
    assert "action-runtime design remains future work" in section


def test_traceability_matrix_names_new_foundation_evidence_tests():
    text = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert "test_snapshot_current_text_uses_same_replacements_as_patch_export" in text
    assert (
        "test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata"
        in text
    )
    assert (
        "test_repl_task_engine_does_not_append_metadata_when_structured_candidates_exist"
        in text
    )


def test_batch_4_6_docs_name_high_risk_and_engine_evidence():
    traceability = (
        ROOT / "docs/v1_5/architecture/repair-agent-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    localization = (
        ROOT / "docs/modules/failure-classification-and-localization-prd.md"
    ).read_text(encoding="utf-8")
    engine = (ROOT / "docs/modules/repair-task-engine-prd.md").read_text(
        encoding="utf-8"
    )
    policy = (ROOT / "docs/modules/policy-and-risk-gate-prd.md").read_text(
        encoding="utf-8"
    )

    assert "TopLevelCommandBlock" in localization
    assert (
        "test_top_level_command_adapter_accepts_theory_context_success" in traceability
    )
    assert "test_orchestrator_sends_fallback_metadata_to_policy" in traceability
    assert (
        "test_policy_requires_review_for_fallback_artifact_acceptance" in traceability
    )
    assert "test_escalated_task_enters_review_without_applying_artifact" in traceability
    assert (
        "test_fallback_rerun_continuation_requires_review_before_continue"
        in traceability
    )
    assert "test_repl_engine_stops_when_validation_budget_is_exhausted" in traceability
    assert (
        "test_controller_returns_action_count_trace_details_and_selected_source"
        in traceability
    )
    assert "budgeted deterministic trace" in engine
    assert "trace_counts" in engine
    assert "fallback and continuation gating" in policy
