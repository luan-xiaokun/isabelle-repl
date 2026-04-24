# Theory Repair Orchestrator PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`proof-repair-architecture.md`](../architecture/overview.md) for the
  architecture view
- [`theory-repair-run-prd.md`](./theory-repair-run-prd.md) for run-level
  process semantics
- [`failure-classification-and-localization-prd.md`](./failure-classification-and-localization-prd.md)
  for failure target selection and block contracts
- [`repair-task-engine-prd.md`](./repair-task-engine-prd.md) for task execution
  semantics
- [`policy-and-risk-gate-prd.md`](./policy-and-risk-gate-prd.md) for policy
  gating semantics
- [`intervention-and-review-hooks-prd.md`](./intervention-and-review-hooks-prd.md)
  for intervention behavior
- [`repair-state-and-records-prd.md`](./repair-state-and-records-prd.md) for
  record object and promotion semantics

## Role In Architecture

This document is authoritative for `theory repair orchestrator` behavior.

It defines:

- orchestrator control-flow loop
- component invocation sequencing
- continuation selection procedure ownership
- orchestration of run-state transitions
- orchestration of record emission boundaries

It is not authoritative for:

- run-state semantic definitions
- task-engine internal action semantics
- policy rule definitions
- hook response definitions
- record schema internals

## Problem Statement

The current design has a clear top-level process concept (`theory repair run`)
and clear peer modules (classification/localization, task engine, policy, hook,
records). However, without a dedicated orchestrator PRD, control-flow behavior
is underspecified and tends to leak into unrelated documents.

This creates recurring risks:

- `theory repair run` and `orchestrator` are treated as interchangeable
- control-flow sequencing drifts into run semantics docs
- continuation decisions are described in multiple places with inconsistent
  detail
- module boundaries become blurred during implementation

The goal of this document is to define the orchestrator as a distinct module
inside the theory repair run, with explicit flow ownership and explicit
interfaces to peer modules.

## Solution

Build `theory repair orchestrator` as the control component that drives one
`theory repair run`.

The orchestrator:

- drives the top-level progression loop
- invokes peer modules in a controlled order
- consumes their outputs
- updates run state through defined transitions
- chooses continuation within run-level and contract-level constraints

The orchestrator does not replace peer modules. It coordinates them.

## User Stories

1. As a maintainer, I want a dedicated orchestrator module, so that top-level control flow is not scattered across multiple subsystem docs.
2. As a maintainer, I want run semantics and orchestrator behavior to be separate, so that state definitions do not get entangled with control procedure.
3. As a maintainer, I want the orchestrator to own top-level sequencing, so that module invocation order is explicit and testable.
4. As a maintainer, I want the orchestrator to invoke failure classification and localization explicitly, so that task launch always starts from a structured target.
5. As a maintainer, I want the orchestrator to launch exactly one task for the currently selected target in v1, so that one-failure-at-a-time behavior is preserved.
6. As a maintainer, I want the orchestrator to consume task results without re-implementing task internals, so that task boundaries remain stable.
7. As a maintainer, I want the orchestrator to request policy decisions through explicit interfaces, so that risk gates remain enforceable.
8. As a maintainer, I want the orchestrator to route review-required paths into intervention handling, so that review pauses are explicit.
9. As a maintainer, I want the orchestrator to transition run state into `awaiting_review` when review is pending, so that automatic progression pauses safely.
10. As a maintainer, I want the orchestrator to resume from `awaiting_review` only after hook resolution is consumed, so that racey continuation does not occur.
11. As a maintainer, I want continuation choice to be orchestrator-owned, so that task outcomes are not treated as direct next-step commands.
12. As a maintainer, I want continuation choice to remain constrained by block contracts and artifact semantics, so that orchestrator authority is bounded.
13. As a maintainer, I want the orchestrator to handle `continue`, `rerun_then_continue`, and `stop` paths consistently, so that run progression is predictable.
14. As a maintainer, I want the orchestrator to update the working theory snapshot through explicit integration points, so that state mutation remains auditable.
15. As a maintainer, I want orchestrator-driven record emission points to be explicit, so that run-level records are complete and low-noise.
16. As a maintainer, I want orchestrator behavior to distinguish run termination (`stopped` vs `completed`), so that outcomes remain semantically honest.
17. As a maintainer, I want orchestrator behavior to remain deterministic under fixed module outputs, so that orchestration tests are stable.
18. As a maintainer, I want orchestrator tests to use stubbed peer-module outputs, so that orchestration logic can be validated without heavy integration setup.
19. As a maintainer, I want orchestrator responsibilities to be documented independently from policy rules, so that risk logic can evolve without flow-layer ambiguity.
20. As a maintainer, I want orchestrator responsibilities to be documented independently from hook response semantics, so that intervention contracts remain clear.
21. As a maintainer, I want orchestrator responsibilities to be documented independently from record schemas, so that state model evolution does not force control-flow redesign.
22. As a maintainer, I want orchestrator behavior to remain compatible with future invalidation/rerun/rollback modules, so that v1 does not block later extension.

## Implementation Decisions

- `theory repair orchestrator` is a distinct module inside `theory repair run`.
- `theory repair run` is the process container; orchestrator is its control
  component.
- Orchestrator is responsible for top-level sequencing and transition
  triggering.
- Orchestrator is not responsible for:
  - failure-localization internals
  - task-engine action internals
  - policy rule internals
  - hook-response interpretation internals
  - record-schema internals

### Top-Level Loop Ownership

- The orchestrator owns the v1 one-failure-at-a-time progression loop.
- Under normal progression, it repeatedly:
  - advances execution over the current working theory snapshot
  - acquires the currently exposed failure
  - invokes failure classification and localization
  - launches one repair task
  - consumes task/policy/intervention outputs
  - selects continuation
  - triggers run-state transition and record emission
- Detailed peer-module behavior remains delegated.

### Component Interaction Boundaries

- Classification/localization:
  - orchestrator requests localized target and contract context
  - orchestrator does not perform localization logic itself
- Repair task engine:
  - orchestrator provides task-level inputs
  - orchestrator consumes task outcome/artifact outputs
  - orchestrator does not execute task action loops
- Policy:
  - orchestrator requests policy gating results where required
  - orchestrator consumes policy outcomes
  - orchestrator does not evaluate policy rules directly
- Intervention hook:
  - orchestrator routes review-required paths to hook handling
  - orchestrator transitions run into/out of `awaiting_review`
  - orchestrator does not implement hook response generation
- Repair state and records:
  - orchestrator triggers run-level integration points
  - record schema and promotion internals remain in records module

### Continuation Ownership

- Orchestrator owns continuation selection.
- Continuation selection is constrained by:
  - block-kind contract boundaries
  - artifact kind
  - task outcome
  - relevant policy/intervention outcomes
- V1 continuation kinds:
  - `continue`
  - `rerun_then_continue`
  - `stop`
- `awaiting_review` is a run-state pause, not a continuation kind.

### Run-State Transition Orchestration

- Orchestrator triggers transitions among:
  - `active`
  - `awaiting_review`
  - `stopped`
  - `completed`
- Run-state semantic meaning is defined in run PRD.
- Orchestrator behavior must conform to those semantics.

### Record-Orchestration Responsibilities

- Orchestrator ensures externally meaningful control-flow events are emitted to
  run-level records at the right control points.
- Typical orchestrator-controlled emission points include:
  - task completion integration points
  - continuation-selection results
  - review pause entry/exit points
  - terminal run outcomes
- Record object shapes remain owned by the records PRD.

## Testing Decisions

- A good orchestrator test validates externally visible control behavior under
  fixed peer-module outputs.
- Tests should focus on:
  - one-failure-at-a-time progression behavior
  - component invocation ordering and gating boundaries
  - continuation selection routing behavior
  - review pause and resume behavior
  - run-state transition triggering correctness
  - separation between task outcome and continuation choice
  - control-point record emission triggering
- Orchestrator tests should mostly use stubs/fakes for:
  - classifier/localizer
  - task engine
  - policy
  - intervention hook
  - records sink
- Integration tests may validate real peer-module wiring in a smaller subset.

## Out of Scope

- detailed run-state semantic definitions
- block-level contract semantics
- task-engine action and validation internals
- policy-rule authoring and evaluation internals
- intervention response semantics internals
- record schema definitions
- rollback/invalidation algorithms

## Further Notes

- The orchestrator exists to keep top-level flow ownership explicit without
  collapsing peer modules.
- This PRD should be read together with `theory-repair-run-prd.md`; the run PRD
  defines process semantics, while this document defines control behavior.
