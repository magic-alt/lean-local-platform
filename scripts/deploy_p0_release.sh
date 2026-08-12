#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

SOURCE_MANIFEST="$(mktemp)"
trap 'rm -f "${SOURCE_MANIFEST}"' EXIT
git ls-files -co --exclude-standard -- \
  docker-compose.yml web/backend web/frontend scripts \
  | LC_ALL=C sort \
  | while IFS= read -r path; do
      if [[ -f "${path}" ]]; then
        shasum -a 256 "${path}"
      fi
    done >"${SOURCE_MANIFEST}"

export LEAN_RELEASE_SHA="${LEAN_RELEASE_SHA:-$(git rev-parse HEAD)}"
SOURCE_SHA="$(shasum -a 256 "${SOURCE_MANIFEST}" | awk '{print $1}')"
export LEAN_RELEASE_ID="${LEAN_RELEASE_ID:-${LEAN_RELEASE_SHA}-${SOURCE_SHA:0:16}}"

echo "Applying migrations for release ${LEAN_RELEASE_ID}"
docker compose run --rm --no-deps api \
  python -c "from app.db import init_db; init_db()"

echo "Rolling API"
docker compose up -d --no-deps --force-recreate api

echo "Rolling workers"
for service in worker data-worker data-lineage-worker data-demand-worker backtest-worker ml-worker; do
  docker compose up -d --no-deps --force-recreate "${service}"
done

echo "Rolling LEAN runner and Beat"
docker compose up -d --no-deps --force-recreate lean-runner
docker compose up -d --no-deps --force-recreate beat

echo "Verifying release convergence"
web/backend/.venv/bin/python scripts/verify_release_convergence.py
