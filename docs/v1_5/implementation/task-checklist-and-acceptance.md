# v1.5 Implementation Task Checklist and Acceptance

Status: Execution checklist for implementation phase

Companion documents:

- [`./README.md`](./README.md)
- [`./01-incremental-localizer-and-snapshot.md`](./01-incremental-localizer-and-snapshot.md)
- [`./02-candidate-source-unification.md`](./02-candidate-source-unification.md)
- [`./03-run-state-and-records-v1_5.md`](./03-run-state-and-records-v1_5.md)
- [`../contracts/theory-repair-run-state-machine-contract.md`](../contracts/theory-repair-run-state-machine-contract.md)
- [`../testing/repair-acceptance-gate.md`](../testing/repair-acceptance-gate.md)

## Phase 0: Baseline and Guardrails

### Task 0.1: Lock v1.5 schema intent

- Define and document `schema_version = v1.5`.
- Declare v1 artifacts as non-compatible and disposable.

Acceptance:

- records writer emits `v1.5` for new runs
- docs explicitly state no backward compatibility with v1
- at least one integration test asserts `schema_version == "v1.5"` in JSONL rows

### Task 0.2: Strengthen acceptance gate criteria

- Extend acceptance gate checks to include v1.5 docs paths.
- Ensure gate fails fast when required v1.5 docs are missing.

Acceptance:

- `cd python && uv run python scripts/check_repair_acceptance_gate.py` passes
- intentionally removing one required v1.5 doc causes gate failure

## Phase 1: Incremental Localizer + Snapshot

### Task 1.1: Expand snapshot model

- Add snapshot execution fields:
  - `current_anchor_state_id`
  - `command_cursor`
  - `applied_replacements`
  - `last_failure_digest`
  - minimal proof context (`mode`, `proof_level`)

Acceptance:

- unit tests verify snapshot update semantics and invariant checks
- snapshot state is sufficient to deterministically resume localization step
- records include enough metadata to audit snapshot evolution

### Task 1.2: Implement incremental localizer runtime

- Replace one-shot localizer behavior with incremental progression.
- Localizer consumes snapshot state and returns next failure task.

Acceptance:

- unit tests prove no nominal full header replay per task
- localizer stops returning tasks when target/theory boundary is reached
- integration tests show multiple sequential failures are discovered

### Task 1.3: Context-drift fallback strategy

- Implement explicit fallback when context is invalid:
  - execution mismatch errors
  - proof context drift (`mode`/`proof_level` mismatch)

Acceptance:

- unit tests for both drift trigger categories
- integration case demonstrates fallback recovers or fails with explicit reason
- drift reason is observable in logs/records payload

## Phase 2: CandidateSource Unification

### Task 2.1: Introduce unified candidate-source contract

- Add a single interface for candidate delivery consumed by controller.
- Support source metadata for auditability.

Acceptance:

- controller runs against interface, not source-specific branches
- unit tests cover source contract behavior and metadata propagation

### Task 2.2: Implement two production candidate sources

- `AutoCandidateSource` for deterministic/rule-first proposals.
- `ReviewCandidateSource` for hook-provided replacements.

Acceptance:

- both sources produce candidates accepted by the same controller path
- no dedicated test-only engine is required for review-injected candidate flow
- source type is visible in task trace/records for analysis

### Task 2.3: Enforce unified validation contract

- Every candidate must pass:
  - REPL execute success
  - block-kind adapter contract validation

Acceptance:

- unit tests assert reviewed candidate cannot bypass adapters
- integration tests show review-injected candidate rejection paths are explicit
- invalid review responses remain rejected by hook guard

## Phase 3: Run State and Terminal Semantics

### Task 3.1: Upgrade run state model to five states

- Add `finished` state.
- Keep `completed` for target-boundary completion.

Acceptance:

- state machine tests cover:
  - `active -> completed`
  - `active -> finished`
  - `active -> stopped`
  - `active <-> awaiting_review` (resume only via review path)
- terminal states are mutually exclusive and non-reentrant

### Task 3.2: Introduce run mode and boundary config

- Default mode: `theory_wide`.
- Optional mode: `target_boundary` (regression/experimental use).

Acceptance:

- default run without boundary ends in `finished` when theory-wide done
- target boundary mode ends in `completed` when boundary achieved
- same scenario with different mode yields expected distinct terminal state

### Task 3.3: Terminal reason evidence

- Add explicit `terminal_reason` in terminal logs/records.
- Enforce consistent reason vocabulary:
  - `theory_wide_finished`
  - `target_boundary_completed`
  - `stopped_*`

Acceptance:

- integration tests assert terminal reason is present and state-consistent
- acceptance gate includes checks for terminal reason evidence

## Phase 4: Patch Output

### Task 4.1: Snapshot patch export

- Export human-readable unified diff patch.
- Export machine-readable JSON patch.

Acceptance:

- patch artifacts are generated for successful repaired runs
- unit tests assert patch determinism from same snapshot history
- integration tests assert patch includes reviewed replacements

### Task 4.2: Patch provenance linking

- Link patch outputs to task/artifact/policy/intervention provenance chain.

Acceptance:

- records include stable linkage identifiers for patch entries
- traceability doc maps patch output fields to record provenance entries

## Phase 5: Migration and Cleanup

### Task 5.1: Retire temporary test-only workflow components

- Remove or minimize test-specific localizer/engine once production abstractions
  are sufficient.

Acceptance:

- real-case integration scenarios use production localizer/engine contracts
- test-only components are either deleted or explicitly marked as temporary

### Task 5.2: Update traceability and acceptance docs

- Refresh v1.5 traceability matrix after implementation.
- Ensure acceptance gate docs match real checks.

Acceptance:

- no stale module/test mappings in traceability matrix
- acceptance gate docs and script behavior are aligned

## Release Readiness Checklist

- All phase acceptance criteria are satisfied.
- `tests/repair` passes on supported environments.
- acceptance gate passes:
  - `cd python && uv run python scripts/check_repair_acceptance_gate.py`
- v1 artifacts are cleaned up by maintainers before adopting v1.5 baseline.
