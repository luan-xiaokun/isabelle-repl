# isa-repl Python Client

Python client SDK for the [Isabelle REPL gRPC server](../README.md).

This package provides a Python interface to an Isabelle theorem prover session via gRPC.
It does **not** start or manage the Scala server — you must start it separately first.

## Prerequisites

- The Scala server must be built and running (see root [README](../README.md))
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

Using uv:

```bash
cd python
uv sync
```

Using pip (editable install):

```bash
cd python
pip install -e .
```

## Usage

```python
from isa_repl.client import IsaReplClient

# The Scala server must already be running on localhost:50051
with IsaReplClient() as client:
    session_id = client.create_session(
        isa_path="/path/to/Isabelle2025",
        logic="HOL",
        working_directory="/path/to/your/theories",
    )
    state = client.init_state(session_id, "/path/to/MyTheory.thy", line=42)
    result = client.execute(state.state_id, "by simp")
    print(result.status)  # "PROOF_COMPLETE" or "ERROR"
    client.destroy_session(session_id)
```

If connection fails with `StatusCode.UNAVAILABLE`, the Scala server is not running.
Start it with `sbt run` from the repository root.

## Regenerating protobuf stubs

If `src/main/protobuf/isa_repl.proto` changes, regenerate the Python stubs:

```bash
cd python
uv run bash scripts/gen_proto.sh
```

This requires `grpcio-tools` (included in dev dependencies).

## Running tests

```bash
cd python
uv run pytest
```
