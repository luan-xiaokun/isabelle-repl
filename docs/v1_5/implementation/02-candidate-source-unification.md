# 02. Candidate Source Unification

## Objective

Unify automatic candidate generation and review-provided candidates under one
stable engine-facing contract.

## Module Decisions

- introduce `CandidateSource` contract:
  - emits candidate stream
  - includes source metadata for records/provenance
- implement two sources:
  - auto/rule-first source
  - review-injected source

## Validation Contract

All candidates, regardless of source, must pass:

1. REPL execution success
2. block-contract adapter validation

## Acceptance Criteria

- no separate test-only engine is required for review candidate workflows
- reviewed candidate path produces same validation evidence fields as auto path
- policy/hook behavior remains orchestrator-owned
