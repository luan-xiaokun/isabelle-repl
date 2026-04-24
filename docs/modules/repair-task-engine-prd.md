# Repair Task Engine PRD

Status: Tentative v1 design for local prototyping and discussion

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md) for the overall
  proof-repair system PRD
- [`glossary-and-terminology.md`](../glossary-and-terminology.md) for shared
  vocabulary
- [`proof-repair-architecture.md`](../architecture/overview.md) for the
  high-level architecture
- [`failure-classification-and-localization-prd.md`](./failure-classification-and-localization-prd.md) for failure
  classification and localization design

## Role In Architecture

This document is authoritative for `repair task engine` behavior.

It defines the task-scoped execution semantics of local repair, including:

- engine runtime
- task controller
- candidate generators
- task-local search state
- local validation
- task trace and task outcome semantics

It is not authoritative for:

- top-level theory-run orchestration
- policy configuration semantics
- intervention-hook semantics
- system-wide glossary definitions

## Problem Statement

The current proof-repair design has reached a stronger level of clarity around
failure classification, localization, repair blocks, and architecture
boundaries. However, the `repair task engine` itself is still the least
concretely specified core component.

This creates a planning gap:

- the architecture says there is a `repair task engine`
- the overall PRD says repair tasks are bounded, iterative, and traceable
- the block design says what kind of repair unit should be localized
- but the engine design is still too implicit in several important areas

In particular, we need a concrete v1 design for:

- what the engine receives as input
- what state it owns during a task
- how actions are represented and executed
- how candidate generation, validation, placeholders, and termination work
- how the engine relates to controller logic, policy logic, and the outer
  orchestrator
- what stable contracts can be tested without relying on fragile end-to-end LLM
  tests

Without this engine-focused PRD, implementation risks drifting into one of two
bad extremes:

- a shallow wrapper around ad hoc prompts and REPL calls, with weak execution
  semantics and weak testability
- an overcomplicated architecture that introduces too many intermediate
  concepts before the v1 repair loop is proven useful

The goal of this document is to define a v1 engine design that is powerful
enough to support meaningful proof-repair search, while remaining honest about
uncertainty and disciplined about module boundaries.

## Solution

Build the `repair task engine` as a task-scoped execution module that consumes
an already-localized repair task and performs bounded, action-driven local
repair search.

The v1 engine design is based on the following principles:

- the engine is responsible for local execution semantics, not theory-level
  orchestration
- the engine consumes a structured `task spec`, not just a failure location
- the engine runs an action-driven loop with explicit traceable actions
- the engine maintains a `task-local search state` derived from the current
  working theory snapshot
- the engine exposes a structured `task view` to a `task controller`
- the engine uses `candidate generators` as proposal backends for
  `propose_candidate`
- the engine performs local validation through block-kind-aware contract
  adapters
- the engine distinguishes genuine repair candidates from committed
  placeholder-based continuation artifacts
- the engine is designed to support layered testing through stable contracts

The v1 design intentionally separates:

- `engine runtime`
  - action execution semantics
  - state management
  - REPL interaction
  - validation
  - trace
  - budget enforcement
- `task controller`
  - next-action selection and local search strategy
- `candidate generator`
  - production of complete repair candidates
- `policy module`
  - permissions, risk gating, and acceptance gating

This separation is meant to produce deep modules with stable, testable
interfaces rather than a monolithic prompt-driven loop.

## User Stories

1. As a proof-repair system designer, I want the repair task engine to have a clear role distinct from the orchestrator, so that theory-level continuation logic does not leak into local repair execution.
2. As a proof-repair system designer, I want the engine to consume a structured task specification, so that localization and execution stay decoupled.
3. As a maintainer, I want the engine to receive a localized repair block plus its enclosing context, so that local repair can operate with precise scope.
4. As a maintainer, I want the engine to receive effective task-level policy caps and budget, so that local search respects run-level constraints.
5. As a maintainer, I want the engine to manage a task-local search state, so that local search can branch and refine without mutating the global working theory snapshot.
6. As a maintainer, I want the engine to expose a controller-visible task view, so that controller logic is insulated from runtime internals.
7. As a maintainer, I want the engine to record actions explicitly, so that repair search is traceable rather than hidden inside prompt state.
8. As a maintainer, I want the engine to support `inspect` actions, so that local search can gather proof state, context, dependency, and history information on demand.
9. As a maintainer, I want `inspect` to be a family of actions rather than one overloaded operation, so that different information sources can stay explicit in trace and testing.
10. As a maintainer, I want the engine to support `propose_candidate`, so that candidate generation is modeled as an explicit step in local repair.
11. As a maintainer, I want each proposal to be a complete replacement-block candidate, so that validation always operates on a stable artifact boundary.
12. As a maintainer, I want refinement to happen through repeated propose/validate cycles, so that the engine does not need a separate first-class candidate-construction lifecycle in v1.
13. As a maintainer, I want candidate generation to be delegated to pluggable generators, so that deterministic, LLM-based, and hybrid proposal methods can coexist.
14. As a maintainer, I want the controller to choose which generator to use, so that search strategy stays separate from proposal synthesis.
15. As a maintainer, I want candidate generators to be called through runtime-mediated actions, so that proposal generation remains auditable and contract-bound.
16. As a maintainer, I want candidate generators to receive structured proposal context, so that they do not directly couple to runtime internals.
17. As a maintainer, I want the runtime to construct proposal context from a task-local observation store, so that inspect and validation feedback can be reused systematically.
18. As a maintainer, I want inspect observations and normalized validation feedback to accumulate in the same task-local observation store, so that later proposals can build on earlier search results.
19. As a maintainer, I want proposal context construction to stay under runtime control, so that information passed to generators remains bounded and structured.
20. As a maintainer, I want the engine to support `validate_candidate`, so that candidate checking is a first-class action with explicit outputs.
21. As a maintainer, I want local validation to be non-boolean, so that execution failure, contract failure, timeout, and success can be distinguished honestly.
22. As a maintainer, I want block kind to affect local validation semantics, so that repair blocks are not just a localization artifact.
23. As a maintainer, I want block-kind-aware validation adapters, so that the engine can interpret REPL results through block contracts rather than raw execution status alone.
24. As a maintainer, I want v1 to prioritize adapters for the highest-value block kinds first, so that the engine can become useful before every fine-grained kind is fully supported.
25. As a maintainer, I want unsupported block kinds to fail honestly through explicit fallback validation behavior, so that the system does not fake precision it does not yet have.
26. As a maintainer, I want the engine to support `request_policy_decision`, so that high-risk paths are explicitly gated rather than silently allowed.
27. As a maintainer, I want the engine to support `request_intervention`, so that reviewers or external tools can provide replacements or decisions when needed.
28. As a maintainer, I want the engine to support `emit_placeholder`, so that placeholder-based continuation is explicit and traceable.
29. As a maintainer, I want the engine to distinguish exploratory placeholders from committed placeholder artifacts, so that temporary search aids are not confused with externally committed continuation choices.
30. As a maintainer, I want exploratory placeholders to remain task-local only, so that they never masquerade as accepted repair artifacts.
31. As a maintainer, I want committed placeholder artifacts to require policy approval and explicit validation, so that placeholder continuation remains controlled.
32. As a maintainer, I want committed placeholder artifacts to be modeled as their own artifact kind, so that they do not pollute genuine repair candidate semantics.
33. As a maintainer, I want the engine to support `terminate`, so that accepted, failed, placeholder-based, user-resolved, escalated, and aborted endings are explicit.
34. As a maintainer, I want task acceptance to require both local validation success and any required risk gate approval, so that local execution and policy acceptance stay distinct.
35. As a maintainer, I want task failure to mean bounded search failure rather than every non-success outcome, so that reporting remains semantically clean.
36. As a maintainer, I want the engine to treat action-level failures as recoverable by default, so that a single failed inspect or proposal does not collapse the whole task.
37. As a maintainer, I want the engine runtime to defensively validate controller outputs, so that deterministic and LLM-based controllers alike are constrained by the same runtime checks.
38. As a maintainer, I want the runtime to compute the enabled action space from task state, policy caps, and budget, so that illegal actions can be rejected systematically.
39. As a maintainer, I want the detailed shape of the action legality model to remain tentative in v1, so that implementation can refine it without rewriting the whole PRD.
40. As a maintainer, I want the engine to use a small set of core budgets, so that bounded repair can be enforced without overengineering cost models.
41. As a maintainer, I want `max_actions`, `max_validations`, and wall-clock timeout to be the core task budgets, so that local search is bounded in a simple and testable way.
42. As a maintainer, I want proposal count budgeting to remain optional, so that v1 can stay simple unless proposal churn becomes a real problem.
43. As a maintainer, I want task trace to be action-granular, so that repair behavior is auditable and analyzable.
44. As a maintainer, I want task trace and run-level record to be distinct layers, so that low-level search detail does not overwhelm theory-level records.
45. As a maintainer, I want only externally meaningful task events to be promoted to run-level records, so that rollback- and audit-oriented data remains stable and useful.
46. As a maintainer, I want task trace entries to carry references to related candidates, placeholders, and validation results where relevant, so that the local search path can be reconstructed.
47. As a maintainer, I want committed placeholder artifacts, accepted repair artifacts, policy decisions, and intervention outcomes to appear in run-level records, so that externally meaningful decisions are preserved.
48. As a maintainer, I want the engine to be testable with fake controllers, fake generators, fake policy, and canned REPL scenarios, so that execution semantics can be tested without heavy end-to-end infrastructure.
49. As a maintainer, I want runtime contract tests to focus on observable behavior rather than prompt wording, so that tests remain stable across controller implementations.
50. As a maintainer, I want canned candidate validation tests to cover pass, contract failure, execution failure, and timeout, so that validation classification is explicitly verified.
51. As a maintainer, I want controller tests to focus on legality, enabled-action compatibility, and stable behavior under fixed inputs, so that controller testing does not overfit strategy details prematurely.
52. As a maintainer, I want generator tests to focus on proposal contract rather than proposal success rate, so that generator modules are tested against stable responsibilities.
53. As a maintainer, I want the engine design to stay compatible with both deterministic and LLM-based controllers, so that future controller upgrades do not require replacing the runtime.
54. As a maintainer, I want the engine design to remain honest about placeholder-based continuation and partial validation, so that future evaluation does not overclaim repair success.
55. As a collaborator, I want this engine PRD to separate required v1 functionality from tentative and deferred areas, so that implementation can start without pretending all details are settled.

## Implementation Decisions

- The `repair task engine` is the task-scoped local repair execution module.
- The engine does not decide the next repair target and does not own
  theory-level continuation.
- The engine consumes a structured `task spec` produced after localization.
- Effective task policy caps and budget are task-level inputs derived from
  global configuration plus current task circumstances.
- Task-level policy caps may be more restrictive than global defaults, but do
  not overrule global hard prohibitions without an explicit higher-level gate.
- The engine is decomposed into:
  - `engine runtime`
  - `task controller`
  - `candidate generator`
  - block-kind-aware local validation adapters
  - a task-local observation and trace layer
- The `engine runtime` owns execution semantics:
  - action execution
  - task-local search state
  - REPL interaction
  - validation
  - trace
  - budget enforcement
  - defensive checking of controller outputs
- The `task controller` owns next-action choice and local search sequencing.
- The `policy module` is separate from the task controller:
  - controller decides what to try next
  - policy decides which risky actions or outcomes are permitted
- Candidate generators are proposal backends for `propose_candidate`.
- Candidate generators do not control search flow.
- Candidate generators receive structured proposal context rather than direct
  access to runtime internals.
- The runtime constructs proposal context from task-local observations and other
  structured state summaries.
- The engine uses seven action families:
  - `inspect`
  - `propose_candidate`
  - `validate_candidate`
  - `request_policy_decision`
  - `request_intervention`
  - `emit_placeholder`
  - `terminate`
- `inspect` is an action family containing multiple typed actions rather than a
  single generic action.
- `restore_checkpoint` is treated as a task-internal control primitive in v1
  rather than a required top-level action family.
- Each `propose_candidate` action must produce a complete candidate artifact.
- Refinement happens across repeated `inspect -> propose -> validate` cycles.
- V1 does not introduce a first-class `candidate attempt` lifecycle object.
- The engine maintains a `task-local search state` derived from the working
  theory snapshot.
- The task-local search state is internal to the runtime.
- The controller sees a structured `task view`, not the full internal state.
- The runtime may maintain a `task-local observation store` that accumulates:
  - inspect observations
  - normalized validation feedback
  - other proposal-relevant structured observations
- Validation feedback should be reusable as an observation source rather than
  being available only as raw trace.
- Proposal context construction remains under runtime control, even when the
  controller influences what information should be included.
- The engine distinguishes two externally meaningful artifact kinds:
  - `repair_candidate_artifact`
  - `committed_placeholder_artifact`
- Exploratory placeholders are task-local search aids only.
- Exploratory placeholders do not become externally committed artifacts.
- Committed placeholder artifacts are explicit continuation artifacts and
  require policy gating.
- Committed placeholder artifacts must be validated under a dedicated placeholder
  continuation standard rather than treated as ordinary repair success.
- A task may have many internal search states and many trace events, but at any
  given moment it has at most one current externally relevant artifact.
- Candidate validation is local to the task and uses REPL execution on the
  relevant task entry state.
- Local validation is not boolean.
- V1 local validation result categories are:
  - `passed`
  - `failed_execution`
  - `failed_contract`
  - `failed_timeout`
  - optional `inconclusive`
- Local validation success requires both:
  - executable acceptance by REPL
  - satisfaction of the block-kind-specific local contract
- Execution success alone is not enough.
- Block kinds must participate in local validation through
  block-kind-aware contract adapters.
- V1 should prioritize adapters for:
  - `TerminalProofStepBlock`
  - `WholeProofBodyBlock`
  - `TheoremShellBlock`
  - `TopLevelCommandBlock`
- Unsupported or weakly supported block kinds must use explicit fallback
  validation behavior rather than silently pretending to have precise support.
- Task acceptance requires:
  - a complete repair candidate artifact
  - successful local validation
  - any required policy or intervention approval
  - no leakage of committed placeholder semantics into genuine accepted repair
- `task_outcome = failed` means bounded search failed to obtain an acceptable
  repair artifact and did not end through another named path.
- `task_outcome = escalated` remains tentative in v1 and may be refined further.
- Action-level failure does not automatically mean task-level failure.
- Failed `inspect` and failed `propose_candidate` executions are recorded as
  action-level failures and may be followed by alternative actions.
- The engine runtime defensively validates controller outputs, including:
  - action existence
  - argument shape
  - legality in the current state
  - policy compatibility
  - budget compatibility
  - reference validity
- The engine should support a dedicated legality/enabled-action mechanism, but
  the exact formal shape of that mechanism remains tentative in v1.
- V1 core task budgets are:
  - `max_actions`
  - `max_validations`
  - wall-clock timeout
- `max_proposals` remains optional and may be added later if proposal churn
  becomes a practical issue.
- Task trace is action-granular.
- Run-level record promotion is selective.
- Run-level records should elevate only externally meaningful events such as:
  - accepted repair artifacts
  - committed placeholder artifacts
  - policy decisions
  - intervention outcomes
  - localization summaries
  - task terminal outcomes
  - acceptance-relevant validation summaries
  - provenance or invalidation links
- V1 should explicitly separate:
  - `required in v1`
  - `tentative but deferrable`
  - `future refinement`
- Tentative but deferrable areas include:
  - the exact form of the action legality state model
  - the final data-model position of `escalated`
  - the exact observation-selection strategy for proposal context
  - whether certain search-control capabilities should later become first-class
    actions

## Implemented v1.5 Subset

The current runtime implements a deterministic inspect/propose/validate loop,
not the full future action-runtime design.

Implemented runtime behavior:

- one task-scoped inspection step represented by the localized task input
- ordered candidate proposal from the rule-first generator
- review-injected candidates through the same validation path as automatic
  candidates
- block-kind-aware validation adapters for the implemented block subset
- compact task trace summaries promoted into run records

The current runtime also includes budgeted deterministic trace evidence:

- validation budget enforcement through `max_validations`
- compact action-count summaries for inspect/propose/validate via
  `trace_counts`
- structured fallback block metadata on accepted task results

The action-runtime design remains future work. In particular, the current
implementation does not yet include a first-class enabled-action model,
task-local observation store, controller legality mechanism, or granular action
record stream.

## Testing Decisions

- A good test should assert stable external behavior and module contracts, not
  implementation details or prompt wording.
- The engine design should support layered testing rather than depending on
  fragile heavy end-to-end LLM tests.
- Testing priority for the engine is:
  1. `engine runtime` contract tests
  2. canned-candidate functional validation tests
  3. `task controller` legality and stability tests
  4. candidate generator contract tests
  5. a small number of REPL-backed integration tests
- `engine runtime` tests should focus on observable behavior such as:
  - executing legal actions
  - rejecting illegal actions
  - enforcing budget
  - classifying validation results correctly
  - recording task trace correctly
  - keeping exploratory placeholders local
  - handling committed placeholder artifacts as explicit continuation artifacts
- `engine runtime` tests should not assert controller thought process or prompt
  shape.
- Functional validation tests should use canned candidate classes against
  representative task states and REPL scenarios, including:
  - a candidate that passes local validation
  - a candidate that executes but fails contract validation
  - a candidate that fails execution
  - a candidate that times out
- `task controller` tests should focus on:
  - legality of chosen actions
  - compatibility with enabled action space
  - compatibility with policy constraints
  - stable behavior under fixed structured inputs
- `task controller` tests should not require proving optimal strategy quality in
  v1.
- Candidate generator tests should focus on generator contract:
  - returns a complete candidate artifact
  - returns required metadata
  - preserves stable input/output contract
- Candidate generator tests should not require candidate success as a contract
  condition.
- Deterministic generators should be tested for stable outputs under fixed
  inputs.
- LLM-backed generators should be tested for interface behavior and output
  contract, not prompt wording or broad success-rate guarantees.
- Prior art from this repository may inform test style, but does not bind the
  engine design to any one exact pre-existing pattern.
- Candidate generator tests are lower priority than runtime and validation tests
  because the generator contract is thinner than the runtime contract.
- Module testing priority should begin with:
  1. `engine runtime`
  2. local validation contract adapters
  3. `task controller`
  4. task trace / run-record bridge
  5. candidate generator

## Out of Scope

- theory-level repair orchestration
- selection of the next repair target across the whole theory run
- project-wide campaign scheduling
- finalized rollback engine behavior
- finalized persistent strategy memory
- comprehensive support for every repair block kind in v1
- final formalization of the action legality model
- optimal controller strategy design
- broad evaluation benchmarking for generator quality
- treating placeholder continuation as genuine repair success
- binding the design to any specific prompt wording or LLM implementation

## Further Notes

- This PRD is intentionally focused on the `repair task engine` rather than the
  full proof-repair system.
- The engine design is meant to complement, not replace, the overall
  proof-repair PRD.
- The engine is intentionally designed as a deep module boundary with strong
  execution semantics and explicit test contracts.
- The action legality model is required in spirit, but its exact implementation
  form remains intentionally open for v1 prototyping.
- The engine should remain honest about uncertainty, bounded search, and the
  distinction between true repair and placeholder-based continuation.
