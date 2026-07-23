#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${1:-${ROOT_DIR}/web/runtime/audit/sbom}"
COMPOSE_PROJECT_NAME="${LEAN_COMPOSE_PROJECT_NAME:-lean-platform}"

if ! docker sbom --help >/dev/null 2>&1; then
  echo "docker sbom is unavailable; install/enable Docker Scout before this release gate." >&2
  exit 2
fi

mkdir -p "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}"

mapfile_compat() {
  while IFS= read -r line; do
    [[ -n "${line}" ]] && printf '%s\n' "${line}"
  done
  return 0
}

images="$(
  {
    docker compose --project-directory "${ROOT_DIR}" -p "${COMPOSE_PROJECT_NAME}" images --format json 2>/dev/null \
      | "${ROOT_DIR}/web/backend/.venv/bin/python" -c \
        'import json,sys
payload=json.load(sys.stdin)
items=payload if isinstance(payload, list) else [payload]
for item in items:
    image=item.get("ID") or item.get("Repository")
    if image:
        print(image)'
    printf '%s\n' "${LEAN_DOCKER_IMAGE:-}"
    printf '%s\n' "${LEAN_RESEARCH_IMAGE:-}"
  } | mapfile_compat | sort -u
)"

if [[ -z "${images}" ]]; then
  echo "No local runtime image was found. Start/build the stack before generating SBOM evidence." >&2
  exit 2
fi

manifest="${OUTPUT_DIR}/manifest.tsv"
warnings="${OUTPUT_DIR}/scanner-warnings.log"
: >"${manifest}"
: >"${warnings}"
while IFS= read -r image; do
  [[ -z "${image}" ]] && continue
  safe_name="$(printf '%s' "${image}" | tr '/:@' '____' | tr -cd 'A-Za-z0-9_.-')"
  output="${OUTPUT_DIR}/${safe_name}.cyclonedx.json"
  docker sbom --format cyclonedx-json "${image}" >"${output}" 2>>"${warnings}"
  test -s "${output}"
  digest="$(shasum -a 256 "${output}" | awk '{print $1}')"
  printf '%s\t%s\t%s\n' "${image}" "$(basename "${output}")" "${digest}" >>"${manifest}"
done <<<"${images}"

shasum -a 256 "${OUTPUT_DIR}"/*.cyclonedx.json "${manifest}" "${warnings}" >"${OUTPUT_DIR}/sha256sums.txt"
printf 'sbom_dir=%s\nmanifest=%s\n' "${OUTPUT_DIR}" "${manifest}"
