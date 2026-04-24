# Proof Repair Architecture Docs

Status: Architecture index for the proof-repair design set

This folder contains architecture-oriented documents and diagrams for the proof
repair system.

The architecture material is intentionally split into two layers:

- a high-level overview architecture that shows relationships between the main
  modules
- focused sub-architecture documents for important high-level modules

## Overview

- [`overview.md`](./overview.md)
- [`overview.png`](./figures/overview.png)

Use the overview first when you want to understand the top-level decomposition
between:

- theory repair run
- theory repair orchestrator
- failure classification and localization
- repair task engine
- policy and risk gate
- intervention / review hooks
- repair state / records
- Isabelle REPL service

## Sub-Architecture Docs

- [`theory-repair-run-architecture.md`](./theory-repair-run-architecture.md)
- [`repair-task-engine-architecture.md`](./repair-task-engine-architecture.md)
- [`policy-and-risk-gate-architecture.md`](./policy-and-risk-gate-architecture.md)
- [`intervention-and-review-hooks-architecture.md`](./intervention-and-review-hooks-architecture.md)
- [`repair-agent-traceability-matrix.md`](./repair-agent-traceability-matrix.md)
  (redirect to v1.5 traceability set)

## Notes

- Detailed behavior remains authoritative in the PRDs.
- These documents focus on structure, authority boundaries, and major dataflow.
