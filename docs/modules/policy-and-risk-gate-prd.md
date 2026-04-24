# Policy and Risk Gate PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`proof-repair-architecture.md`](../architecture/overview.md) for the
  top-level architecture
- [`failure-classification-and-localization-prd.md`](./failure-classification-and-localization-prd.md) for repair block and
  contract design
- [`repair-task-engine-prd.md`](./repair-task-engine-prd.md) for task-engine
  execution semantics

## Role In Architecture

This document is authoritative for `policy and risk gate` behavior.

It defines:

- policy configuration
- contextual policy decisions
- repair authorization mode
- policy checks vs recordable policy decisions
- derived risk posture

It is not authoritative for:

- task-engine execution semantics
- intervention-hook response semantics
- top-level continuation orchestration
- shared glossary definitions

## Problem Statement

The proof-repair architecture already distinguishes:

- failure classification and localization
- repair task execution
- theory-level orchestration

However, the current design still lacks a sufficiently explicit PRD for
`policy and risk gate`.

This gap matters because the proof-repair system is explicitly not a pure
"repair whatever passed REPL validation" tool. It must instead control:

- which actions may happen
- which repairs may be accepted automatically
- which outcomes require review
- which continuation paths are allowed after failure

Without a clear policy design, the rest of the architecture becomes unstable:

- the task controller may overstep into risk decisions
- the orchestrator may hardcode ad hoc acceptance behavior
- intervention hooks may become a catch-all escape hatch
- records may fail to explain why a risky path was allowed or blocked

The goal of this document is to define a v1 `policy and risk gate` design that
is powerful enough to control risky proof-repair behavior, while remaining
simple enough to implement as a rule-based system in the first prototype.

## Solution

Build `policy and risk gate` as a first-class, pluggable module that provides:

- top-level `policy configuration`
- rule-based `contextual policy decisions`
- explicit policy decision recording for externally meaningful decisions

The v1 policy design is based on the following principles:

- policy governs permissions, risk gating, and acceptance gating
- policy does not own search orchestration
- policy does not replace theory-level continuation ownership
- policy decisions are not restricted to post-failure moments
- policy must support pre-action gating, acceptance gating, and continuation
  gating
- v1 policy is rule-based and context-sensitive
- future policy-agent extensions are allowed but not required

The architecture distinguishes:

- `policy configuration`
  - default risk posture and hard constraints
- `contextual policy decision`
  - a concrete gate result produced for a specific task/run context
- `policy decision record`
  - a recordable event for externally meaningful policy decisions

The design also introduces a top-level `repair authorization mode` to express
the run's overall default autonomy posture.

## User Stories

1. As a maintainer, I want the repair system to distinguish low-risk and high-risk repair situations, so that automation can remain useful without becoming reckless.
2. As a maintainer, I want policy to govern whether certain task actions are allowed, so that runtime behavior respects risk boundaries.
3. As a maintainer, I want policy to control whether sledgehammer may be used, so that automation can be enabled or disabled per run.
4. As a maintainer, I want policy to control whether committed placeholder artifacts may be emitted, so that placeholder-based continuation remains explicit and governed.
5. As a maintainer, I want policy to influence whether a failure kind may be handled automatically at all, so that some risky categories can be blocked by default.
6. As a maintainer, I want policy to gate acceptance of locally validated repairs, so that "passed local validation" does not automatically imply acceptance.
7. As a maintainer, I want statement-affecting repairs to be treated as high-risk, so that theorem statement changes do not silently slip through.
8. As a maintainer, I want statement-affecting repairs to be treated closer to non-proof repairs than to proof-body repairs, so that policy posture reflects semantic risk.
9. As a maintainer, I want non-proof repairs to follow a more conservative default posture than proof-body repairs, so that definitions and declarations are not changed too casually.
10. As a maintainer, I want placeholder continuation to be policy-controlled, so that placeholder use remains a deliberate and auditable choice.
11. As a maintainer, I want policy to apply before actions occur, so that some high-risk operations can be blocked before they happen.
12. As a maintainer, I want policy to apply after local validation, so that risky artifacts can require review before acceptance.
13. As a maintainer, I want policy to apply after search failure, so that post-failure continuation paths remain controlled.
14. As a maintainer, I want policy to consume structured context rather than scrape runtime internals, so that the module boundary stays stable and testable.
15. As a maintainer, I want task-scoped policy context and run-scoped policy context to be distinct, so that task-level gating and run-level gating can evolve independently.
16. As a maintainer, I want risk posture to be derived from existing classifications rather than from a brand-new parallel taxonomy, so that policy stays aligned with the rest of the design.
17. As a maintainer, I want policy risk posture to be derived mainly from failure kind and block kind, so that policy leverages the existing repair design.
18. As a maintainer, I want artifact kind to further refine policy risk posture, so that genuine repair artifacts and committed placeholder artifacts can be treated differently.
19. As a maintainer, I want localization confidence and fallback mode to remain available as additional context, so that coarse localization can trigger more conservative policy outcomes.
20. As a maintainer, I want a top-level repair authorization mode, so that the same repair architecture can operate in more or less autonomous run postures.
21. As a maintainer, I want the authorization mode to behave like an overall edit/acceptance permission posture rather than a search-strategy setting, so that policy concerns stay distinct from controller concerns.
22. As a maintainer, I want authorization mode to influence defaults without replacing finer-grained policy rules, so that high-risk distinctions are not flattened away.
23. As a maintainer, I want policy configuration to be organized around default dispositions for decision scopes rather than as a bag of unrelated flags, so that policy remains explainable and maintainable.
24. As a maintainer, I want policy decision scopes to distinguish action permission, artifact acceptance, and continuation gating, so that decisions remain semantically clear.
25. As a maintainer, I want contextual policy decisions to be rule-based in v1, so that policy can be implemented without requiring a sophisticated policy agent.
26. As a maintainer, I want the design to remain open to future policy-agent integration, so that the architecture can evolve later without replacing the policy boundary.
27. As a maintainer, I want policy decision kinds to stay small and hard-edged in v1, so that runtime and orchestrator behavior remain simple.
28. As a maintainer, I want policy decisions to distinguish `allow`, `deny`, and `requires_review`, so that review paths are explicitly separated from rejection.
29. As a maintainer, I want `requires_review` to mean "may proceed only through review" rather than "denied," so that high-risk but viable paths can still be considered.
30. As a maintainer, I want policy to avoid introducing soft disposition semantics too early, so that v1 complexity stays under control.
31. As a maintainer, I want future soft-disposition policy behavior to remain possible later, so that policy-agent evolution is not blocked.
32. As a maintainer, I want all externally meaningful policy decisions to be recordable, so that the system can explain why a risky action or acceptance path was allowed or blocked.
33. As a maintainer, I want policy checks and policy decision records to be distinguished, so that records stay meaningful and do not drown in low-level noise.
34. As a maintainer, I want important policy decisions to be attached to tasks, artifacts, and continuation steps where relevant, so that later review and rerun are traceable.
35. As a maintainer, I want policy to remain separate from intervention hooks, so that risk gating and external review stay conceptually distinct.
36. As a maintainer, I want policy to remain separate from the task controller, so that search sequencing and risk authorization are not entangled.
37. As a maintainer, I want policy to remain separate from the orchestrator, so that theory-level continuation authority does not get hidden inside the gate layer.
38. As a reviewer, I want policy-triggered review requests to carry clear reason codes, so that I can understand why review was required.
39. As a maintainer, I want policy rules to be testable against structured inputs and outputs, so that risk behavior does not depend on fragile prompt interpretation.
40. As a maintainer, I want the v1 policy design to be simple enough to ship early, so that the rest of the theory repair run can become complete without waiting for a sophisticated policy subsystem.

## Implementation Decisions

- `policy and risk gate` is a first-class module in the proof-repair system.
- Policy governs:
  - pre-action gating
  - post-validation acceptance gating
  - post-failure continuation gating
- Policy does not own search sequencing.
- Policy does not replace the orchestrator's authority over top-level
  continuation.
- V1 policy is divided into:
  - `policy configuration`
  - `contextual policy decision`
  - `policy decision record`
- `policy configuration` contains default posture and hard constraints.
- `contextual policy decision` is a rule-based gate result derived for a
  concrete context.
- V1 policy does not require a sophisticated policy agent.
- The design remains open to future policy-agent integration.
- Policy consumes structured input from the runtime or orchestrator rather than
  reading internal state directly.
- Policy context is separated into:
  - task-scoped policy context
  - run-scoped policy context
- Policy risk posture is not modeled as a brand-new standalone taxonomy.
- Policy risk posture is derived primarily from:
  - `failure kind`
  - `block kind`
  - `artifact kind`
- Additional context such as localization confidence or fallback mode may refine
  a decision, but is not the primary classification axis.
- Statement-affecting repair remains `statement_failure` in failure taxonomy,
  but is treated as a high-risk posture closer to non-proof repair than to
  proof-body repair.
- `repair authorization mode` is a top-level configuration concept.
- Authorization mode represents overall edit/acceptance posture rather than
  search strategy.
- Authorization mode influences default dispositions but does not erase
  fine-grained risk distinctions.
- V1 policy configuration should be organized around decision scopes and default
  dispositions rather than a flat collection of feature flags.
- V1 decision scopes include:
  - action permission
  - artifact acceptance
  - continuation gating
- V1 contextual policy decision kinds are intentionally minimal:
  - `allow`
  - `deny`
  - `requires_review`
- V1 does not introduce soft-disposition policy decision kinds such as
  `prefer_stop` or `prefer_escalation`.
- Future policy-agent extensions may later introduce richer guidance semantics.
- `requires_review` means the current path is not automatically allowed to take
  effect, but may proceed through the intervention / review path.
- `deny` means the path is not allowed under the current policy posture.
- `allow` means the path is permitted under the current policy posture.
- Contextual policy decisions should be recordable when they are externally
  meaningful.
- V1 distinguishes:
  - `policy check`
  - `policy decision record`
- Lightweight or repetitive capability checks do not all need to become
  heavyweight decision records.
- Acceptance-relevant, placeholder-relevant, review-triggering, and
  continuation-relevant policy results should be represented in records.
- A policy decision output should minimally include:
  - `decision kind`
  - `decision scope`
  - optional `triggered rule ids`
- Human-readable rationale text is optional in v1 and is not part of the core
  policy contract.
- Important policy decisions must be linkable to related tasks, artifacts, and
  continuation behavior.
- Policy rules should be implementable and testable through structured inputs
  and outputs rather than through prompt-shape expectations.

## Implemented v1.5 Subset

The current runtime includes fallback and continuation gating for the v1.5
single-theory repair loop.

Implemented policy inputs include failure kind, block kind, artifact kind,
fallback depth, fallback origin, and continuation kind. High-risk failure kinds
still require review, committed placeholder policy remains configurable, and
fallback-based repair acceptance or rerun continuation can require review.

## Testing Decisions

- A good policy test should assert stable input/output behavior under structured
  contexts rather than internal implementation style.
- Policy tests should focus on:
  - whether the correct decision kind is returned
  - whether the correct decision scope is applied
  - whether triggered rule ids are recorded where expected
  - whether different authorization modes alter default dispositions correctly
  - whether high-risk postures are gated more conservatively than low-risk ones
- Policy tests should explicitly cover:
  - proof-body local repair posture
  - statement-affecting repair posture
  - non-proof repair posture
  - header/load repair posture
  - committed placeholder gating
  - action permission gating for automation such as sledgehammer
- Policy tests should distinguish:
  - lightweight policy checks
  - record-worthy policy decisions
- Policy tests should not require a future policy-agent implementation.
- Policy tests should not rely on natural-language explanation text.
- Policy should be tested primarily as a rule-based structured module in v1.

## Out of Scope

- a sophisticated policy agent for v1
- soft-disposition policy semantics in v1
- full rollback decision logic
- project-wide scheduling policy
- campaign-level cross-theory policy
- final UI/UX for policy explanation presentation
- finalized policy-agent prompt design

## Further Notes

- This document defines the v1 risk-gating layer needed to make the rest of the
  repair system trustworthy.
- The policy design intentionally prefers clarity and explicitness over maximal
  expressive power in the first prototype.
- Future work may extend this layer with richer policy-agent reasoning, but
  v1 should remain rule-based and testable.
