# isa-repl Python Client

Python client SDK for the [Isabelle REPL gRPC server](../README.md).

This package provides a Python interface to an Isabelle theorem prover session via gRPC.
It does **not** start or manage the Scala server — you must start it separately first.

## Prerequisites

- The Scala server must be built and running (see root [README](../README.md))
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

Using `uv`:

```bash
cd python
uv sync
```

Using `pip` (editable install):

```bash
cd python
pip install -e .
```

## Usage

```python
from isa_repl import IsaReplClient

# The Scala server must already be running on localhost:50051
with IsaReplClient() as client:
    session_id = client.create_session(
        isa_path="/path/to/Isabelle2025",
        logic="HOL",
        working_directory="/path/to/your/theories",
    )
    state = client.init_state(
        session_id,
        "/path/to/MyTheory.thy",
        after_line=42,
    ).unwrap()
    result = client.execute(state.state_id, "by simp")
    print(result.status)  # "PROOF_COMPLETE" or "ERROR"
    client.destroy_session(session_id)
```

If connection fails with `StatusCode.UNAVAILABLE`, the Scala server is not running.
Start it with `sbt run` from the repository root.

## Regenerating protobuf stubs

If [`src/main/protobuf/repl.proto`](../src/main/protobuf/repl.proto) changes,
regenerate the Python stubs:

```bash
cd python
uv run bash scripts/gen_proto.sh
```

This requires `grpcio-tools` (included in dev dependencies).

## Running tests

```bash
cd python
uv run pytest tests/test_smoke.py tests/test_client_unit.py
uv run pytest -m integration_local
uv run pytest -m integration_afp_heavy
uv run pytest -m integration
uv run pytest
```

Notes:

- `test_smoke.py` and `test_client_unit.py` do not require a running server
- `integration_local` requires a running server plus Isabelle (`ISABELLE_PATH`)
- `integration_afp_heavy` additionally requires AFP (`AFP_PATH`)
- Integration tests use the shared fixtures in [`tests/conftest.py`](tests/conftest.py), which auto-skip when prerequisites are missing
- Auto-generated protobuf modules are excluded from coverage so the report reflects handwritten client code
