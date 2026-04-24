# Isabelle REPL Architecture

This diagram focuses on the architecture of `isabelle-repl` itself.

It intentionally stays at the component level:

- no code-level snippets
- no file-by-file structure
- no proof-repair-specific orchestration logic

```mermaid
flowchart TB
    caller["External caller"]

    subgraph Client["Client Layer"]
        pyclient["Python client / other clients"]
    end

    subgraph Api["Service Interface"]
        grpc["gRPC API contract"]
    end

    subgraph Server["REPL Service Core"]
        sessionmgr["Session manager"]
        statereg["State registry"]
        replay["Replay and checkpoint planner"]
        theorysvc["Theory parsing and command service"]
        workspacesvc["Workspace and import resolver"]
        querysvc["State query service"]
        autosvc["Automation bridge"]
    end

    subgraph Runtime["Execution Runtime"]
        isabelle["Isabelle process runtime"]
        sledgehammer["Sledgehammer and prover tools"]
    end

    subgraph Inputs["Project Inputs"]
        theories["Theory files"]
        roots["ROOT files / session roots / AFP-style workspaces"]
    end

    caller --> pyclient
    pyclient --> grpc
    grpc --> sessionmgr

    sessionmgr --> statereg
    sessionmgr --> replay
    sessionmgr --> theorysvc
    sessionmgr --> querysvc

    replay --> theorysvc
    theorysvc --> workspacesvc
    querysvc --> statereg
    autosvc --> isabelle
    autosvc --> sledgehammer

    theorysvc --> isabelle
    replay --> isabelle
    querysvc --> isabelle

    workspacesvc --> roots
    theorysvc --> theories
```

## Reading guide

The main architectural idea is that `isabelle-repl` acts as a stateful REPL
service on top of Isabelle:

- clients talk to a stable RPC boundary
- the service manages long-lived Isabelle sessions
- proof states evolve non-destructively and are tracked through state IDs
- theory loading, replay, querying, and optional automation are exposed as
  reusable primitives

In other words, `isabelle-repl` is the substrate that higher-level tools can
build on, rather than a proof-repair system by itself.
