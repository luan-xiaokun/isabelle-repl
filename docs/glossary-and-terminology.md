# Glossary and Terminology

Status: Shared vocabulary for proof-repair design documents

Purpose:

- provide a common vocabulary across the proof-repair PRDs
- reduce terminology drift between system-level and module-level documents
- identify which terms are coarse system categories vs fine operational
  categories

This document is the authoritative glossary for the current proof-repair design
set.

## System-Level Units

### Repair Campaign

A future outer-layer effort that may coordinate multiple theories, dependency
orderings, or project-wide scheduling.

This is not the v1 core execution unit.

### Theory Repair Run

The primary v1 top-level execution unit.

A single-theory orchestration loop that repeatedly discovers one currently
exposed failure, localizes a repair target, launches one repair task, consumes
results, updates records and snapshot, and chooses continuation.

### Theory Repair Orchestrator

The controlling component inside a `theory repair run`.

It owns top-level run progression, task launch, and continuation authority, but
it is not the same thing as the `theory repair run` itself.

### Repair Task

A bounded local repair process over one localized repair task block.

The repair task belongs to the repair task engine and is distinct from the
top-level theory repair run.

### Working Theory Snapshot

A logical working copy of the theory under repair.

It reflects accepted repair artifacts, committed placeholder artifacts, and
prior accepted decisions relevant to the current run state.

### Repair State And Records

The shared run-level state layer for a proof-repair execution.

It includes the working theory snapshot, run state, and run-level records such
as task records, artifact records, policy decision records, intervention
records, continuation records, and provenance links.

## Failure And Localization Vocabulary

### Failure Kind

A coarse top-level category for a newly exposed failure.

Current v1 failure kinds:

- `proof_body_failure`
- `statement_failure`
- `non_proof_command_failure`
- `theory_load_or_header_failure`

Failure kinds are system-level routing categories, not the same thing as block
kinds.

### Repair Region

A relatively stable enclosing syntactic or textual region used as a
localization concept.

### Repair Task Block

The operational replacement unit handed to a repair task.

It is the smallest text interval in the current working theory snapshot that can
be replaced as a whole and after which the orchestrator can determine how to
resume execution.

### Block Kind

A more precise operational category for the localized repair block.

Examples include:

- `HeaderImportsBlock`
- `TopLevelCommandBlock`
- `TheoremShellBlock`
- `WholeProofBodyBlock`
- `TerminalProofStepBlock`

Block kinds define contracts, continuation boundaries, fallback structure, and
acceptance posture hints.

## Contract And Validation Vocabulary

### Entry Checkpoint

The block-kind-level schema describing the expected local state at task entry.

### Primary Contract

The principal exit/continuation contract for a block kind.

Examples include:

- `goal_closed`
- `subproof_closed`
- `theorem_closed`
- `context_updated`
- `theory_context_restored`

### Continuation Boundary

The principal boundary from which theory execution may continue after a block is
replaced.

This is constrained by block contract semantics rather than by ad hoc top-level
heuristics.

### Local Validation

Task-level validation performed by the repair task engine.

It checks whether a candidate artifact both executes and satisfies the
block-kind-specific local contract.

### Local Validation Result

The result category of task-local validation.

Current v1 design:

- `passed`
- `failed_execution`
- `failed_contract`
- `failed_timeout`
- optional `inconclusive`

### Theory-Run Validation

Top-level validation based on whether the updated working theory snapshot can
continue meaningfully in the theory repair run.

### Policy Acceptance

The risk-gated acceptance layer that decides whether a locally validated
artifact may enter the active run state.

## Artifact Vocabulary

### Repair Artifact

A genuine externally meaningful repair result produced for a task.

### Committed Placeholder Artifact

A placeholder-based externally meaningful continuation artifact that affects the
working theory snapshot but is not a genuine repair success.

### Exploratory Placeholder

A task-local search aid used inside repair-task search.

An exploratory placeholder is not an externally committed artifact.

### Artifact Kind

A category used by policy and continuation logic to distinguish:

- genuine repair artifacts
- committed placeholder artifacts

## Engine Vocabulary

### Repair Task Engine

The task-scoped local repair subsystem.

### Engine Runtime

The execution-semantics core of the repair task engine.

It owns action execution, task-local state, validation, trace, and budget
enforcement.

### Task Controller

The component inside the repair task engine that chooses the next task action.

It does not own policy gating or top-level continuation.

### Candidate Generator

A proposal backend that produces complete repair candidates when invoked through
`propose_candidate`.

### Task View

The structured controller-visible summary of current task state.

### Task-Local Search State

The runtime-internal state used by the engine while searching within one task.

### Task-Local Observation Store

A task-local structured store of inspect observations and validation-derived
observations used to build proposal context.

## Policy Vocabulary

### Policy Configuration

The static/default layer of policy.

It defines default posture, hard constraints, and the top-level authorization
mode.

### Contextual Policy Decision

A rule-based policy result derived for a concrete task/run context.

Current v1 decision kinds are:

- `allow`
- `deny`
- `requires_review`

### Policy Check

A lightweight policy query that may not rise to the level of a heavyweight
recorded decision.

### Policy Decision Record

A recordable, externally meaningful policy decision event linked to tasks,
artifacts, or continuation.

### Repair Authorization Mode

The top-level overall autonomy/authorization posture for a run.

It behaves more like an edit/acceptance permission mode than like a search
strategy mode.

### Risk Posture

A derived policy posture, primarily based on:

- failure kind
- block kind
- artifact kind

It is not a separate standalone taxonomy in the current design.

## Intervention Vocabulary

### Intervention / Review Hook

The unified external intervention / review boundary used when automated
execution must not proceed autonomously.

### Intervention Context

The structured input provided to an `intervention / review hook`.

It includes the trigger source, reason code, current artifact under review,
relevant validation and policy summaries, and the allowed response space.

### Reason Code

A structured code explaining why intervention / review is being requested.

### Intervention Record

A run-level record of a hook invocation and response.

### Hook Response Kinds

Current core v1 response kinds:

- `approve_current_artifact`
- `reject_current_artifact`
- `provide_replacement_artifact`
- `request_committed_placeholder`
- `request_stop`

## Run-Level Vocabulary

### Continuation Selection

The explicit top-level step that decides how the theory repair run proceeds
after task results have been integrated.

### Contract-Constrained Continuation Selection

The current design principle that continuation choice is constrained by block
kind, contract satisfaction, artifact kind, and related risk information.

### Continuation Record

A run-level record describing how the top-level run proceeded after a task.

### Run State

The top-level state of a theory repair run.

Current v1 run states:

- `active`
- `awaiting_review`
- `stopped`
- `completed`

### Completed

A theory-run terminal state meaning the theory file has been fully processed in
the current run and no further exposed failures remain under the current working
snapshot.

### Stopped

A theory-run terminal state meaning the run halted before natural completion.

### Awaiting Review

A paused run state used when the run is waiting for intervention / review hook
results before proceeding.

## Record Vocabulary

### Task Record

A run-level summary record for one repair task.

### Artifact Record

A run-level record for a repair artifact or committed placeholder artifact.

### Run-Local Sequence Number

A stable per-run ordering index attached to run-level records.

It complements timestamps by giving a deterministic local ordering for the
current theory repair run.

### Provenance Link

A direct operational dependency link between recorded run-level objects.

V1 provenance is operational and local to the execution flow; it is not a full
semantic dependency graph.

## Archived Notes

### Archived Working Notes

Documents explicitly marked as archived working notes are retained for design
history only and are not authoritative sources of current design behavior.
