# isabelle-repl

A Scala gRPC server + Python client that exposes Isabelle as an interactive REPL with:

- Multiple simultaneous proof states (branching, parallel tactic exploration)
- Non-destructive state transitions (every `execute` produces a new state ID)
- Efficient theory loading with two-level preamble caching
- Sledgehammer integration for automated proof search

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Proof engine | [Isabelle 2025](https://isabelle.in.tum.de/) |
| Scala–Isabelle bridge | [scala-isabelle 0.4.5](https://github.com/dominique-unruh/scala-isabelle) |
| Server transport | gRPC (ScalaPB + Netty-shaded) |
| Build system (Scala) | sbt 1.x, Scala 2.13 |
| JVM | Java 17 (Temurin recommended) |
| Python runtime | Python 3.12+, managed with [uv](https://github.com/astral-sh/uv) |
| Code generation | ScalaPB (Scala stubs), grpcio-tools (Python stubs) |

---

## Architecture

```
src/main/
  protobuf/repl.proto              # gRPC service definition (source of truth)
  scala/
    IsaReplServer.scala            # gRPC service impl; session map + entry point
    IsabelleSession.scala          # One Isabelle process; theory/state caches
    TheoryManager.scala            # Theory parsing, import resolution, Sledgehammer

python/src/isa_repl/
  client.py                        # IsaReplClient — thin gRPC wrapper, returns dataclasses
  repl_pb2*.py                     # Auto-generated; do not edit by hand
```

**Proof state model.** Every `execute` allocates a fresh UUID and leaves the source state intact in the session's `stateMap`. Branching is safe without cloning.

**Two caches, lazy execution.** `load_theory` parses the `.thy` file and stores the resulting transition list (`theoryCache`) — no execution yet. `init_state` looks for the highest already-executed checkpoint ≤ the target line (`initCache: (path, line) → stateId`), replays only the delta, and caches the new result. Repeated calls to the same line are O(1); nearby lines share work.

**Session roots.** Two ROOT file layouts are supported: a single ROOT with `in SubDir` clauses (Isabelle standard library style), and AFP-style per-directory ROOT files.

---

## Step-by-Step Setup

### Prerequisites

- Isabelle 2025 installed (default path assumed: `~/Isabelle2025`)
- Internet access for SDK/tool downloads

---

### 1. Install SDKMAN and Java 17

[SDKMAN](https://sdkman.io/) manages JVM installations without touching system packages.

```bash
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"

sdk install java 17.0.18-tem
sdk use java 17.0.18-tem

java -version   # should print openjdk 17.0.18
```

> If you open a new shell, run `source "$HOME/.sdkman/bin/sdkman-init.sh"` (or add it to `~/.bashrc` / `~/.zshrc`) before using `java` or `sbt`.

---

### 2. Install sbt

```bash
sdk install sbt
sbt --version   # e.g. sbt 1.10.x
```

---

### 3. Install uv (Python package manager)

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
# Follow the prompt to add uv to PATH, then:
uv --version
```

---

### 4. Clone and compile the Scala server

```bash
git clone <repo-url> isabelle-repl
cd isabelle-repl

# First compile generates ScalaPB stubs from repl.proto automatically
sbt compile
```

Compilation downloads all dependencies (~300 MB on first run) and generates Scala gRPC stubs under `target/scala-2.13/src_managed/`.

---

### 5. Start the server

```bash
sbt run
```

The server starts on **port 50051** and prints a startup message. Leave this terminal open — the server must be running before connecting from Python.

The Scala tests in `src/test/` are integration tests that require Isabelle 2025 and AFP to be installed at the configured paths:

```bash
sbt test
```

---

### 6. Set up the Python client

```bash
cd python

# Install all dependencies (including dev tools for code generation)
uv sync

# Activate the virtual environment so scripts can use the installed tools
source .venv/bin/activate
```

---

### 7. Regenerate gRPC stubs (only needed after editing repl.proto)

```bash
# Run from inside python/ with the venv active
bash scripts/gen_proto.sh
```

The script:
1. Invokes `grpc_tools.protoc` to generate `repl_pb2.py`, `repl_pb2.pyi`, and `repl_pb2_grpc.py`
2. Patches the generated `repl_pb2_grpc.py` to use relative imports (`from . import repl_pb2`) so the package works correctly when installed

> **Do not edit `repl_pb2*.py` by hand** — they are always overwritten by the script.

---

### 8. Run Python tests

Integration tests require the Scala server (`sbt run`) and Isabelle 2025.

```bash
cd python

uv run pytest                        # all tests (smoke tests pass without a server)
uv run pytest tests/test_smoke.py    # smoke only — no server needed
uv run pytest -m integration         # integration tests only
```

Environment variables (all optional, defaults shown):

| Variable | Default |
|----------|---------|
| `ISA_REPL_HOST` | `localhost` |
| `ISA_REPL_PORT` | `50051` |
| `ISABELLE_PATH` | `/home/lxk/Isabelle2025` |
| `AFP_PATH` | `/home/lxk/repositories/afp-2025/thys` |

Tests auto-skip (via `pytest.skip`) when the server is unreachable.

---

## Proof Repair — Worked Example

A typical use-case is **proof repair**: given a `.thy` file where a lemma's proof is broken or missing, enumerate candidate tactics and check which one closes the goal.

The example below works against `python/tests/theories/Simple.thy`:

```python
from pathlib import Path

from isa_repl import IsaReplClient

ISABELLE_PATH = "/home/lxk/Isabelle2025"
THEORY_PATH = str(Path("python/tests/theories/Simple.thy").absolute())
WORKING_DIR = str(Path("python/tests").absolute())

client = IsaReplClient(host="localhost", port=50051)

# ── 1. Create a session (one Isabelle process) ────────────────────────────────
session_id = client.create_session(
    isa_path=ISABELLE_PATH,
    logic="HOL",
    working_directory=WORKING_DIR,
)

# ── 2. Parse and cache the theory file ───────────────────────────────────────
#    Returns the number of top-level commands found.
cmd_count = client.load_theory(session_id, THEORY_PATH)
print(f"Loaded {cmd_count} commands")

# ── 3. Discover proof obligations ────────────────────────────────────────────
#    only_proof_stmts=True returns only lemma/theorem/... declarations.
lemmas = client.list_theory_commands(session_id, THEORY_PATH, only_proof_stmts=True)
for cmd in lemmas:
    print(f"  line {cmd.line:3d}  [{cmd.kind}]  {cmd.text.strip()}")
# Example output:
#   line   5  [lemma]  lemma trivial: "True"
#   line   8  [lemma]  lemma add_comm_nat: "(x :: nat) + y = y + x"
#   line  11  [lemma]  lemma conj_easy: "⟦P; Q⟧ ⟹ P ∧ Q"
#   line  14  [lemma]  lemma nat_not_zero: "(n :: nat) > 0 ⟹ n ≠ 0"

# ── 4. Initialise a proof state just before a lemma ──────────────────────────
#    after_line=8 positions the state after executing line 8 (the lemma header),
#    entering PROOF mode with the goal open.
result = client.init_state(session_id, THEORY_PATH, after_line=8)
if not result.is_success():
    raise RuntimeError(f"init_state failed: {result.error.error_msg}")

state = result.unwrap()
print(f"State: mode={state.mode}, proof_level={state.proof_level}")
# State: mode=PROOF, proof_level=1

# Inspect the open goal (expensive — only when needed)
info = client.get_state_info(state.state_id, include_text=True)
print("Goal:\n", info.proof_state_text)
# Goal:
#  proof (prove)
#  goal (1 subgoal):
#   1. x + y = y + x

# ── 5. Try candidate tactics ──────────────────────────────────────────────────
#    execute() is non-destructive: state.state_id is unchanged after each call.
candidates = ["by simp", "by auto", "by blast", "by (simp add: add.commute)"]

for tactic in candidates:
    r = client.execute(state.state_id, tactic, timeout_ms=10_000)
    if r.proof_is_finished():
        print(f"✓  {tactic!r} closes the goal")
    elif r.status == "ERROR":
        print(f"✗  {tactic!r} → {r.error_msg.splitlines()[0]}")
    elif r.status == "TIMEOUT":
        print(f"⏱  {tactic!r} timed out")
    else:
        print(f"~  {tactic!r} → {r.status} (proof_level={r.proof_level})")

# Example output:
# ✓  'by simp' closes the goal
# ✓  'by auto' closes the goal
# ✗  'by blast' → Failed
# ✓  'by (simp add: add.commute)' closes the goal

# ── 6. Batch exploration (parallel) ──────────────────────────────────────────
#    execute_many sends all tactics to the server in one RPC and runs them
#    in parallel.  Results are returned in the same order as tactics.
results = client.execute_many(
    state.state_id,
    candidates,
    timeout_ms=10_000,
    drop_failed=True,  # auto-free state IDs for failed tactics
)
winning = [tac for tac, r in zip(candidates, results) if r.proof_is_finished()]
print("Winning tactics:", winning)

# ── 7. Sledgehammer (automated proof search) ─────────────────────────────────
found, tactic, sh_result = client.run_sledgehammer(
    state.state_id,
    timeout_ms=60_000,
    sledgehammer_timeout_ms=30_000,
)
if found:
    print(f"Sledgehammer found: {tactic}")
    # Sledgehammer found: by (simp add: add.commute)

# ── 8. Clean up ───────────────────────────────────────────────────────────────
client.drop_all_states(session_id)
client.destroy_session(session_id)
client.close()
```

### Key points illustrated

| Concept | API call | Notes |
|---------|----------|-------|
| One process per session | `create_session` | Supports multiple concurrent sessions |
| Parse once, query many | `load_theory` then `list_theory_commands` | Preamble cached in server |
| Position by line or command text | `init_state(after_line=N)` or `init_state(after_command="…")` | Both reach same ML state |
| Non-destructive execution | `execute(state_id, tactic)` | `state_id` remains valid after call |
| Parallel tactic search | `execute_many` | Single RPC, server runs in parallel |
| Goal inspection is opt-in | `get_state_info(include_text=True)` | Omit for high-throughput loops |
| Automated proof search | `run_sledgehammer` | Uses cvc5, z3, vampire, verit, … |

---

## gRPC API Reference

| RPC | Request → Response | Description |
|-----|--------------------|-------------|
| `CreateSession` | `CreateSessionRequest → CreateSessionResponse` | Start an Isabelle process |
| `DestroySession` | `SessionRef → Empty` | Stop the process and free resources |
| `LoadTheory` | `LoadTheoryRequest → LoadTheoryResponse` | Parse and cache a `.thy` file |
| `ListTheoryCommands` | `ListCommandsRequest → ListCommandsResponse` | List commands (optionally only proof statements) |
| `InitState` | `InitStateRequest → InitStateResponse` | Create a proof state at a given line or command |
| `DropState` | `DropStateRequest → Empty` | Free one or more state IDs |
| `DropAllStates` | `SessionRef → Empty` | Free all states in a session |
| `Execute` | `ExecuteRequest → StateResult` | Apply a tactic; allocates a new state ID |
| `ExecuteBatch` | `ExecuteBatchRequest → ExecuteBatchResponse` | Apply multiple tactics in parallel |
| `RunSledgehammer` | `SledgehammerRequest → SledgehammerResponse` | Automated proof search |
| `GetStateInfo` | `GetStateInfoRequest → StateInfo` | Query mode / proof level / goal text |

See [src/main/protobuf/repl.proto](src/main/protobuf/repl.proto) for full message definitions.

### Execution status codes

| Status | Meaning |
|--------|---------|
| `SUCCESS` | Tactic succeeded; proof still open |
| `PROOF_COMPLETE` | Proof closed (proof level dropped to 0) |
| `ERROR` | Tactic failed; `error_msg` contains the Isabelle error |
| `TIMEOUT` | Execution exceeded `timeout_ms` |

---

## Project Structure

```
.
├── build.sbt                           # Scala build + dependency config
├── project/
│   ├── plugins.sbt                     # sbt-scalafmt, sbt-protoc, ScalaPB plugin
│   └── build.properties
├── src/main/
│   ├── protobuf/repl.proto             # gRPC service definition (shared source of truth)
│   └── scala/
│       ├── IsaReplServer.scala         # Server entry point + gRPC method implementations
│       ├── IsabelleSession.scala       # Session: Isabelle process + state + theory caches
│       └── TheoryManager.scala         # Theory parsing, import resolution, Sledgehammer
└── python/
    ├── pyproject.toml                  # Package metadata (uv / pip)
    ├── scripts/gen_proto.sh            # Regenerate Python gRPC stubs from repl.proto
    ├── src/isa_repl/
    │   ├── __init__.py
    │   ├── client.py                   # IsaReplClient public API
    │   └── repl_pb2*.py               # Auto-generated; do not edit
    └── tests/
        ├── theories/
        │   └── Simple.thy             # Reference theory used by integration tests
        ├── conftest.py                 # Fixtures: client, hol_session, hol_afp_session
        ├── test_smoke.py              # Import/instantiation checks (no server needed)
        ├── test_integration_simple.py # Full API coverage against Simple.thy
        └── test_integration_afp.py    # AFP Completeness theory tests
```

---

## Key Design Decisions

**Non-destructive execution.** `execute` always allocates a fresh state ID; the source state is an immutable ML value in Isabelle's heap. Branching and parallel tactic exploration require no explicit clone step.

**Lazy execution with checkpoint cache.** `LoadTheory` only parses — it stores the transition list but executes nothing. `InitState` looks up the highest already-executed checkpoint ≤ the target line, replays only the delta, and caches the result as a new checkpoint. Repeated calls to the same line are O(1); nearby lines share work automatically.

**`GetStateInfo` is opt-in and expensive.** `Execute` and `InitState` return a lightweight `StateResult`. Request `include_text=True` (or call `GetStateInfo`) only when the human-readable goal display is needed.

**Async gRPC server.** All service methods return `Future[T]` and run on a cached thread pool, keeping the server responsive under concurrent load from multiple Python clients.
