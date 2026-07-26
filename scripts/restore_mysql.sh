#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"
MYSQL_SERVICE="${LEAN_MYSQL_SERVICE:-mysql}"
MYSQL_USER="${LEAN_MYSQL_USER:-root}"
MYSQL_PASSWORD="${LEAN_MYSQL_ROOT_PASSWORD:-}"
BACKUP_PATH=""
TARGET_DATABASE=""
CONFIRM=""
SOURCE_DATABASE="${LEAN_MYSQL_DATABASE:-lean_market}"
VERIFY_TABLES=("schema_migrations" "paper_accounts" "paper_ledger_entries" "stored_objects")

usage() {
  cat <<'EOF'
Usage:
  scripts/restore_mysql.sh --backup FILE --target-database lean_restore_NAME \
    --confirm RESTORE_ISOLATED_DATABASE

The target must begin with "lean_restore_". The script refuses to restore over
lean_market. It verifies FILE.sha256, then compares exact row counts and MySQL
table checksums for critical source/target tables.
EOF
}

while (($#)); do
  case "$1" in
    --backup)
      BACKUP_PATH="${2:-}"
      shift 2
      ;;
    --target-database)
      TARGET_DATABASE="${2:-}"
      shift 2
      ;;
    --confirm)
      CONFIRM="${2:-}"
      shift 2
      ;;
    --source-database)
      SOURCE_DATABASE="${2:-}"
      shift 2
      ;;
    --verify-table)
      if [[ "${VERIFY_TABLES[*]}" == "schema_migrations paper_accounts paper_ledger_entries stored_objects" ]]; then
        VERIFY_TABLES=()
      fi
      VERIFY_TABLES+=("${2:-}")
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${BACKUP_PATH}" || ! -f "${BACKUP_PATH}" ]]; then
  echo "A readable --backup file is required." >&2
  exit 2
fi
if [[ -z "${MYSQL_PASSWORD}" ]]; then
  echo "LEAN_MYSQL_ROOT_PASSWORD must be supplied through the environment." >&2
  exit 2
fi
if [[ "${TARGET_DATABASE}" != lean_restore_* || "${TARGET_DATABASE}" == "lean_market" ]]; then
  echo "--target-database must start with lean_restore_ and may not be lean_market." >&2
  exit 2
fi
if [[ ! "${TARGET_DATABASE}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unsafe target database name." >&2
  exit 2
fi
if [[ ! "${SOURCE_DATABASE}" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "Unsafe source database name." >&2
  exit 2
fi
if [[ "${CONFIRM}" != "RESTORE_ISOLATED_DATABASE" ]]; then
  echo "Explicit --confirm RESTORE_ISOLATED_DATABASE is required." >&2
  exit 2
fi
if [[ ! -f "${BACKUP_PATH}.sha256" ]]; then
  echo "Missing checksum file: ${BACKUP_PATH}.sha256" >&2
  exit 2
fi

(cd "$(dirname "${BACKUP_PATH}")" && shasum -a 256 -c "$(basename "${BACKUP_PATH}").sha256")

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
  exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
  mysql --user="${MYSQL_USER}" -e \
  "CREATE DATABASE \`${TARGET_DATABASE}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"

docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
  exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
  mysql --user="${MYSQL_USER}" "${TARGET_DATABASE}" <"${BACKUP_PATH}"

table_count="$(
  docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
    exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
    mysql --user="${MYSQL_USER}" -Nse \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${TARGET_DATABASE}'"
)"
verification_count=0
verification_failures=0
verification_output=""
for table_name in "${VERIFY_TABLES[@]}"; do
  if [[ ! "${table_name}" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "Unsafe verification table name: ${table_name}" >&2
    exit 2
  fi
  source_exists="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse \
      "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${SOURCE_DATABASE}' AND table_name='${table_name}'"
  )"
  target_exists="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse \
      "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='${TARGET_DATABASE}' AND table_name='${table_name}'"
  )"
  if [[ "${source_exists}" != "1" || "${target_exists}" != "1" ]]; then
    verification_output+="${table_name}:missing_source_or_target"$'\n'
    verification_failures=$((verification_failures + 1))
    continue
  fi
  source_rows="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse "SELECT COUNT(*) FROM \`${SOURCE_DATABASE}\`.\`${table_name}\`"
  )"
  target_rows="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse "SELECT COUNT(*) FROM \`${TARGET_DATABASE}\`.\`${table_name}\`"
  )"
  source_checksum="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse "CHECKSUM TABLE \`${SOURCE_DATABASE}\`.\`${table_name}\`" | awk '{print $2}'
  )"
  target_checksum="$(
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" \
      exec -T -e "MYSQL_PWD=${MYSQL_PASSWORD}" "${MYSQL_SERVICE}" \
      mysql --user="${MYSQL_USER}" -Nse "CHECKSUM TABLE \`${TARGET_DATABASE}\`.\`${table_name}\`" | awk '{print $2}'
  )"
  passed="true"
  if [[ "${source_rows}" != "${target_rows}" || -z "${source_checksum}" || "${source_checksum}" != "${target_checksum}" ]]; then
    passed="false"
    verification_failures=$((verification_failures + 1))
  fi
  verification_count=$((verification_count + 1))
  verification_output+="${table_name}:rows=${source_rows}/${target_rows}:checksum=${source_checksum}/${target_checksum}:passed=${passed}"$'\n'
done
completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'status=%s\nstarted_at=%s\ncompleted_at=%s\ntarget_database=%s\ntable_count=%s\nverification_count=%s\nverification_failures=%s\n%s' \
  "$([[ "${verification_failures}" == "0" ]] && printf restored_verified || printf verification_failed)" \
  "${started_at}" "${completed_at}" "${TARGET_DATABASE}" "${table_count}" \
  "${verification_count}" "${verification_failures}" "${verification_output}"
if [[ "${verification_failures}" != "0" ]]; then
  exit 1
fi
