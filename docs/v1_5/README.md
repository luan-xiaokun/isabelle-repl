# Docs v1.5

This folder is the authoritative home for v1.5 materials.

## Authority

This folder is the authoritative runtime baseline for current proof-repair
implementation work.

The module PRDs in `docs/modules/` remain active design context, but current
implementation planning should distinguish the implemented subset from future
design intent. When runtime behavior and older v1 text disagree, prefer the
v1.5 PRD, contract, acceptance-gate, and traceability documents.

## Structure

- `prd/`
  - v1.5 product requirements
- `contracts/`
  - executable semantic contracts (state machine, invariants)
- `architecture/`
  - traceability and architecture-to-code mapping
- `implementation/`
  - staged implementation plan chapters
- `testing/`
  - acceptance-gate design and execution policy

## Entry Points

- PRD: [`./prd/theory-repair-run-prd.md`](./prd/theory-repair-run-prd.md)
- State contract:
  [`./contracts/theory-repair-run-state-machine-contract.md`](./contracts/theory-repair-run-state-machine-contract.md)
- Implementation plan: [`./implementation/README.md`](./implementation/README.md)
- Implementation checklist + acceptance:
  [`./implementation/task-checklist-and-acceptance.md`](./implementation/task-checklist-and-acceptance.md)
