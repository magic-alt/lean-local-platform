#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_API="${LEAN_WEB_BASE_URL:-http://127.0.0.1:8000}"
DRY_RUN=0
FORCE=0
CONFIRM_REQUIRED=1

usage() {
  cat <<'EOF'
Usage: clear_local_history.sh [--dry-run] [--force] [--api URL]

Options:
  --dry-run        Only preview what will be removed.
  --force          Skip interactive confirmation.
  --api URL        Override backend base URL (default: http://127.0.0.1:8000)
  --help           Show this help.
EOF
}

while (($# > 0)); do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --force)
      FORCE=1
      CONFIRM_REQUIRED=0
      shift
      ;;
    --api)
      if (($# < 2)); then
        echo "--api requires a URL" >&2
        exit 1
      fi
      BACKEND_API="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to call local maintenance API." >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 0 && "$FORCE" -eq 0 && "$CONFIRM_REQUIRED" -eq 1 ]]; then
  echo "This will clear local history records and runtime cache (excluding market data tables)."
  read -r -p "Continue? [y/N] " confirm
  case "$confirm" in
    y|Y|yes|YES)
      ;;
    *)
      echo "Canceled by user"
      exit 0
      ;;
  esac
fi

payload=$(cat <<JSON
{\"dryRun\": ${DRY_RUN}, \"force\": ${FORCE}}
JSON
)

temp_file="$(mktemp)"
http_code=$(curl -sS -X POST "${BACKEND_API}/api/maintenance/clear-history" \
  -H 'Content-Type: application/json' \
  -d "${payload}" \
  -w "%{http_code}" \
  -o "${temp_file}")

if [[ "$http_code" != "200" ]]; then
  echo "Clear request failed (HTTP ${http_code})." >&2
  cat "${temp_file}" >&2
  rm -f "${temp_file}"
  exit 1
fi

echo "Backend response:"
if command -v python3 >/dev/null 2>&1; then
  python3 -m json.tool "${temp_file}"
else
  cat "${temp_file}"
fi
rm -f "${temp_file}"
