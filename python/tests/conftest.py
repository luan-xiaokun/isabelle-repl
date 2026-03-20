"""
Shared fixtures for integration tests.

Prerequisites:
  - The Isabelle REPL gRPC server must be running:  sbt run  (repo root)
  - Isabelle 2025 installed at ISABELLE_PATH  (default: /home/lxk/Isabelle2025)
  - AFP 2025 checked out at AFP_PATH          (default: /home/lxk/repositories/afp-2025/thys)

Environment overrides:
  ISA_REPL_HOST   gRPC server host  (default: localhost)
  ISA_REPL_PORT   gRPC server port  (default: 50051)
  ISABELLE_PATH   Isabelle installation root
  AFP_PATH        AFP thys/ root
"""

import os
import pytest
import grpc

from isa_repl.client import IsaReplClient

# ── Configuration ─────────────────────────────────────────────────────────────

SERVER_HOST = os.environ.get("ISA_REPL_HOST", "localhost")
SERVER_PORT = int(os.environ.get("ISA_REPL_PORT", "50051"))
ISABELLE_PATH = os.environ.get("ISABELLE_PATH", "/home/lxk/Isabelle2025")
AFP_PATH = os.environ.get("AFP_PATH", "/home/lxk/repositories/afp-2025/thys")

THEORIES_DIR = os.path.join(os.path.dirname(__file__), "theories")
COMPLETENESS_WORKDIR = os.path.join(AFP_PATH, "Completeness")


# ── Client ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def client():
    """gRPC client shared across the entire test session."""
    with IsaReplClient(host=SERVER_HOST, port=SERVER_PORT) as c:
        yield c


# ── HOL session (no AFP) — used by test_integration_simple.py ────────────────


@pytest.fixture(scope="module")
def hol_session(client):
    """
    Isabelle HOL session with working directory = tests/theories/.
    Created once per test module; destroyed after the module finishes.
    """
    try:
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=THEORIES_DIR,
        )
    except grpc.RpcError as e:
        pytest.skip(
            f"Isabelle REPL server unavailable or session creation failed: {e.details()}"
        )
    yield session_id
    try:
        client.destroy_session(session_id)
    except grpc.RpcError:
        pass  # best-effort cleanup


# ── HOL + AFP session — used by test_integration_afp.py ──────────────────────


@pytest.fixture(scope="module")
def hol_afp_session(client):
    """
    Isabelle HOL session with AFP session roots.
    Working directory = AFP Completeness/ so the server can resolve local .thy imports.
    """
    try:
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=COMPLETENESS_WORKDIR,
            # session_roots=["/home/lxk/Isabelle2025/src/HOL", AFP_PATH],
        )
    except grpc.RpcError as e:
        pytest.skip(
            f"Isabelle REPL server unavailable or AFP session creation failed: {e.details()}"
        )
    yield session_id
    try:
        client.destroy_session(session_id)
    except grpc.RpcError:
        pass
