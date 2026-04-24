# Theory Repair Run Architecture

Status: Sub-architecture view for the top-level run

Companion documents:

- [`../modules/theory-repair-run-prd.md`](../modules/theory-repair-run-prd.md)
- [`../glossary-and-terminology.md`](../glossary-and-terminology.md)
- [`./overview.md`](./overview.md)

## Diagram

```mermaid
flowchart TB
    subgraph Run["Theory Repair Run"]
        orchestrator["Theory repair orchestrator"]
        execute["Execute current working theory snapshot"]
        cont["Continuation selection\n(contract-constrained)"]
        subgraph StateLayer["Repair state and records\n(foundational module)"]
            snapshot["Working theory snapshot"]
            runstate["Run state\nactive | awaiting_review | stopped | completed"]
            records["Run-level records"]
        end
    end

    classify["Failure classification\nand localization"]
    task["Repair task engine"]
    policy["Policy and risk gate"]
    hook["Intervention / review hook"]

    orchestrator --> execute
    execute --> orchestrator
    orchestrator --> classify
    classify --> orchestrator
    orchestrator --> task
    task --> orchestrator
    orchestrator --> policy
    policy --> orchestrator
    orchestrator --> cont
    cont --> orchestrator
    orchestrator --> hook
    hook --> orchestrator

    execute --> snapshot
    task --> snapshot
    orchestrator --> runstate
    orchestrator --> records
    task --> records
    cont --> records
    hook --> records
    policy --> records
```

## Reading Guide

- `theory repair run` is the process container.
- `theory repair orchestrator` is the controlling component inside that run.
- `repair state and records` is modeled as a foundational module inside the run
  container rather than as an external utility.
- This foundational module contains:
  - `working theory snapshot` (execution substrate and mutable repaired text
    state)
  - `run-level records` and `run state` (auditable process model)
- Classification/localization, task engine, policy, and hooks are peer modules
  invoked by orchestrator rather than orchestrator internals.
- Continuation remains constrained by block-contract semantics.
- Intervention / review pauses run progression via `awaiting_review` state rather
  than as a continuation kind.
- Run-level records remain separate from task-local trace.
