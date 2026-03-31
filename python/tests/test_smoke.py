"""Smoke tests — verify that the package imports correctly without a running server."""


def test_import_isabelle_repl():
    import isabelle_repl  # noqa: F401


def test_import_client():
    from isabelle_repl.client import IsabelleReplClient  # noqa: F401


def test_client_instantiation_no_connect():
    """IsabelleReplClient can be instantiated without connecting to a server."""
    from isabelle_repl.client import IsabelleReplClient

    # Just instantiate — gRPC channels are lazy, no actual connection yet
    client = IsabelleReplClient(host="localhost", port=50051)
    client.close()
