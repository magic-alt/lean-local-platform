from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR, RUNTIME_DIR


POLICY_PATH = PLATFORM_DIR / "config" / "runtime" / "windows-celery-certification.json"
DEFAULT_CERTIFICATE_PATH = RUNTIME_DIR / "certification" / "windows-celery.json"
BOUND_FILES = (
    PLATFORM_DIR / "web" / "backend" / "requirements.lock",
    PLATFORM_DIR / "config" / "runtime" / "lean-native.lock.json",
    POLICY_PATH,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"windows_certification_document_invalid:{path.name}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"windows_certification_document_invalid:{path.name}")
    return value


def issue_windows_certificate(
    evidence_path: Path,
    certificate_path: Path = DEFAULT_CERTIFICATE_PATH,
) -> dict[str, Any]:
    policy = _read_json(POLICY_PATH)
    evidence = _read_json(evidence_path)
    errors = _evidence_errors(evidence, policy)
    if errors:
        raise RuntimeError("windows_certification_evidence_failed:" + ",".join(errors))
    now = datetime.now(timezone.utc)
    certificate = {
        "schemaVersion": 1,
        "status": "WINDOWS_CELERY_CERTIFIED",
        "issuedAt": now.isoformat(),
        "machine": os.environ.get("COMPUTERNAME", "").strip().lower(),
        "versions": evidence["versions"],
        "soakSeconds": int(evidence["soakSeconds"]),
        "scenarios": evidence["scenarios"],
        "evidenceSha256": _sha256(evidence_path),
        "bindings": {str(path.relative_to(PLATFORM_DIR)): _sha256(path) for path in BOUND_FILES},
    }
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = certificate_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(certificate, indent=2) + "\n", encoding="utf-8")
    temporary.replace(certificate_path)
    return certificate


def _evidence_errors(evidence: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if evidence.get("schemaVersion") != 1 or evidence.get("passed") is not True:
        errors.append("evidence_not_passed")
    if int(evidence.get("soakSeconds") or 0) < int(policy["minimumSoakSeconds"]):
        errors.append("soak_too_short")
    versions = evidence.get("versions") or {}
    for name, prefix in policy["requiredVersionPrefixes"].items():
        if not str(versions.get(name) or "").startswith(str(prefix)):
            errors.append(f"version_{name}")
    scenarios = evidence.get("scenarios") or {}
    for scenario in policy["requiredScenarios"]:
        if scenarios.get(scenario) is not True:
            errors.append(f"scenario_{scenario}")
    return errors


def verify_windows_certificate(
    certificate_path: Path = DEFAULT_CERTIFICATE_PATH,
) -> dict[str, Any]:
    try:
        policy = _read_json(POLICY_PATH)
        certificate = _read_json(certificate_path)
        errors = _evidence_errors(
            {
                "schemaVersion": certificate.get("schemaVersion"),
                "passed": certificate.get("status") == "WINDOWS_CELERY_CERTIFIED",
                "versions": certificate.get("versions"),
                "soakSeconds": certificate.get("soakSeconds"),
                "scenarios": certificate.get("scenarios"),
            },
            policy,
        )
        issued_at = datetime.fromisoformat(str(certificate.get("issuedAt") or "").replace("Z", "+00:00"))
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - issued_at.astimezone(timezone.utc)).total_seconds() / 86400
        if age_days < 0 or age_days > int(policy["maximumCertificateAgeDays"]):
            errors.append("certificate_expired")
        current_machine = os.environ.get("COMPUTERNAME", "").strip().lower()
        if current_machine and certificate.get("machine") != current_machine:
            errors.append("machine_binding_mismatch")
        bindings = certificate.get("bindings") or {}
        for path in BOUND_FILES:
            key = str(path.relative_to(PLATFORM_DIR))
            if not path.is_file() or bindings.get(key) != _sha256(path):
                errors.append(f"binding_{path.name}")
        return {
            "ready": not errors,
            "status": "WINDOWS_CELERY_CERTIFIED" if not errors else "WINDOWS_CELERY_UNCERTIFIED",
            "errors": sorted(set(errors)),
            "certificate": str(certificate_path),
        }
    except (RuntimeError, ValueError, TypeError, KeyError) as exc:
        return {
            "ready": False,
            "status": "WINDOWS_CELERY_UNCERTIFIED",
            "errors": [str(exc)],
            "certificate": str(certificate_path),
        }
