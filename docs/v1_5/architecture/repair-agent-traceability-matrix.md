# Repair Agent Traceability Matrix (v1.5)

Status: Acceptance traceability for v1.5

## Purpose

Map drawio nodes/edges and PRD requirements to runtime modules and evidence
tests. v1.5 implementation must keep this matrix updated.

## Drawio Node Mapping

| Drawio node | Runtime code module(s) | Evidence tests |
| --- | --- | --- |
| Theory repair orchestrator | `run/orchestrator` | `tests/repair/unit/test_orchestrator.py` |
| Failure classification and localization | `localization/repl` | `tests/repair/unit/test_engine_localization.py` |
| Repair task engine | `repl/minimal`, `engine/controller`, `engine/generator`, `engine/adapters` | `tests/repair/unit/test_engine_localization.py` |
| Policy and risk gate | `policy/rules`, `policy/config`, `policy/config_loader` | `tests/repair/unit/test_policy_and_hook.py` |
| Intervention / review hook | `hooks/static`, `hooks/guard` | `tests/repair/unit/test_policy_and_hook.py` |
| Working theory snapshot | `run/working_snapshot` | `tests/repair/integration/test_single_theory_flow.py` |
| Run-level records | `records/store`, `model/types` | `tests/repair/unit/test_records.py` |

## PRD Requirement Mapping

## Foundation Alignment Evidence

| Foundation concern | Evidence test |
| --- | --- |
| Working snapshot text/patch consistency | `test_snapshot_current_text_uses_same_replacements_as_patch_export` |
| Structured fallback consumed before legacy metadata | `test_repl_task_engine_prefers_structured_fallback_candidates_over_metadata` |
| Structured fallback excludes legacy metadata append | `test_repl_task_engine_does_not_append_metadata_when_structured_candidates_exist` |

## High-Risk And Engine Hardening Evidence

| Concern | Evidence test |
| --- | --- |
| Top-level command validation | `test_top_level_command_adapter_accepts_theory_context_success` |
| Fallback metadata reaches policy | `test_orchestrator_sends_fallback_metadata_to_policy` |
| Fallback acceptance review policy | `test_policy_requires_review_for_fallback_artifact_acceptance` |
| Escalated task does not auto-apply artifact | `test_escalated_task_enters_review_without_applying_artifact` |
| Fallback continuation gating | `test_fallback_rerun_continuation_requires_review_before_continue` |
| Engine validation budget | `test_repl_engine_stops_when_validation_budget_is_exhausted` |
| Engine action-count trace | `test_controller_returns_action_count_trace_details_and_selected_source` |
| Engine fallback trace counts | `test_repl_engine_fallback_aggregates_trace_counts_and_block_summaries` |

| Requirement area | Runtime modules | Evidence tests |
| --- | --- | --- |
| Incremental localization and fallback | `localization/*`, `run/orchestrator` | `test_engine_localization.py` |
| Contract-driven candidate validation | `engine/adapters`, `engine/controller` | `test_engine_localization.py` |
| Review-gated statement failures | `policy/rules`, `run/orchestrator`, `hooks/guard` | `test_acceptance_matrix.py`, `test_life_table_real_review_flow.py` |
| Run-state pause/resume semantics | `run/orchestrator` | `test_orchestrator.py`, `test_acceptance_matrix.py` |
| Records and replay evidence | `records/store`, `run/theory_run` | `test_records.py`, `test_run_repair_once_script.py` |
| Working snapshot text/patch consistency | `run/working_snapshot`, `run/theory_run` | `test_working_snapshot.py`, `test_single_theory_flow.py` |
| Structured localization fallback | `model/types`, `localization/repl`, `repl/minimal` | `test_engine_localization.py` |

## Known Gaps

- Cross-process resume remains out of scope for v1.5.
- Legacy v1 schema compatibility is intentionally not guaranteed.
- Real AFP heavy case still uses test-specific harness classes under
  `tests/repair/integration`; runtime source remains production-only.

## Patch Provenance Mapping

| Patch output field | Record evidence field | Notes |
| --- | --- | --- |
| `entries[].patch_entry_id` | `provenance(linked_to=patch_entries).entries[].patch_entry_id` | Stable patch entry identity |
| `entries[].task_id` | `task.task_id` and `provenance(...).entries[].task_id` | Links patch entry to orchestrated task |
| `entries[].artifact_record_id` | `artifact.record_id` and `provenance(...).entries[].artifact_record_id` | Links patch entry to persisted artifact record |
| `theory_path` | `run_metadata.payload.theory_path` | Patch is scoped to one theory run |
