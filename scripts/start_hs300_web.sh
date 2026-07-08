#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export LEAN_DATABASE_URL="${LEAN_DATABASE_URL:-mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market}"
export LEAN_WEB_HOST="${LEAN_WEB_HOST:-127.0.0.1}"
export LEAN_WEB_PORT="${LEAN_WEB_PORT:-8000}"

cd "${ROOT_DIR}/web/backend"
exec .venv/bin/python -m uvicorn app.main:app --host "${LEAN_WEB_HOST}" --port "${LEAN_WEB_PORT}"
