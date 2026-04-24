# Intervention and Review Hooks PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`policy-and-risk-gate-prd.md`](./policy-and-risk-gate-prd.md) for policy and
  risk-gate design
- [`repair-task-engine-prd.md`](./repair-task-engine-prd.md) for task-engine
  execution semantics

## Role In Architecture

This document is authoritative for `intervention / review hook` behavior.

It defines:

- hook trigger sources
- intervention context
- hook response kinds
- approval, rejection, replacement, placeholder, and stop semantics
- intervention recording expectations

It is not authoritative for:

- policy configuration semantics
- task-engine execution semantics
- top-level theory-run continuation semantics
- shared glossary definitions

## Problem Statement

The proof-repair system explicitly intends to support structured external
intervention / review. However, without a dedicated hook design, review paths
remain underspecified:

- when review is triggered
- what information is shown to the reviewer
- what kinds of responses are allowed
- how those responses interact with runtime validation, policy gates, and
  continuation

This gap creates several risks:

- policy and intervention may collapse into one concept
- review may become an unstructured side channel
- hook outputs may overstep runtime or orchestrator boundaries
- records may fail to show how external intervention changed the run

The goal of this document is to define a v1 `intervention / review hook`
interface that is strong enough to support meaningful reviewer control without
turning the hook into a universal imperative escape hatch.

## Solution

Build `intervention / review hook` as the unified external-decision boundary for
cases where the automated system cannot or should not proceed autonomously.

The v1 hook design is based on the following principles:

- hooks are invoked through explicit intervention / review paths
- hooks consume structured context
- hooks return structured response kinds
- hooks do not directly mutate hidden internal state
- hooks do not bypass runtime execution semantics
- hooks do provide genuine correction power by allowing replacement artifacts or
  path-changing requests

The design supports at least two v1 trigger sources:

- `policy-triggered`
- `task-triggered`

`run-triggered` hooks remain possible, but are deferred until the theory-run
design is finalized more fully.

## User Stories

1. As a maintainer, I want the repair system to expose a structured intervention / review boundary, so that risky situations can be handled without hidden state edits.
2. As a reviewer, I want to know why I am being asked to review something, so that I can make informed decisions quickly.
3. As a reviewer, I want to receive structured context rather than raw internal engine state, so that the hook contract stays usable and stable.
4. As a maintainer, I want hooks to be triggered both by policy and by task-level explicit requests, so that review is not restricted to one mechanism.
5. As a maintainer, I want policy-triggered review to be distinguishable from task-triggered intervention, so that the system can record why external review happened.
6. As a reviewer, I want to see the current artifact under review, so that I know what exactly I am approving, rejecting, or replacing.
7. As a reviewer, I want to see validation summaries and policy summaries, so that I understand the technical and risk context of the current request.
8. As a reviewer, I want a reason code explaining why intervention / review is needed, so that I do not have to reconstruct the cause from raw trace.
9. As a maintainer, I want hook response kinds to be explicitly limited, so that hook behavior remains predictable and testable.
10. As a reviewer, I want to be able to approve the current artifact, so that a high-risk but otherwise valid path can proceed.
11. As a reviewer, I want to be able to reject the current artifact, so that the system does not accept something I consider unacceptable.
12. As a reviewer, I want to be able to provide a replacement artifact, so that I can actively repair the current situation rather than merely approve or reject.
13. As a reviewer, I want to be able to request committed placeholder continuation, so that the run can keep moving when true repair is not yet practical.
14. As a reviewer, I want to be able to request stop, so that unsafe or low-value automatic continuation can be halted explicitly.
15. As a maintainer, I want hook-provided replacement artifacts to go through normal validation, so that intervention does not bypass execution semantics.
16. As a maintainer, I want hook approval to satisfy review gating without overriding hard runtime constraints, so that the hook does not become an unrestricted superuser interface.
17. As a maintainer, I want hook rejection to reject the current artifact only, so that rejecting one proposal does not automatically terminate the whole path.
18. As a maintainer, I want request-stop semantics to target the current automated path, so that it remains distinct from simply rejecting one artifact.
19. As a maintainer, I want "continue searching" not to require a separate hook response kind, so that hooks do not start owning controller sequencing.
20. As a maintainer, I want committed-placeholder requests to remain distinct from stop requests, so that placeholder continuation retains its own semantics.
21. As a maintainer, I want hook responses to become structured records, so that intervention remains auditable and provenance-aware.
22. As a reviewer, I want my intervention decisions to appear in the run record, so that later analysis can distinguish autonomous resolution from external resolution.
23. As a maintainer, I want hook behavior to remain compatible with humans, scripts, and future lightweight external reviewer agents, so that the interface is future-proof.
24. As a maintainer, I want hook behavior to be testable through structured contracts, so that v1 can avoid brittle UI- or prompt-dependent testing.

## Implementation Decisions

- `intervention / review hook` is the unified external intervention / review
  boundary.
- Hooks are not a generic replacement for controller, policy, or orchestrator
  logic.
- V1 hook trigger sources are:
  - `policy-triggered`
  - `task-triggered`
- `run-triggered` hook paths remain tentative and are deferred pending more
  complete theory-run design.
- Hook invocations consume structured `intervention context`.
- Hook context should include at least:
  - trigger source
  - reason code
  - optional triggered rule ids
  - current task summary
  - current artifact under review or intervention
  - relevant validation summary
  - relevant policy decision summary
  - concise task trace summary
  - allowed response space
- Hooks do not grab hidden state directly.
- Hooks consume explicit structured inputs rather than raw internal runtime
  objects.
- V1 hook response kinds are:
  - `approve_current_artifact`
  - `reject_current_artifact`
  - `provide_replacement_artifact`
  - `request_committed_placeholder`
  - `request_stop`
- `request_skip` and `request_escalation` remain tentative and are not required
  in the v1 core response set.
- `approve_current_artifact` means the current artifact may proceed through the
  review gate.
- Approval satisfies review requirements but does not override hard runtime
  constraints.
- `reject_current_artifact` rejects the current artifact only.
- Rejecting the current artifact does not itself mean stopping the path.
- Continuing automated search after rejection is a later control-flow decision,
  not a dedicated hook response kind.
- `provide_replacement_artifact` supplies a new artifact to replace the current
  artifact under consideration.
- Replacement artifacts supplied by hooks must go through normal validation.
- Hook-supplied artifacts must be tagged as intervention-supplied for source and
  provenance purposes.
- `request_committed_placeholder` asks the system to continue via a committed
  placeholder-artifact path rather than via a genuine repair artifact.
- `request_stop` asks the system to stop the current automated path.
- Stop is a path-level intervention, not an artifact-level rejection.
- Committed-placeholder request and stop request remain semantically distinct.
- Hooks provide real correction power not by bypassing constraints, but by:
  - approving gated valid artifacts
  - rejecting unsafe artifacts
  - supplying replacement artifacts
  - requesting placeholder continuation
  - requesting stop
- Hook outputs must be recordable.
- Hook interactions should become `intervention records` linked to tasks,
  artifacts, policy decisions, and continuation outcomes where relevant.

## Testing Decisions

- A good hook test should assert stable structured input/output behavior rather
  than UI or free-form prompt details.
- Hook tests should focus on:
  - trigger-source handling
  - context construction
  - reason-code propagation
  - allowed response-space enforcement
  - response-kind semantics
  - validation behavior for replacement artifacts
  - distinction between reject and stop
  - distinction between committed-placeholder request and stop
- Hook tests should verify that:
  - hook responses do not bypass hard runtime validation
  - approval satisfies review gating where appropriate
  - replacement artifacts are routed into normal validation
  - intervention records are emitted correctly
- Hook tests should not rely on future UI behavior or policy-agent explanation
  text.

## Out of Scope

- finalized UI for human reviewers
- editor or IDE integration specifics
- `run-triggered` hook semantics for v1 core
- hook-driven direct mutation of hidden runtime state
- unrestricted arbitrary scripting through the hook interface
- prompt design for future LLM-based reviewers

## Further Notes

- The hook system is intentionally designed to be powerful enough to matter, but
  constrained enough to preserve runtime and policy boundaries.
- Intervention / review is not a fallback for poor modular design; it is an
  explicit first-class path for externally governed decisions.
