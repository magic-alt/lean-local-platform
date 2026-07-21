#!/usr/bin/env bash
set -euo pipefail

EXAMPLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$EXAMPLE_DIR/../.." && pwd)"
WORKSPACE_ROOT="$(cd "$REPO_ROOT/.." && pwd)"
DATA_DIR="${LEAN_DATA_DIR:-$WORKSPACE_ROOT/Data}"
RESULTS_DIR="$REPO_ROOT/web/runtime/examples/lean-docker-demo/results"

mkdir -p "$RESULTS_DIR"

docker run --rm \
  --name lean-docker-demo \
  -v "$EXAMPLE_DIR/config.json:/Lean/Launcher/bin/Debug/config.json:ro" \
  -v "$EXAMPLE_DIR/DockerDemoAlgorithm.py:/Lean/DockerDemoAlgorithm.py:ro" \
  -v "$DATA_DIR:/Lean/Data:ro" \
  -v "$RESULTS_DIR:/Lean/Results" \
  quantconnect/lean:latest

echo
echo "Result files:"
find "$RESULTS_DIR" -maxdepth 2 -type f | sort
