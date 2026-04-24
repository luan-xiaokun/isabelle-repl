# Theory Repair Run PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`proof-repair-architecture.md`](../architecture/overview.md) for the
  architecture view
- [`failure-classification-and-localization-prd.md`](./failure-classification-and-localization-prd.md) for block and
  continuation-boundary design
- [`repair-task-engine-prd.md`](./repair-task-engine-prd.md) for local task
  execution
- [`policy-and-risk-gate-prd.md`](./policy-and-risk-gate-prd.md) for policy
  design
- [`intervention-and-review-hooks-prd.md`](./intervention-and-review-hooks-prd.md)
  for review and intervention design
- [`theory-repair-orchestrator-prd.md`](./theory-repair-orchestrator-prd.md)
  for orchestrator behavior details
- [`theory-repair-run-state-machine-contract.md`](../v1_5/contracts/theory-repair-run-state-machine-contract.md)
  for executable run-state trigger/invariant contract
- [`theory-repair-run-v1_5-prd.md`](../v1_5/prd/theory-repair-run-prd.md)
  for v1.5 incremental-localizer/snapshot/candidate-source upgrade

## Role In Architecture

This document is authoritative for top-level `theory repair run` behavior.

It defines:

- run-level execution semantics
- run states
- run-level invariants
- run-level boundaries between the orchestrator and peer modules
- run-level relationship to `repair state and records` as a foundational module

It is not authoritative for:

- orchestrator step-by-step control flow details
- repair-task execution semantics
- policy rule semantics
- hook response semantics
- shared glossary definitions

## Problem Statement

The overall proof-repair PRD already defines a `theory repair run` as the main
first-version execution unit. However, after refining block design, task-engine
design, policy design, and hook design, the top-level run now needs a more
explicit PRD of its own.

The central challenge is not merely to "run task after task." The top-level run
must provide a stable semantic container for:

- the working theory snapshot
- a stable run-level state/record model that remains valid across orchestration
  changes
- dynamic exposure of failures during execution
- the orchestrator-driven control flow
- explicit ownership boundaries between controller behavior and state semantics

Without a dedicated top-level run design, the system risks either:

- collapsing too much responsibility into the task engine
- or expressing top-level run behavior as scattered ad hoc logic without stable
  state concepts

The goal of this document is to define the v1 `theory repair run` as the
top-level single-theory process model, while keeping orchestrator behavior
details in a dedicated companion PRD.

## Solution

Build `theory repair run` as a single-theory process model with explicit run
state, explicit run-level records, and explicit boundaries around orchestration
authority.

The v1 theory-run design is based on the following principles:

- the run is the top-level process container
- the orchestrator is the controlling component inside that run
- `repair state and records` is a foundational module inside that run
- peer modules remain distinct from orchestrator internals
- run-level state semantics are explicit and stable
- run-level record semantics are explicit and stable
- intervention / review pause semantics are explicit at run state level

## User Stories

1. As a maintainer, I want to run repair on a single broken theory file, so that I can recover incrementally after an Isabelle or upstream-library change.
2. As a maintainer, I want the top-level run to discover failures dynamically during execution, so that I do not need a complete initial failure list.
3. As a maintainer, I want the run to focus on one currently exposed failure at a time, so that v1 remains understandable and tractable.
4. As a maintainer, I want run semantics to remain stable while orchestration logic evolves, so that we can improve controller behavior without redefining the run model.
5. As a maintainer, I want the run to expose clear module boundaries around classification/localization, engine, policy, hooks, and records, so that responsibilities do not collapse into one module.
6. As a maintainer, I want orchestrator behavior to be documented separately, so that run semantics and control-flow procedure are not conflated.
7. As a maintainer, I want task results to update the working theory snapshot explicitly, so that subsequent execution operates on the accumulated repaired state.
8. As a maintainer, I want accepted repair artifacts to become part of the working theory snapshot, so that later failures are exposed relative to current progress.
9. As a maintainer, I want committed placeholder artifacts to also affect the working theory snapshot, so that the run can continue exposing later failures.
10. As a maintainer, I want task outcome alone not to define run progression semantics, so that control-flow policy can remain explicit and inspectable.
11. As a maintainer, I want continuation semantics to remain contract-constrained at run level, so that successful repairs are not treated as equivalent by default.
12. As a maintainer, I want run semantics to distinguish repair artifacts from committed placeholder artifacts, so that process outcomes remain honest.
13. As a maintainer, I want run semantics to acknowledge localization confidence and fallback context, so that coarse contexts can remain visible to orchestration.
14. As a maintainer, I want run semantics to remain policy-aware without embedding policy rules, so that policy and run responsibilities stay separate.
15. As a maintainer, I want intervention / review to pause the run explicitly, so that external decisions do not race with automatic continuation.
16. As a maintainer, I want a clear run state model, so that the top-level process can be reasoned about independently from task internals.
17. As a maintainer, I want the run to distinguish active execution from waiting-for-review, so that the system remains honest about when it is actually progressing.
18. As a maintainer, I want the run to distinguish completed from stopped, so that records can show whether the theory ran to the end or halted early.
19. As a maintainer, I want run-level continuation decisions to be recorded separately from task outcomes, so that the theory-level process can be reconstructed later.
20. As a maintainer, I want run-level continuation to support direct continue and guarded rerun paths, so that the system can recover from local context uncertainty without redesigning the loop.
21. As a maintainer, I want the run to be able to rerun from a safer continuation anchor after certain accepted repairs, so that local context stability issues can be handled explicitly.
22. As a maintainer, I want the run to support review pauses without pretending they are normal continuation kinds, so that hook behavior and continuation behavior remain cleanly separated.
23. As a maintainer, I want the run to persist theory-run metadata and structured records, so that future rollback and rerun are possible.
24. As a maintainer, I want the run to be record-oriented, so that downstream evaluation can distinguish autonomous resolution, hook-guided resolution, and placeholder-based continuation.
25. As a maintainer, I want the run to remain small enough in v1 that it does not become a multi-failure queueing scheduler, so that single-theory orchestration can mature first.

## Implementation Decisions

- `theory repair run` is the primary v1 process unit.
- V1 theory repair run operates on one theory file at a time.
- The run maintains a `working theory snapshot`.
- The run handles one currently exposed failure at a time.
- V1 does not introduce a simultaneous multi-failure scheduling queue at the
  top level.
- `theory repair orchestrator` is the controlling component within the run.
- `repair state and records` is a run-internal foundational module.
- Its v1 model contains:
  - `working theory snapshot` for executable mutable theory text state
  - `run state` and append-oriented `run-level records` for process semantics
- The run remains semantically valid even if orchestrator internals evolve.
- Detailed orchestrator procedure is defined in
  [`theory-repair-orchestrator-prd.md`](./theory-repair-orchestrator-prd.md).
- Continuation semantics at run level remain
  `block-contract-constrained continuation semantics`.
- V1 continuation kinds are intentionally small:
  - `continue`
  - `rerun_then_continue`
  - `stop`
- Intervention / review is not modeled as a continuation kind in v1.
- Instead, the run enters an explicit review-waiting state when external review
  is pending.
- V1 run states are:
  - `active`
  - `awaiting_review`
  - `stopped`
  - `completed`
- `completed` is a terminal state meaning the current theory run reached the end
  of the theory file without exposing further failures under the current working
  snapshot.
- `completed` is a theory-run terminal state, not a task-level success.
- `completed` does not claim full semantic certainty beyond the current repair
  system's acceptance model.
- `stopped` is a terminal state meaning the run halted before natural
  completion.
- `awaiting_review` is a paused state:
  - no new failure discovery proceeds
  - no new task is started
  - automatic advancement pauses until hook resolution returns
- Hook-triggered review transitions the run into `awaiting_review`.
- Hook results are consumed by the orchestrator according to the orchestrator
  behavior document.
- `continue` means the current theory run keeps advancing on the current updated
  working theory snapshot from the selected continuation boundary.
- `rerun_then_continue` means the run first replays from a safer continuation
  anchor and then resumes forward progress.
- `stop` means the current theory run ceases automatic progression.
- Accepted repair artifacts and committed placeholder artifacts both update the
  working theory snapshot, but they differ in policy semantics, artifact kind,
  and record semantics.
- Working-theory mutation authority remains explicit:
  - task engine proposes artifacts
  - orchestrator selects continuation and integration path
  - repair-state module performs the state update and records provenance
- Task outcome is not identical to continuation choice.
- Continuation should be recorded separately through `continuation records`.
- The run should produce and maintain theory-run metadata separate from task
  records.
- The run should consume and link:
  - task records
  - artifact records
  - policy decision records
  - intervention records
  - continuation records
  - provenance links

## Testing Decisions

- A good theory-run test should assert stable orchestration behavior, state
  transitions, and record semantics rather than internal implementation details.
- Theory-run tests should focus on:
  - run-state transition behavior
  - run semantics independent of orchestrator implementation details
  - transitions between `active`, `awaiting_review`, `stopped`, and `completed`
  - separation between task outcome and continuation semantics
  - correct handling of intervention / review pause semantics
  - correct distinction between repair artifacts and committed placeholder
    artifacts
- Theory-run tests should avoid turning v1 into a full project scheduler test
  harness.
- Theory-run tests should use stubbed orchestrator interactions where possible.
- A smaller number of integration tests may combine the real task engine with
  real snapshot execution to validate end-to-end single-theory flow.

## Out of Scope

- multi-theory campaign scheduling
- simultaneous multi-failure top-level queues
- finalized rollback engine behavior
- full project-level planning
- cross-theory dependency scheduling
- UI/UX for top-level run dashboards
- policy-agent-driven continuation strategy

## Further Notes

- This document intentionally focuses on the top-level single-theory run as a
  separate design concern from task execution and review handling.
- The top-level run should remain orchestrational, record-aware, and explicit
  about pauses, stops, and completion.
