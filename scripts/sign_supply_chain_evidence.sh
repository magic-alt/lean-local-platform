#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE_DIR="${1:-${ROOT_DIR}/web/runtime/audit/sbom}"
PRIVATE_KEY="${LEAN_RELEASE_SIGNING_PRIVATE_KEY:-${ROOT_DIR}/web/runtime/secrets/release-signing-private.pem}"
PUBLIC_KEY="${ROOT_DIR}/config/release-signing-public.pem"
MANIFEST="${EVIDENCE_DIR}/release-manifest.txt"
SIGNATURE="${EVIDENCE_DIR}/release-manifest.sig"

if [[ ! -f "${PRIVATE_KEY}" ]]; then
  echo "Missing release signing private key: ${PRIVATE_KEY}" >&2
  exit 2
fi
if [[ ! -f "${PUBLIC_KEY}" ]]; then
  echo "Missing trusted release signing public key: ${PUBLIC_KEY}" >&2
  exit 2
fi

{
  shasum -a 256 "${ROOT_DIR}/web/backend/requirements.lock"
  shasum -a 256 "${ROOT_DIR}/web/backend/Dockerfile"
  shasum -a 256 "${ROOT_DIR}/docker-compose.yml"
  shasum -a 256 "${ROOT_DIR}/config/supply-chain-vulnerability-policy.json"
  shasum -a 256 "${EVIDENCE_DIR}/manifest.tsv"
  shasum -a 256 "${EVIDENCE_DIR}"/*.cyclonedx.json
  shasum -a 256 "${EVIDENCE_DIR}"/*.critical.sarif.json
} | LC_ALL=C sort >"${MANIFEST}"

openssl pkeyutl -sign -rawin -inkey "${PRIVATE_KEY}" -in "${MANIFEST}" -out "${SIGNATURE}"
openssl pkeyutl -verify -rawin -pubin -inkey "${PUBLIC_KEY}" \
  -in "${MANIFEST}" -sigfile "${SIGNATURE}" >/dev/null
chmod 600 "${MANIFEST}" "${SIGNATURE}"
printf 'signed_manifest=%s\nsignature=%s\n' "${MANIFEST}" "${SIGNATURE}"
