#!/usr/bin/env bash
set -euo pipefail

PLATFORM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$PLATFORM_DIR/.." && pwd)"
DATA_DIR="${LEAN_DATA_DIR:-$WORKSPACE_ROOT/Data}"
RESULTS_DIR="$PLATFORM_DIR/results"

mkdir -p "$RESULTS_DIR"

docker run --rm \
  --name lean-docker-demo \
  -v "$PLATFORM_DIR/config.json:/Lean/Launcher/bin/Debug/config.json:ro" \
  -v "$PLATFORM_DIR/DockerDemoAlgorithm.py:/Lean/DockerDemoAlgorithm.py:ro" \
  -v "$DATA_DIR:/Lean/Data:ro" \
  -v "$RESULTS_DIR:/Lean/Results" \
  quantconnect/lean:latest

echo
echo "Result files:"
find "$RESULTS_DIR" -maxdepth 2 -type f | sort
