# Repair Block Design

Status: Tentative v1 design snapshot

Companion documents:

- [`proof-repair-agent-prd.md`](../proof-repair-agent-prd.md)
- [`glossary-and-terminology.md`](../glossary-and-terminology.md)
- [`proof-repair-architecture.md`](../architecture/overview.md)

## Role In Architecture

This document is authoritative for repair-block and block-contract design.

It defines:

- repair block taxonomy
- block schema
- entry checkpoints
- primary contracts and continuation boundaries
- fallback structure
- block-level acceptance posture hints

It is not authoritative for:

- task-engine runtime semantics
- policy configuration semantics
- top-level theory-run state transitions

## Purpose

This document captures the current repair-block design for the proof repair
agent. It is intentionally narrower than the full PRD. Its main focus is:

- block taxonomy
- block schema
- entry and exit semantics
- fallback structure
- what is already decided for v1
- what remains intentionally unresolved

This is a phase-one delivery artifact. It is meant to be concrete enough to
guide prototyping, while still acknowledging that localization, continuation,
and acceptance semantics will likely require refinement during implementation.

## Design Principles

The current design adopts the following principles:

- A repair block is not just a textual span. It is an operational unit with a
  stable entry checkpoint, a principal exit boundary, and a replacement-based
  repair model.
- A construct should become a first-class peer block kind only if it has its
  own stable primary contract shape.
- Selection preference, repair autonomy, and acceptance posture must remain
  separate axes.
- Modifiers are controlled annotations, not an open-ended extension point.
- Fallback structure should stay simple at the schema level. Extra upward
  re-localization paths belong to selection logic, not to the block schema
  itself.
- v1 should prefer a smaller block only when its entry checkpoint, primary
  contract, and continuation boundary can be determined stably.

## Unified Schema

The current v1 schema draft is:

```text
BlockKind {
  name
  surface
  span_rule
  entry_checkpoint        // kind-level checkpoint schema
  primary_contract        // exactly one
  secondary_effects       // zero or more, compatibility-table restricted
  first_class
  selection_bias
  autonomy_level
  acceptance_rule
  fallback_parent
  modifiers               // controlled modifiers only
  common_failures         // explanatory
  notes                   // explanatory
}
```

### Field Roles

- `name`, `surface`, `span_rule`, `modifiers`
  taxonomy and localization
- `entry_checkpoint`, `primary_contract`, `secondary_effects`
  continuation semantics and local validation semantics
- `first_class`, `selection_bias`, `autonomy_level`, `acceptance_rule`
  orchestration-facing policy posture
- `fallback_parent`
  schema-level canonical upward fallback
- `common_failures`, `notes`
  explanatory fields for design, debugging, and testing guidance

### Entry Checkpoint

At the block-kind level, `entry_checkpoint` specifies the required checkpoint
schema rather than a concrete runtime instance.

The current checkpoint schema under discussion is:

```text
EntryCheckpoint {
  outer_context_kind
  proof_mode
  proof_depth
  fact_state
  goal_shape_summary
}
```

Current v1 decision:

- required to model stably:
  - `outer_context_kind`
  - `proof_mode`
  - `proof_depth`
- best-effort / partial availability in v1:
  - `fact_state`
  - `goal_shape_summary`

### Primary Contract and Secondary Effects

Each block kind must declare exactly one `primary_contract`.

Secondary effects are allowed, but only as bounded additional consequences.
They do not redefine the principal continuation boundary.

Current v1 contract vocabulary:

- `context_updated`
- `fact_produced`
- `subproof_closed`
- `branch_closed`
- `goal_closed`
- `theorem_closed`
- `theory_context_restored`
- `focused_subgoal_discharged`

Current v1 principles:

- each block has exactly one primary contract
- secondary effects are optional
- secondary effects must be compatibility-table restricted
- a secondary effect must not override or replace the meaning of the primary
  contract

### Selection Bias

In v1, `selection_bias` is restricted to exactly three values:

- `default_preferred`
- `neutral`
- `fallback_preferred`

`selection_bias` only governs default block-selection preference. It does not
encode acceptance conservativeness, repair risk, or autonomy.

### Autonomy Level

In v1, `autonomy_level` is restricted to exactly three values:

- `high`
- `medium`
- `low`

`autonomy_level` governs how aggressively the system may search, propose, and
continue automatically after a block has been selected. It does not govern
whether the block should have been selected in the first place.

`autonomy_level` does not by itself override contract-based validation or
kind-specific acceptance restrictions.

### Acceptance Rule

In v1, `acceptance_rule` is restricted to exactly three values:

- `default_accept`
- `conservative_accept`
- `restricted_accept`

Definitions:

- `default_accept`: local validation success normally permits acceptance,
  subject to general policy
- `conservative_accept`: local validation success is not normally sufficient on
  its own; additional review or stronger policy confirmation is typically
  expected
- `restricted_accept`: acceptance is allowed only when kind-specific contract
  conditions are satisfied

`acceptance_rule` governs the default acceptance posture after local
validation. It does not change the block's primary contract, and it does not
determine selection preference.

### Modifiers

In v1, modifiers are controlled annotations, not an open-ended extension point.

Current modifier set:

- `chain_sensitive`
- `calculation_sensitive`

Modifiers refine localization, validation, and policy behavior, but do not
introduce an independent principal exit boundary and do not override the base
block kind's primary contract.

## Non-Goals for First-Class Blocks

The following should not be treated as accepted replacement blocks in v1:

- standalone proposition text
- standalone method text
- standalone `then` / `from` / `with`
- standalone `also` / `finally` / `moreover` / `ultimately`
- standalone `proof` / `qed` / `next`

These may still appear as:

- internal search or edit objects
- block boundary markers
- localization hints

Likewise, statement-only repair is not the default accepted block-level
submission target. In v1, accepted statement repair normally escalates to
`TheoremShellBlock`.

## Peer Block Kinds for v1

The current v1 peer block kinds are:

- `HeaderImportsBlock`
- `TopLevelCommandBlock`
- `TheoremShellBlock`
- `WholeProofBodyBlock`
- `TerminalProofStepBlock`
- `AtomicPropositionStepBlock`
- `StructuredPropositionStepBlock`
- `ContextUpdateStepBlock`
- `BranchBlock`
- `ApplySegmentBlock`
- `SubgoalBlock`

The following are no longer treated as peer block kinds in v1:

- `ChainSensitiveBlock`
- `CalculationBlock`

Instead, they survive as controlled modifiers:

- `chain_sensitive`
- `calculation_sensitive`

## Current v1 Block Rules

This section records what is already decided or strongly tentatively decided.

### HeaderImportsBlock

- `surface = theory_surface`
- span: full header/imports region from `theory ...` through `begin`
- `primary_contract = theory_context_restored`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = none`

Rules:

- accepted repairs are normalized to the whole header/imports block
- theorem or proof-level continuation is not defined until
  `HeaderImportsBlock` has restored a valid theory context

Notes:

- smaller edits inside the header may still be used during search
- this is the default owner for `theory_load_or_header_failure`

### TopLevelCommandBlock

- `surface = theory_surface`
- span: one complete top-level or local-theory command block
- `primary_contract = context_updated`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = none`

Rules:

- theorem-like commands are excluded from `TopLevelCommandBlock`
- theorem-like commands belong to `TheoremShellBlock`
- local validation establishes only that the enclosing theory or local-theory
  context has been validly updated at the block boundary
- local validation does not guarantee downstream repair success

### TheoremShellBlock

- `surface = mixed_surface`
- span: theorem-like command from statement through proof closure
- `primary_contract = theorem_closed`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = fallback_preferred`
- `fallback_parent = none`

Rules:

- `TheoremShellBlock` uses `theorem_closed` as its sole primary contract and
  carries no secondary effects in v1
- it is a top-level peer kind, but operationally acts as a low-priority
  fallback block
- this is the default accepted target for statement-level repair decisions

### WholeProofBodyBlock

- `surface = proof_surface`
- span: full proof body excluding the theorem shell header
- `primary_contract = subproof_closed`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = fallback_preferred`
- `fallback_parent = TheoremShellBlock`

Rules:

- `WholeProofBodyBlock` is a structural fallback kind
- in v1, `WholeProofBodyBlock` always uses `subproof_closed` as its sole
  primary contract, regardless of whether it happens to occupy the top-level
  proof body of a theorem
- the theorem-level closure boundary belongs exclusively to
  `TheoremShellBlock`

### TerminalProofStepBlock

- `surface = proof_surface`
- span: terminal step that closes the current goal or theorem-proximate proof
  step
- `primary_contract = goal_closed`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = WholeProofBodyBlock`

Rules:

- in v1, `TerminalProofStepBlock` always uses `goal_closed` as its sole
  primary contract and carries no secondary effects
- this is one of the clearest high-value local repair units

### AtomicPropositionStepBlock

- `surface = proof_surface`
- span: atomic proposition step without an explicit nested `proof ... qed`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = WholeProofBodyBlock`

Rules:

- the primary contract is determined by the proposition role in the enclosing
  proof
- fact-producing roles use `fact_produced`
- goal-discharge roles use `goal_closed`
- `secondary_effects = none` in v1

### StructuredPropositionStepBlock

- `surface = proof_surface`
- span: proposition step with explicit nested proof
- `primary_contract = subproof_closed`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = WholeProofBodyBlock`

Rules:

- `subproof_closed` is always the primary contract in v1
- `fact_produced` may appear as a secondary effect only when the structured
  proposition yields a reusable enclosing-proof fact
- goal-discharge uses may carry no secondary effect in v1

### ContextUpdateStepBlock

- `surface = proof_surface`
- span: one proof-context update step such as `fix`, `assume`, `let`, `note`,
  or `define`
- `primary_contract = context_updated`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = WholeProofBodyBlock`

Rules:

- local validation establishes only the legitimacy of the context update at the
  block boundary
- local validation does not guarantee downstream proof compatibility

### BranchBlock

- `surface = proof_surface`
- span: one branch segment such as a `case ...` branch
- `primary_contract = branch_closed`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = WholeProofBodyBlock`

Rules:

- `BranchBlock` models branch completion as a control-flow boundary, not as a
  fact-producing block

### ApplySegmentBlock

- `surface = proof_surface`
- span: a continuous apply-style tactic segment up to a structural boundary
- `first_class = yes`
- `selection_bias = neutral`
- `fallback_parent = TheoremShellBlock`

Rules:

- v1 does not introduce a weaker standalone progress contract for
  `ApplySegmentBlock`
- `ApplySegmentBlock` is accepted only when it satisfies `goal_closed`
- partial tactic progress inside the segment may inform search and
  localization, but does not satisfy local validation for accepted repair in v1

Notes:

- `ApplySegmentBlock` is currently understood as a first-class but
  acceptance-restricted block kind

### SubgoalBlock

- `surface = proof_surface`
- span: explicit `subgoal ... done` block
- `primary_contract = focused_subgoal_discharged`
- `secondary_effects = none`
- `first_class = yes`
- `selection_bias = default_preferred`
- `fallback_parent = ApplySegmentBlock`

Rules:

- the focused subgoal must be fully discharged and control must return to the
  enclosing goal state
- partial progress within the focused subgoal does not satisfy local
  validation in v1

## Selection Logic

The current selection principle is:

`Prefer the smallest block whose entry checkpoint, primary contract, and
continuation boundary can be determined stably; fall back to larger enclosing
blocks only when smaller candidates are judged unstable or ambiguous.`

Important clarifications:

- block kinds are not assumed to be globally disjoint
- one failure site may match multiple candidate kinds
- the schema describes kinds
- the selector chooses instances
- canonical `fallback_parent` belongs to the schema
- extra re-localization choices belong to selection logic

## What Is Still Not Fully Decided

The following points are not yet fully finalized:

### Full Strategy Matrix per Kind

The schema is stable enough to discuss, but not every peer kind has had its
full strategy tuple explicitly finalized:

- `autonomy_level`
- `acceptance_rule`

Some kinds strongly suggest obvious values, but the document does not yet claim
those values are final across the full v1 matrix.

### Compatibility Table for Secondary Effects

The document records the principle that secondary effects must be compatibility-
table restricted, but the actual compatibility table has not yet been fully
written down.

### Entry Checkpoint Precision

We have a stable checkpoint schema direction, but `fact_state` and
`goal_shape_summary` are still best-effort concepts in v1, not hardened runtime
contracts.

### Span Rules for Some Proof Shapes

The conceptual boundaries are clear, but some span rules still need more
operational precision, especially for:

- mixed Isar/apply proofs
- long apply chains with multiple semantic phases
- nested proof structures that could plausibly match multiple peer kinds

### Selection Details vs Schema Details

The current design intentionally separates schema-level fields from selection
logic. A later refinement pass may still be needed to ensure that no schema
field is quietly carrying selection semantics that should live elsewhere.

## Expected Refinement Areas

The most likely redesign pressure during prototyping is expected around:

- block localization quality
- continuation semantics after replacement
- contract validation for borderline blocks
- exact boundaries between theorem shell, whole proof body, and apply-style
  fallback chains

These are expected implementation risks, not signs that the schema is failing.

## Implemented v1.5 Subset

Current runtime support is intentionally narrower than the full block taxonomy
above.

Implemented first-class runtime block kinds:

- `TerminalProofStepBlock`
- `WholeProofBodyBlock`
- `TheoremShellBlock`
- `TopLevelCommandBlock`

Implemented runtime contracts:

- `goal_closed`
- `subproof_closed`
- `theorem_closed`
- `context_updated`

The REPL-backed localizer currently discovers failures incrementally from the
working snapshot command cursor and selects a terminal proof-step block first.
It also returns a structured fallback chain that allows the task engine to try
larger proof-body and theorem-shell blocks under explicit contracts.

`TopLevelCommandBlock` has minimal v1.5 runtime validation support through the
`context_updated` contract. Autonomous generation remains conservative; reviewed
or externally supplied replacements are the primary supported path.
Other block kinds in this document are design intent until their runtime
support is explicitly added to this implemented-subset section and to the v1.5
traceability matrix.

## Summary

The current block design has already converged on several strong v1 decisions:

- peer block kinds are now much more orthogonal
- `primary_contract`, `selection_bias`, `autonomy_level`, and
  `acceptance_rule` are separated
- `ChainSensitive` and `Calculation` are now modifiers, not peer kinds
- theorem-level, proof-body-level, and local proof-step-level closures are
  now more sharply distinguished
- canonical fallback structure is substantially clearer than in the earlier PRD

What remains is not a new taxonomy from scratch, but the final tightening of:

- per-kind strategy settings
- secondary-effect compatibility
- selector behavior on ambiguous matches

That means this document should already be usable as a first-phase block design
artifact for discussion, implementation planning, and PRD alignment.
