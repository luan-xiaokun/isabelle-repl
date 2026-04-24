# 03. Run State and Records v1.5

## Objective

Upgrade run state semantics and records schema to support explicit terminal
modes and stronger replay/analysis evidence.

## State Model

- `active`
- `awaiting_review`
- `stopped`
- `completed` (target-boundary completion)
- `finished` (theory-wide completion)

## Records Decisions

- schema version: `v1.5`
- v1 compatibility: not required
- old artifacts: may be deleted
- terminal records include explicit `terminal_reason`

## Patch Output

Snapshot exports both:

- unified diff patch
- machine-readable JSON patch

## Acceptance Criteria

- terminal semantics are distinguishable in state, logs, and records
- acceptance gate validates `terminal_reason` and state transition invariants
- run metadata includes theory identity and sufficient provenance for replay
