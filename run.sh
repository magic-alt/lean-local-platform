#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

mkdir -p "$RESULTS_DIR"

docker run --rm \
  --name lean-docker-demo \
  -v "$SCRIPT_DIR/config.json:/Lean/Launcher/bin/Debug/config.json:ro" \
  -v "$SCRIPT_DIR/DockerDemoAlgorithm.py:/Lean/DockerDemoAlgorithm.py:ro" \
  -v "$REPO_ROOT/Data:/Lean/Data:ro" \
  -v "$RESULTS_DIR:/Lean/Results" \
  quantconnect/lean:latest

echo
echo "Result files:"
find "$RESULTS_DIR" -maxdepth 2 -type f | sort
