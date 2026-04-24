# Theory Repair Run State-Machine Contract (v1.5)

Status: Acceptance contract for v1.5 run-state semantics

Companion documents:

- [`../prd/theory-repair-run-prd.md`](../prd/theory-repair-run-prd.md)
- [`../../modules/theory-repair-orchestrator-prd.md`](../../modules/theory-repair-orchestrator-prd.md)
- [`../architecture/repair-agent-traceability-matrix.md`](../architecture/repair-agent-traceability-matrix.md)

## State Definitions

| State | Meaning | Terminal |
| --- | --- | --- |
| `active` | run is allowed to discover/select tasks and advance automatically | No |
| `awaiting_review` | run is paused pending review response; no automatic progression | No |
| `stopped` | run terminated early by failure/policy/review stop path | Yes |
| `completed` | run target achieved (configured target-boundary mode) | Yes |
| `finished` | theory-wide run reached natural end (no further localized task) | Yes |

## Trigger Conditions

| From -> To | Trigger | Required side effects |
| --- | --- | --- |
| `active -> awaiting_review` | policy returns `requires_review` for current artifact | emit `review_entered` log; append intervention record with `reason_code` and `allowed_response_kinds`; set `pending_review` |
| `awaiting_review -> active` | `resume_from_review(...)` consumes review response and guard validation completes | emit `review_resolved` log; append intervention resolution record; clear `pending_review` |
| `active -> stopped` | unrecoverable task failure, policy deny path with stop selection, or review response `request_stop` | append continuation record with `stop`; emit `continuation_selected`; emit `run_finished` with `stopped` |
| `active -> completed` | configured target boundary achieved and no next in-boundary failure | emit `run_finished` with `completed` and `terminal_reason=target_boundary_completed` |
| `active -> finished` | theory-wide localizer returns no next task | emit `run_finished` with `finished` and `terminal_reason=theory_wide_finished` |

## Invariants

1. While `state == awaiting_review`, orchestrator must not start a new task.
2. `pending_review` must be non-null iff `state == awaiting_review`.
3. Terminal states (`stopped`, `completed`, `finished`) must not transition to
   non-terminal states in the same run instance.
4. Every accepted artifact integration must have ordered evidence:
   `task -> policy -> optional intervention -> artifact -> continuation ->
   provenance`.
5. Every review resolution must be guard-validated.
6. `completed` is target-achieved completion, not theory-wide completion.
7. `finished` is theory-wide completion.
8. `stopped`, `completed`, and `finished` are mutually exclusive.

## Required Observability Fields

- event logs: `timestamp`, `level`, `event`, `run_id`, `task_id?`, `state`,
  `payload`
- run-level records: monotonic sequence, stable `theory_run_id`,
  `record_kind`, operation payload, and terminal `terminal_reason`
