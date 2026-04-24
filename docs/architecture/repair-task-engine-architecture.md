# Repair Task Engine Architecture

Status: Sub-architecture view for the repair task engine

Companion documents:

- [`../modules/repair-task-engine-prd.md`](../modules/repair-task-engine-prd.md)
- [`../glossary-and-terminology.md`](../glossary-and-terminology.md)
- [`./overview.md`](./overview.md)

## Diagram

```mermaid
flowchart TB
    spec["Task spec"]
    runtime["Engine runtime"]
    controller["Task controller"]
    generators["Candidate generators"]
    repl["Isabelle REPL service"]
    policy["Policy and risk gate"]
    hooks["Intervention / review hooks"]
    obs["Task-local observation store"]
    trace["Task-local trace"]
    records["Run-level records"]

    spec --> runtime
    controller --> runtime
    controller --> generators
    generators --> runtime
    runtime --> repl
    runtime --> policy
    runtime --> hooks
    runtime --> obs
    runtime --> trace
    runtime --> records
```

## Reading Guide

- `engine runtime` owns task-local execution semantics.
- `task controller` chooses the next action but does not own policy or
  top-level continuation.
- `candidate generators` are proposal backends invoked through runtime-mediated
  actions.
- Task-local observation and trace stay inside the task path and only selected
  events are promoted to run-level records.
