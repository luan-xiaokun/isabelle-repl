# Repair Acceptance Gate (v1.5)

## Goal

Enforce architecture-meaningful acceptance, not only raw test pass status.

## Gate Components

1. Required docs exist and contain mandatory sections.
2. Acceptance marker suite passes:
   - `pytest -m acceptance_gate`
3. No skipped tests inside the acceptance marker suite.
4. Runtime boundary enforcement:
   - test-only helper modules must not live under `python/src/isabelle_repair/*`.

## Execution

- `cd python && uv run python scripts/check_repair_acceptance_gate.py`

## Scope

- review pause/resume lifecycle
- policy/hook constrained behavior
- records/log consistency
- real-case regression scenarios marked as acceptance when stabilized
