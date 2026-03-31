#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROTO_DIR="$REPO_ROOT/src/main/protobuf"
OUT_DIR="$REPO_ROOT/python/src/isabelle_repl"

echo "Generating Python gRPC stubs from $PROTO_DIR/repl.proto"
echo "Output directory: $OUT_DIR"

python -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --pyi_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/repl.proto"

python - <<'PY'
from pathlib import Path

path = Path("src/isabelle_repl/repl_pb2_grpc.py")
text = path.read_text()
text = text.replace(
    "import repl_pb2 as repl__pb2",
    "from . import repl_pb2 as repl__pb2",
)
path.write_text(text)
PY

echo "Done."
