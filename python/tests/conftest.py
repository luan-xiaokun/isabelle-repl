"""
Shared fixtures for integration tests.

Prerequisites:
  - The Isabelle REPL gRPC server must be running:  sbt run  (repo root)
  - Isabelle 2025 installed at ISABELLE_PATH  (default: /home/lxk/Isabelle2025)
  - AFP 2025 checked out at AFP_PATH (default: /home/lxk/repositories/afp-2025/thys)

Environment overrides:
  ISABELLE_REPL_HOST   gRPC server host  (default: localhost)
  ISABELLE_REPL_PORT   gRPC server port  (default: 50051)
  ISABELLE_PATH   Isabelle installation root
  AFP_PATH        AFP thys/ root
"""

import grpc
import pytest
from test_env import load_test_env, missing_local_prereqs

from isabelle_repl.client import IsaReplClient

# ── Configuration ─────────────────────────────────────────────────────────────

TEST_ENV = load_test_env()

SERVER_HOST = TEST_ENV.server_host
SERVER_PORT = TEST_ENV.server_port
ISABELLE_PATH = str(TEST_ENV.isabelle_path)
AFP_PATH = str(TEST_ENV.afp_path)
HOL_SRC = str(TEST_ENV.hol_src)

THEORIES_DIR = str(TEST_ENV.theories_dir)
COMPLETENESS_WORKDIR = str(TEST_ENV.completeness_workdir)
QUERY_OPTIMIZATION_WORKDIR = str(TEST_ENV.query_optimization_workdir)


def _skip_if_local_prereqs_missing(require_afp: bool) -> None:
    missing = missing_local_prereqs(TEST_ENV, require_afp=require_afp)
    if missing:
        msg = "Local integration prerequisites not met:\n- " + "\n- ".join(missing)
        pytest.skip(msg)


def _skip_if_server_unreachable() -> None:
    channel = grpc.insecure_channel(f"{SERVER_HOST}:{SERVER_PORT}")
    try:
        grpc.channel_ready_future(channel).result(timeout=1)
    except grpc.FutureTimeoutError:
        pytest.skip(
            "Isabelle REPL server unreachable at "
            f"{SERVER_HOST}:{SERVER_PORT}. Start it with `sbt run`."
        )
    finally:
        channel.close()


# ── Client ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def client():
    """gRPC client shared across the entire test session."""
    _skip_if_local_prereqs_missing(require_afp=False)
    _skip_if_server_unreachable()
    with IsaReplClient(host=SERVER_HOST, port=SERVER_PORT) as c:
        yield c


# ── HOL session (no AFP) — used by test_integration_simple.py ────────────────


@pytest.fixture(scope="module")
def hol_session(client):
    """
    Isabelle HOL session with working directory = tests/theories/.
    Created once per test module; destroyed after the module finishes.
    """
    _skip_if_local_prereqs_missing(require_afp=False)
    try:
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=THEORIES_DIR,
        )
    except grpc.RpcError as e:
        pytest.skip(
            "Isabelle REPL server unavailable or session creation failed: "
            + str(e.details())
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
    _skip_if_local_prereqs_missing(require_afp=True)
    try:
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=COMPLETENESS_WORKDIR,
            session_roots=[HOL_SRC, AFP_PATH],
        )
    except grpc.RpcError as e:
        pytest.skip(
            "Isabelle REPL server unavailable or AFP session creation failed: "
            + str(e.details())
        )
    yield session_id
    try:
        client.destroy_session(session_id)
    except grpc.RpcError:
        pass


@pytest.fixture(scope="module")
def query_optimization_afp_session(client):
    """
    Isabelle HOL session with AFP session roots and Query_Optimization as workdir.
    Used to validate cross-AFP session imports and whole-theory replay.
    """
    _skip_if_local_prereqs_missing(require_afp=True)
    try:
        session_id = client.create_session(
            isa_path=ISABELLE_PATH,
            logic="HOL",
            working_directory=QUERY_OPTIMIZATION_WORKDIR,
            session_roots=[HOL_SRC, AFP_PATH],
        )
    except grpc.RpcError as e:
        pytest.skip(
            "Isabelle REPL server unavailable or Query_Optimization session "
            f"creation failed: {e.details()}"
        )
    yield session_id
    try:
        client.destroy_session(session_id)
    except grpc.RpcError:
        pass
