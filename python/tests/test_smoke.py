"""Smoke tests — verify that the package imports correctly without a running server."""


def test_import_isa_repl():
    import isa_repl  # noqa: F401


def test_import_client():
    from isa_repl.client import IsaReplClient  # noqa: F401


def test_client_instantiation_no_connect():
    """IsaReplClient can be instantiated without connecting to a server."""
    from isa_repl.client import IsaReplClient

    # Just instantiate — gRPC channels are lazy, no actual connection yet
    client = IsaReplClient(host="localhost", port=50051)
    client.close()
