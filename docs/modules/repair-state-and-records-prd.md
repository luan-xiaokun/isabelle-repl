# Repair State and Records PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`proof-repair-architecture.md`](../architecture/overview.md) for the
  architecture view
- [`theory-repair-run-prd.md`](./theory-repair-run-prd.md) for top-level run
  orchestration
- [`repair-task-engine-prd.md`](./repair-task-engine-prd.md) for task-level
  execution and trace semantics
- [`policy-and-risk-gate-prd.md`](./policy-and-risk-gate-prd.md) for policy
  decision semantics
- [`intervention-and-review-hooks-prd.md`](./intervention-and-review-hooks-prd.md)
  for intervention outcomes and hook response semantics

## Role In Architecture

This document is authoritative for `repair state and records` behavior.

It defines:

- run-level state model
- run-level record object model
- record promotion rules from task-local behavior
- provenance-link model
- common record fields and ordering metadata

It is not authoritative for:

- task-engine action semantics
- policy rule semantics
- hook response semantics
- top-level continuation rule semantics
- shared glossary definitions

## Problem Statement

The current proof-repair design already has strong module-level definitions for:

- failure classification and localization
- repair task engine
- policy and risk gate
- intervention / review hooks
- theory repair run

However, the design still lacks a dedicated record-and-state PRD that unifies
how run-level truth is represented and persisted.

Without this, several risks remain:

- inconsistent record fields across modules
- confusion between task-local trace and run-level records
- unclear semantics for what is record-worthy
- weak provenance links for rerun and rollback planning
- ambiguous meaning of run state transitions

The goal of this document is to define a clear v1 model for repair state and
records that is auditable, stable, and compatible with future rollback,
invalidation, and memory extensions.

## Solution

Build `repair state and records` as a dedicated run-level model layer with:

- explicit run state
- explicit run-level record object types
- shared record metadata contracts
- explicit promotion rules from task-local events to run-level records
- direct operational provenance links between records

The v1 model is intentionally conservative:

- task-local trace remains local by default
- only externally meaningful events are promoted to run-level records
- record history is append-oriented and audit-friendly
- provenance is direct operational linkage rather than full semantic dependency
  reconstruction

## User Stories

1. As a maintainer, I want run-level state and record semantics to be centralized, so that modules do not invent incompatible record shapes.
2. As a maintainer, I want the run state model to be explicit, so that top-level orchestration status is unambiguous.
3. As a maintainer, I want run states to distinguish `active`, `awaiting_review`, `stopped`, and `completed`, so that pause/stop/finish behavior is auditable.
4. As a maintainer, I want `completed` to be represented as a run-level terminal state, so that it is not confused with task-level success.
5. As a maintainer, I want task-local trace and run-level records to be separate layers, so that low-level action noise does not pollute run-level history.
6. As a maintainer, I want record promotion to be rule-based, so that module behavior remains consistent.
7. As a maintainer, I want run-level records to capture externally meaningful decisions, so that rerun and rollback planning is possible.
8. As a maintainer, I want `task record` to summarize each task at run level, so that task outcomes can be reconstructed later.
9. As a maintainer, I want `artifact record` to distinguish repair artifacts and committed placeholder artifacts, so that continuation semantics are honest.
10. As a maintainer, I want `policy decision record` to capture externally meaningful policy outcomes, so that risk gates are explainable.
11. As a maintainer, I want lightweight `policy check` to be distinct from policy decision records, so that logs remain high signal.
12. As a maintainer, I want `intervention record` to capture trigger, response, and final disposition, so that intervention impact is auditable.
13. As a maintainer, I want `continuation record` to be separate from task outcome, so that run progression logic can be analyzed explicitly.
14. As a maintainer, I want each continuation decision to carry clear source context, so that orchestrator, policy, and intervention effects can be separated.
15. As a maintainer, I want run-level records to include stable ordering metadata, so that timeline reconstruction is deterministic.
16. As a maintainer, I want each record to include a schema version, so that future format evolution remains manageable.
17. As a maintainer, I want each record to include theory-run identity, so that records can always be mapped back to the correct run.
18. As a maintainer, I want task-scoped records to include task identity, so that cross-record linkage remains straightforward.
19. As a maintainer, I want theory path and run metadata to live in run metadata rather than duplicated in every record, so that repeated fields do not drift.
20. As a maintainer, I want committed placeholder events to be clearly visible in run-level records, so that placeholder continuation is never misread as genuine repair.
21. As a maintainer, I want accepted repair artifacts to be explicitly visible in run-level records, so that autonomous resolution can be counted accurately.
22. As a maintainer, I want record updates to be append-oriented rather than destructive edits, so that history remains auditable.
23. As a maintainer, I want superseded decisions to be represented explicitly, so that record timelines remain honest.
24. As a maintainer, I want intervention outcomes that fail validation to still be represented, so that rejected intervention paths are visible.
25. As a maintainer, I want run-level records to support direct operational provenance links, so that dependency-aware invalidation is possible later.
26. As a maintainer, I want provenance links to be first-class record relationships, so that dependent outcomes can be traced without ad hoc parsing.
27. As a maintainer, I want provenance scope in v1 to be operational rather than semantic-complete, so that implementation remains tractable.
28. As a maintainer, I want record promotion rules to be deterministic under fixed inputs, so that tests remain stable.
29. As a maintainer, I want the record model to be compatible with `repair authorization mode`, so that run posture can be correlated with outcomes.
30. As a maintainer, I want policy-triggered and task-triggered intervention events to be distinguishable, so that review load can be analyzed correctly.
31. As a maintainer, I want continuation kinds in records to align with v1 continuation model, so that run-state and continuation semantics stay consistent.
32. As a maintainer, I want `awaiting_review` transitions to be recordable, so that paused intervals are explicitly represented.
33. As a maintainer, I want record model constraints to be testable without REPL-heavy end-to-end runs, so that iteration remains fast.
34. As a maintainer, I want record model tests to prioritize external behavior over internal storage layout, so that schema implementation can evolve safely.
35. As a maintainer, I want this records design to leave clear hooks for future rollback and memory modules, so that v1 does not block later expansion.

## Implementation Decisions

- `repair state and records` is a dedicated run-level model layer.
- V1 separates:
  - task-local trace
  - run-level records
- V1 run-level records are object-oriented rather than a flat undifferentiated
  event log.

### Record Object Model

- V1 run-level record objects are:
  - `task record`
  - `artifact record`
  - `policy decision record`
  - `intervention record`
  - `continuation record`
  - `provenance link`
- `task record` summarizes one repair task and links to relevant artifacts,
  policy decisions, interventions, and continuation outcomes.
- `artifact record` distinguishes:
  - `repair artifact`
  - `committed placeholder artifact`
- `policy decision record` represents externally meaningful policy outcomes and
  remains distinct from lightweight policy checks.
- `intervention record` stores trigger source, hook response kind, and result
  disposition.
- `continuation record` stores post-task continuation selection and source.
- `provenance link` stores direct operational dependency between run-level
  records.

### Common Record Fields

- All run-level records must include:
  - `record_id`
  - `record_kind`
  - `schema_version`
  - `theory_run_id`
  - `timestamp`
  - `run_local_sequence_number`
- `task_id` is required for task-scoped records and optional for purely
  run-scoped records.
- Theory path and other run background metadata should be stored in run metadata
  referenced by `theory_run_id`, not duplicated in every record.

### State Model

- V1 run states are:
  - `active`
  - `awaiting_review`
  - `stopped`
  - `completed`
- `completed` is run-level terminal completion of the current theory run and is
  not task-level success.
- `stopped` is run-level terminal early halt.
- `awaiting_review` is a pause state with no automatic progression until review
  resolution is consumed.

### Record Promotion Rules

- Task-local trace events are not promoted by default.
- Run-level promotion includes at least:
  - accepted repair artifacts
  - committed placeholder artifacts
  - record-worthy policy decisions
  - intervention outcomes
  - task terminal outcomes
  - continuation selections
  - provenance links
- `policy check` remains non-record-worthy by default unless it produces an
  externally consequential decision.
- Validation failures are promoted only when they materially influence external
  path decisions.

### Continuation and Outcome Recording

- Task outcome and continuation must be recorded separately.
- V1 continuation kinds in continuation records are:
  - `continue`
  - `rerun_then_continue`
  - `stop`
- Review waiting is represented by run state `awaiting_review`, not a
  continuation kind.
- Continuation records should carry source context sufficient to distinguish
  orchestrator-selected, policy-constrained, and intervention-influenced paths.

### Intervention and Policy Recording

- Intervention records should include final result disposition such as:
  - `consumed`
  - `superseded`
  - `failed_validation`
  - `not_applied`
- Policy records should include:
  - `decision kind`
  - `decision scope`
  - optional `triggered rule ids`
- Human-readable rationale text remains optional in v1.

### Provenance Model

- V1 provenance is direct operational provenance.
- V1 does not require full semantic dependency graph reconstruction.
- Provenance links should support:
  - accepted artifact dependence on prior records
  - continuation decisions linked to antecedent outcomes and gates
  - later invalidation and rerun planning

### Mutability and History Semantics

- Run-level records are append-oriented by default.
- Historical records should not be destructively overwritten.
- Supersession should be represented by new records and explicit linkage/status
  rather than silent in-place mutation.
- ID generation algorithm is not fixed in v1, but IDs must be stable and unique
  within run context.

## Testing Decisions

- A good record/state test validates observable record semantics and state
  transitions rather than storage implementation details.
- Tests should focus on:
  - common record field presence and invariants
  - record object type shape and required link fields
  - run-state transition correctness
  - promotion behavior from task-level events to run-level records
  - separation of task-local trace from run-level records
  - policy check vs policy decision record behavior
  - intervention disposition recording
  - continuation-record generation and alignment with run state
  - provenance-link integrity for direct dependencies
- Prior art for style:
  - existing integration and boundary-oriented tests around run lifecycle and
    replay in this repository's Scala/Python testing patterns
  - contract-first tests used in module PRDs for engine, policy, and hook
    semantics

## Out of Scope

- concrete storage backend selection and implementation
- database schema migration plan
- full rollback execution engine logic
- full semantic dependency graph derivation
- project-wide campaign scheduling records
- UI/dashboard presentation for records
- policy-agent-specific explanation rendering

## Further Notes

- This document is intended to become the single source of truth for run-level
  state and records, replacing cross-module implicit assumptions.
- The v1 scope intentionally prioritizes stable semantics and auditability over
  maximum expressive power.
- Future modules for rollback, invalidation, and memory should consume this
  record model rather than redefining core record concepts.
