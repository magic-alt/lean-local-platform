#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_PATH="${1:-${ROOT_DIR}/web/runtime/backups/lean_market-$(date -u +%Y%m%dT%H%M%SZ).sql}"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"
MYSQL_DATABASE="${LEAN_MYSQL_DATABASE:-lean_market}"
MYSQL_USER="${LEAN_MYSQL_USER:-lean}"
MYSQL_PASSWORD="${LEAN_MYSQL_PASSWORD:-lean}"

mkdir -p "$(dirname "${OUTPUT_PATH}")"
TEMP_PATH="${OUTPUT_PATH}.partial"
trap 'rm -f "${TEMP_PATH}"' EXIT

docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
  exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" mysql \
  mysqldump --user="${MYSQL_USER}" --single-transaction --quick --routines --triggers \
  --no-tablespaces --set-gtid-purged=OFF "${MYSQL_DATABASE}" >"${TEMP_PATH}"

test -s "${TEMP_PATH}"
mv "${TEMP_PATH}" "${OUTPUT_PATH}"
shasum -a 256 "${OUTPUT_PATH}" >"${OUTPUT_PATH}.sha256"
chmod 600 "${OUTPUT_PATH}" "${OUTPUT_PATH}.sha256"
printf 'backup=%s\nchecksum=%s\n' "${OUTPUT_PATH}" "${OUTPUT_PATH}.sha256"
