# Theory Repair Run v1.5 PRD

Status: Approved design baseline for next implementation phase

Companion documents:

- [`../../modules/theory-repair-run-prd.md`](../../modules/theory-repair-run-prd.md)
- [`../../modules/theory-repair-orchestrator-prd.md`](../../modules/theory-repair-orchestrator-prd.md)
- [`../../modules/failure-classification-and-localization-prd.md`](../../modules/failure-classification-and-localization-prd.md)
- [`../../modules/repair-task-engine-prd.md`](../../modules/repair-task-engine-prd.md)
- [`../contracts/theory-repair-run-state-machine-contract.md`](../contracts/theory-repair-run-state-machine-contract.md)
- [`../architecture/repair-agent-traceability-matrix.md`](../architecture/repair-agent-traceability-matrix.md)

## Problem Statement

Current v1 implementation exposes a gap between design intent and real workflow:

- runtime `localizer` is still near one-shot behavior and not a true incremental
  failure-localization component
- snapshot semantics are shallow and do not hold enough execution state to
  support efficient continuation/recovery
- real regression tests can require test-specific localizer/engine behavior,
  which indicates insufficient productized abstractions
- terminal semantics need a clearer split between target-achieved completion and
  full theory-wide completion

The system needs a v1.5 architecture that preserves v1 boundaries while making
real workflow behavior first-class.

## Solution

Implement v1.5 as a runtime-semantic upgrade with three coupled deliverables:

1. Incremental localizer + stronger run snapshot
2. Unified candidate source abstraction for automatic and review-provided
   candidate paths
3. Explicit 5-state run model with separate `completed` and `finished`

Default run mode remains `theory_wide` automatic discovery and progression.
`target_boundary` is optional and intended for regression/experimentation.

## User Stories

1. As a maintainer, I want failure discovery to be incremental, so that the run
   does not re-scan from scratch on every task.
2. As a maintainer, I want snapshot to hold stable execution anchors, so that
   continuation and rerun are deterministic.
3. As a maintainer, I want review-provided candidates to follow the same
   validation contract as automatic candidates, so that acceptance behavior is
   uniform.
4. As a maintainer, I want `STATEMENT_FAILURE` to require review by policy in
   high-risk mode, so that risky transformations remain governed.
5. As a maintainer, I want the run to pause in `awaiting_review` and only
   resume through structured hook resolution, so that autonomous progression and
   external intervention do not race.
6. As a maintainer, I want `completed` and `finished` to be semantically
   distinct, so that target-achieved outcomes and full-theory outcomes are not
   conflated.
7. As a maintainer, I want default mode to stay theory-wide automatic, so that
   repair remains an autonomous process by default.
8. As a maintainer, I want optional target-boundary mode for regression
   workflows, so that narrow real-case validation is possible without changing
   default semantics.
9. As a maintainer, I want run terminal records to include explicit reason
   codes, so that post-run analysis is accurate.
10. As a maintainer, I want snapshot to produce patch artifacts, so that final
    repair outputs are directly usable and auditable.

## Implementation Decisions

- Scope remains single-theory run only.
- `localizer` owns failure discovery; `engine` does not scan theory state on its
  own.
- Incremental progression uses `current_anchor_state_id` and command cursor.
- Context drift fallback is triggered when either:
  - execution indicates context mismatch, or
  - mode/proof-level deviates from snapshot expectations.
- Introduce a unified candidate-source contract used by both:
  - automatic generation path
  - review-injected candidate path
- Keep block-contract validation mandatory for reviewed candidates.
- Run state model becomes:
  - `active`
  - `awaiting_review`
  - `stopped`
  - `completed`
  - `finished`
- Terminal semantics:
  - `completed`: configured target achieved (optional target-boundary mode)
  - `finished`: theory-wide natural completion with no next failure
- Default run mode: `theory_wide`.
- Optional run mode: `target_boundary` (regression/experimental use only).
- Snapshot is responsible for generating final patch outputs:
  - unified diff artifact
  - machine-readable JSON patch artifact
- Records schema is upgraded to `v1.5` and declared incompatible with v1.

## Testing Decisions

- Unit tests cover state-machine rules, snapshot invariants, candidate-source
  contract, and localizer drift fallback behavior.
- Integration tests cover real REPL workflows, including review-injected real
  candidates on known failures.
- Acceptance-gate tests cover end-to-end run semantics and records/log evidence.

## Out of Scope

- multi-theory campaign scheduling
- cross-process resume from records replay
- learning/LLM strategy layer
- production SLA/performance guarantees

## Further Notes

- `target_boundary` does not replace automatic failure discovery; it only
  changes termination boundary for specific workflows.
