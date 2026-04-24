# Proof Repair Agent PRD

Status: System PRD, overview, and document index

Current implementation baseline: v1.5.

The v1.5 documents under `docs/v1_5/` are the authoritative runtime baseline
for current implementation work. The v1 module PRDs remain design context for
module intent, terminology, and future expansion, but they may describe
capabilities beyond the currently implemented subset.

Companion documents:

- [`glossary-and-terminology.md`](./glossary-and-terminology.md) for shared
  terminology and cross-document vocabulary
- [`proof-repair-architecture.md`](./architecture/overview.md) for the
  architecture view
- [`failure-classification-and-localization-prd.md`](./modules/failure-classification-and-localization-prd.md) for failure
  classification, localization, and repair-block design
- [`repair-task-engine-prd.md`](./modules/repair-task-engine-prd.md) for repair task
  engine design
- [`policy-and-risk-gate-prd.md`](./modules/policy-and-risk-gate-prd.md) for policy and
  risk-gate design
- [`intervention-and-review-hooks-prd.md`](./modules/intervention-and-review-hooks-prd.md)
  for intervention and review-hook design
- [`theory-repair-run-prd.md`](./modules/theory-repair-run-prd.md) for top-level
  theory-repair-run orchestration
- [`theory-repair-run-v1_5-prd.md`](./v1_5/prd/theory-repair-run-prd.md)
  for v1.5 runtime-semantic upgrade plan
- [`theory-repair-orchestrator-prd.md`](./modules/theory-repair-orchestrator-prd.md)
  for orchestrator behavior details

## Purpose

This document is the system-level PRD for the proof repair agent.

It is the authoritative document for:

- problem statement
- overall system design direction
- shared system-level definitions
- system-level user stories
- architecture summary
- global non-goals
- document map for the refined module and subsystem PRDs

It is not the authoritative document for detailed module behavior. Module-level
and subsystem-level design details live in the companion PRDs listed above.

## Problem Statement

When Isabelle itself or upstream libraries change, previously working theory
files may stop checking. In practice, these failures are difficult to repair
because:

- the broken parts are not fully known in advance
- fixing one failure may expose new failures
- a locally successful-looking repair may still be semantically dubious
- some repairs are much riskier than others

The goal is not merely to build a one-shot proof patcher. The goal is to build
an interactive, traceable, policy-aware proof repair agent that can:

- discover failures dynamically during theory execution
- localize repair targets to operational repair blocks
- attempt bounded local repair using Isabelle REPL primitives
- distinguish lower-risk and higher-risk repair paths
- request review or intervention when appropriate
- record decisions and provenance for later rerun, rollback, and analysis

The system must also remain honest about uncertainty:

- passing REPL validation is not the same as proving semantic correctness
- placeholder-based continuation is not the same as successful repair
- high-risk statement and non-proof repairs should not be silently accepted

## Overall Solution

Build a proof repair agent on top of the existing Isabelle REPL substrate in
this repository.

The first-version target is a `single-theory theory repair run`, driven by a
`theory repair orchestrator`, with bounded local repair tasks, explicit risk
gating, explicit intervention / review paths, and record-oriented execution.

At a high level, the design has these parts:

- `failure classification and localization`
  - classify newly exposed failures
  - select a repair block with a stable continuation boundary
- `repair task engine`
  - perform bounded task-local repair search on one localized block
- `policy and risk gate`
  - govern action permissions, acceptance gating, and continuation gating
- `intervention / review hooks`
  - support explicit external review and replacement paths
- `repair state and records`
  - preserve task summaries, artifacts, policy decisions, interventions,
    continuation records, and provenance
- `theory repair run`
  - orchestrate the top-level single-theory loop around all of the above

## Shared Core Definitions

### Repair Campaign

A future outer layer that may coordinate multiple theories, dependency orderings,
or project-wide scheduling. This is out of scope for the first core
implementation target.

### Theory Repair Run

A single run over one theory file that repeatedly:

- executes the current working theory snapshot
- discovers the next exposed failure
- classifies and localizes the current repair target
- launches one repair task
- consumes task, policy, and intervention results
- updates records and snapshot
- chooses a continuation path

This is the primary top-level execution unit for v1.

Detailed design lives in
[`theory-repair-run-prd.md`](./modules/theory-repair-run-prd.md).

### Repair Region

A relatively stable enclosing syntactic or textual region, such as:

- theory header / imports
- a top-level non-proof command
- a whole lemma statement plus proof
- a whole proof body
- a sub-proof

### Repair Task Block

The actual operational unit handed to a repair task.

It is:

`the smallest operational text interval in the current working theory snapshot
that can be replaced as a whole and after which the orchestrator can determine
how to resume execution`

Detailed repair-block and localization design lives in
[`failure-classification-and-localization-prd.md`](./modules/failure-classification-and-localization-prd.md).

### Failure Kinds

The current v1 coarse failure kinds are:

- `proof_body_failure`
- `statement_failure`
- `non_proof_command_failure`
- `theory_load_or_header_failure`

These are coarse system-level categories, not the same thing as repair block
kinds.

### Working Theory Snapshot

A logical working copy of the current theory during a repair run.

It includes not just raw text, but also:

- accepted repair artifacts
- committed placeholder artifacts
- user-provided interventions
- dependencies on prior accepted decisions

### Repair Artifact

An externally meaningful task-level result that may affect the working theory
snapshot.

The design currently distinguishes:

- `repair artifact`
- `committed placeholder artifact`

### Continuation Boundary

The principal boundary from which top-level theory execution may reasonably
continue after a repair block has been replaced.

Continuation boundaries are defined by repair block contracts, not by ad hoc
top-level heuristics.

### Intervention / Review Path

An explicit external-decision path used when autonomous execution must not
proceed without external approval, rejection, replacement, placeholder request,
or stop request.

## Architecture Summary

The system architecture is summarized in
[`proof-repair-architecture.md`](./architecture/overview.md).

At a high level:

- the `theory repair run` is the top-level execution unit
- the `theory repair orchestrator` is the controlling component within that run
- `failure classification and localization` selects repair targets
- the `repair task engine` performs bounded local repair
- `policy and risk gate` governs risky actions and acceptances
- `intervention / review hooks` support external control paths
- `repair state and records` preserve run history and provenance
- `persistent strategy memory` is a future extension

The important architectural boundary is that proof repair consumes Isabelle REPL
primitives as a service rather than merging with the REPL implementation itself.

## System-Level User Stories

1. As an Isabelle project maintainer, I want to start a repair run from one broken theory file, so that I can recover after an Isabelle or AFP upgrade.
2. As a proof migration engineer, I want the system to discover broken parts dynamically while executing a theory, so that I do not need a perfect up-front error list.
3. As a maintainer, I want the system to classify proof-body, statement, non-proof, and header/load failures differently, so that repair policy and continuation can reflect risk.
4. As a maintainer, I want the system to localize repair targets to operational repair blocks, so that local repair can happen at the right granularity.
5. As a maintainer, I want proof tasks to use REPL and auxiliary information actions iteratively within a budget, so that bounded local repair search is possible.
6. As a maintainer, I want repair tasks to output at most one externally meaningful artifact plus structured trace and outcome, so that theory-level integration remains consistent.
7. As a maintainer, I want placeholder continuation to be available for proof-body failures when policy allows, so that later failures can still be surfaced.
8. As a maintainer, I want statement-affecting and non-proof repairs to be treated more conservatively than ordinary proof-body repairs, so that risky edits are not silently accepted.
9. As a maintainer, I want policy to control risky actions, risky acceptances, and risky continuation paths, so that automation remains governed rather than unconditional.
10. As a reviewer, I want the system to expose intervention hooks with structured inputs and outputs, so that external review can guide or override risky paths without hidden edits.
11. As a maintainer, I want theory-level continuation to be constrained by repair-block contracts, so that continuation behavior is grounded in block semantics rather than loose heuristics.
12. As a maintainer, I want the top-level run to pause explicitly while waiting for external review, so that review and autonomous continuation do not race each other.
13. As a maintainer, I want the system to preserve structured records for tasks, artifacts, policy decisions, interventions, continuations, and provenance, so that rerun and rollback stay possible later.
14. As a maintainer, I want the system to distinguish autonomous resolution, externally resolved paths, and placeholder-based continuation, so that evaluation remains honest.
15. As a maintainer, I want the first version to remain focused on one theory at a time, so that single-theory orchestration can mature before project-wide scheduling is attempted.
16. As a collaborator, I want the design to be decomposed into focused PRDs with shared terminology, so that the architecture remains understandable as the design gets refined.

## Module And Subsystem Index

### Failure Classification And Localization

Authoritative document:

- [`failure-classification-and-localization-prd.md`](./modules/failure-classification-and-localization-prd.md)

This document covers:

- repair block taxonomy
- block schema
- entry checkpoints
- primary contracts and continuation boundaries
- fallback structure
- acceptance posture hints at the block level

### Repair Task Engine

Authoritative document:

- [`repair-task-engine-prd.md`](./modules/repair-task-engine-prd.md)

This document covers:

- engine runtime
- task controller
- candidate generators
- action families
- task-local search state
- task-local observation store
- artifact model
- local validation
- task outcomes
- task trace vs run-level record bridge

### Policy And Risk Gate

Authoritative document:

- [`policy-and-risk-gate-prd.md`](./modules/policy-and-risk-gate-prd.md)

This document covers:

- policy configuration
- contextual policy decisions
- repair authorization mode
- derived risk posture
- policy checks vs policy decision records
- hard v1 policy decision kinds

### Intervention And Review Hooks

Authoritative document:

- [`intervention-and-review-hooks-prd.md`](./modules/intervention-and-review-hooks-prd.md)

This document covers:

- hook trigger sources
- structured intervention context
- hook response kinds
- approve/reject/replacement/placeholder/stop semantics
- hook-to-record integration

### Theory Repair Run

Authoritative document:

- [`theory-repair-run-prd.md`](./modules/theory-repair-run-prd.md)

This document covers:

- top-level single-theory orchestration
- run states
- contract-constrained continuation selection
- review waiting semantics
- relation between task outcomes and continuation records

### Theory Repair Orchestrator

Authoritative document:

- [`theory-repair-orchestrator-prd.md`](./modules/theory-repair-orchestrator-prd.md)

This document covers:

- top-level control-flow sequencing
- peer-module invocation boundaries
- continuation selection ownership
- run-state transition triggering
- control-point record emission orchestration

### Repair State And Records

Authoritative document:

- [`repair-state-and-records-prd.md`](./modules/repair-state-and-records-prd.md)

This document covers:

- foundational run-level state semantics
- working theory snapshot model
- run-level record object model
- common record fields
- run state model
- record promotion rules
- provenance model

Related areas that still need dedicated design docs:

- continuation decision matrix
- invalidation / rerun / rollback
- persistent strategy memory

### Shared Terminology

Authoritative glossary:

- [`glossary-and-terminology.md`](./glossary-and-terminology.md)

Use this document to align vocabulary across PRDs before introducing new terms.

## Global Non-Goals

The first-version system does not aim to provide:

- full project-wide repair campaign scheduling
- complete rollback engine implementation
- guaranteed semantic correctness of general repairs
- complete persistent strategy memory
- complete cross-version semantic equivalence checking
- a proof that accepted repaired statements preserve original semantics
- finalized module boundaries immune to future refactoring
- broad end-user UX design beyond explicit hook-oriented intervention / review
  paths

## Archived Working Notes

The file [`draft.md`](./archive/draft.md) is retained only as archived design working
notes. It should not be treated as an authoritative design document.

## Further Notes

- This document should stay relatively stable and high-level.
- Detailed subsystem behavior should be refined in the companion PRDs rather
  than re-expanded here.
- When terminology drifts, update the glossary and then update references in
  the subsystem PRDs.
