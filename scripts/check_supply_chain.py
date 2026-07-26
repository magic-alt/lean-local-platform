#!/usr/bin/env python3
"""Fail closed on mutable runtime dependencies and emit an auditable report."""

from __future__ import annotations

import argparse
from datetime import date
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILES = (ROOT / "web" / "backend" / "Dockerfile",)
REQUIREMENTS = ROOT / "web" / "backend" / "requirements.txt"
REQUIREMENTS_LOCK = ROOT / "web" / "backend" / "requirements.lock"
PACKAGE_LOCK = ROOT / "web" / "frontend" / "package-lock.json"
SBOM_DIR = ROOT / "web" / "runtime" / "audit" / "sbom"
VULNERABILITY_POLICY = ROOT / "config" / "supply-chain-vulnerability-policy.json"
RELEASE_PUBLIC_KEY = ROOT / "config" / "release-signing-public.pem"

IMAGE_RE = re.compile(r"^\s*image:\s*([^\s#]+)", re.MULTILINE)
FROM_RE = re.compile(r"^\s*FROM\s+([^\s]+)", re.MULTILINE | re.IGNORECASE)
EXACT_REQUIREMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^;\s]+(?:\s*;.*)?$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional JSON evidence path.")
    args = parser.parse_args()

    failures: list[dict[str, str]] = []
    checks: list[dict[str, object]] = []

    compose_text = COMPOSE.read_text(encoding="utf-8")
    images = IMAGE_RE.findall(compose_text)
    mutable_images = [image for image in images if "@sha256:" not in image]
    checks.append(
        {
            "name": "compose_images_digest_pinned",
            "status": "passed" if images and not mutable_images else "failed",
            "count": len(images),
            "mutable": mutable_images,
        }
    )
    for image in mutable_images:
        failures.append({"check": "compose_images_digest_pinned", "value": image})

    for dockerfile in DOCKERFILES:
        base_images = FROM_RE.findall(dockerfile.read_text(encoding="utf-8"))
        mutable = [image for image in base_images if "@sha256:" not in image]
        status = "passed" if base_images and not mutable else "failed"
        checks.append(
            {
                "name": "dockerfile_base_digest_pinned",
                "path": str(dockerfile.relative_to(ROOT)),
                "status": status,
                "images": base_images,
                "mutable": mutable,
            }
        )
        for image in mutable:
            failures.append({"check": "dockerfile_base_digest_pinned", "value": image})

    requirement_lines = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    unpinned_requirements = [
        line for line in requirement_lines if not line.startswith(("-", "git+")) and not EXACT_REQUIREMENT_RE.match(line)
    ]
    checks.append(
        {
            "name": "python_direct_dependencies_exact",
            "status": "passed" if requirement_lines and not unpinned_requirements else "failed",
            "count": len(requirement_lines),
            "unpinned": unpinned_requirements,
            "note": "Exact direct versions do not replace a hash-locked transitive dependency set.",
        }
    )
    for line in unpinned_requirements:
        failures.append({"check": "python_direct_dependencies_exact", "value": line})

    lock_text = REQUIREMENTS_LOCK.read_text(encoding="utf-8") if REQUIREMENTS_LOCK.exists() else ""
    locked_packages = re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\", lock_text, re.MULTILINE)
    hash_count = len(re.findall(r"--hash=sha256:[0-9a-f]{64}", lock_text))
    dockerfile_text = DOCKERFILES[0].read_text(encoding="utf-8")
    lock_ok = bool(
        locked_packages
        and hash_count >= len(locked_packages)
        and "requirements.lock" in dockerfile_text
        and "--require-hashes" in dockerfile_text
    )
    checks.append(
        {
            "name": "python_transitive_hash_lock",
            "status": "passed" if lock_ok else "failed",
            "packageCount": len(locked_packages),
            "hashCount": hash_count,
            "dockerInstallRequiresHashes": "--require-hashes" in dockerfile_text,
        }
    )
    if not lock_ok:
        failures.append({"check": "python_transitive_hash_lock", "value": str(REQUIREMENTS_LOCK)})

    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    checks.append(
        {
            "name": "npm_lockfile_present",
            "status": "passed" if lock.get("lockfileVersion", 0) >= 2 else "failed",
            "lockfileVersion": lock.get("lockfileVersion"),
            "packageCount": len(lock.get("packages") or {}),
        }
    )
    if lock.get("lockfileVersion", 0) < 2:
        failures.append({"check": "npm_lockfile_present", "value": str(lock.get("lockfileVersion"))})

    plugin_match = re.search(r"GF_INSTALL_PLUGINS:\s*([^\n#]+)", compose_text)
    plugin_value = plugin_match.group(1).strip() if plugin_match else ""
    plugin_pinned = bool(re.search(r"\s[0-9]+\.[0-9]+\.[0-9]+$", plugin_value))
    checks.append(
        {
            "name": "grafana_plugin_version_pinned",
            "status": "passed" if plugin_pinned else "failed",
            "value": plugin_value,
        }
    )
    if not plugin_pinned:
        failures.append({"check": "grafana_plugin_version_pinned", "value": plugin_value})

    policy = json.loads(VULNERABILITY_POLICY.read_text(encoding="utf-8"))
    sboms = sorted(SBOM_DIR.glob("*.cyclonedx.json"))
    reports = sorted(SBOM_DIR.glob("*.critical.sarif.json"))
    report_findings: dict[str, int] = {}
    unapproved_findings: dict[str, list[str]] = {}
    approved_exceptions = {
        str(item.get("id"))
        for item in policy.get("exceptions") or []
        if item.get("reason")
        and item.get("expiresAt")
        and date.fromisoformat(str(item["expiresAt"])) >= date.today()
    }
    reports_valid = bool(reports)
    for report in reports:
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
            results = [result for run in payload.get("runs") or [] for result in run.get("results") or []]
            findings = len(results)
            unapproved = sorted(
                {
                    str(result.get("ruleId") or "unknown")
                    for result in results
                    if str(result.get("ruleId") or "unknown") not in approved_exceptions
                }
            )
        except (OSError, ValueError, TypeError):
            reports_valid = False
            findings = -1
            unapproved = ["invalid_report"]
        report_findings[report.name] = findings
        unapproved_findings[report.name] = unapproved
        reports_valid = reports_valid and not unapproved
    sbom_policy_ok = bool(
        sboms
        and len(sboms) == len(reports)
        and reports_valid
        and policy.get("maximumFindings", {}).get("critical") == 0
    )
    checks.append(
        {
            "name": "sbom_vulnerability_policy",
            "status": "passed" if sbom_policy_ok else "failed",
            "sbomCount": len(sboms),
            "reportCount": len(reports),
            "criticalFindings": report_findings,
            "unapprovedCriticalFindings": unapproved_findings,
            "activeExceptions": sorted(approved_exceptions),
            "policy": str(VULNERABILITY_POLICY.relative_to(ROOT)),
        }
    )
    if not sbom_policy_ok:
        failures.append({"check": "sbom_vulnerability_policy", "value": str(SBOM_DIR)})

    signed_manifest = SBOM_DIR / "release-manifest.txt"
    signature = SBOM_DIR / "release-manifest.sig"
    signature_ok = False
    signature_error = None
    if signed_manifest.exists() and signature.exists() and RELEASE_PUBLIC_KEY.exists():
        verified = subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-verify",
                "-rawin",
                "-pubin",
                "-inkey",
                str(RELEASE_PUBLIC_KEY),
                "-in",
                str(signed_manifest),
                "-sigfile",
                str(signature),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        signature_ok = verified.returncode == 0
        signature_error = None if signature_ok else (verified.stderr.strip() or verified.stdout.strip())
    checks.append(
        {
            "name": "publisher_or_release_signature_verification",
            "status": "passed" if signature_ok else "failed",
            "publicKey": str(RELEASE_PUBLIC_KEY.relative_to(ROOT)),
            "manifest": str(signed_manifest),
            "error": signature_error,
        }
    )
    if not signature_ok:
        failures.append(
            {"check": "publisher_or_release_signature_verification", "value": str(signed_manifest)}
        )

    remaining = [
        name
        for name in (
            "python_transitive_hash_lock",
            "sbom_vulnerability_policy",
            "publisher_or_release_signature_verification",
        )
        if any(item["check"] == name for item in failures)
    ]
    payload = {
        "schemaVersion": 1,
        "status": "passed" if not failures else "failed",
        "checks": checks,
        "failures": failures,
        "remainingReleaseGates": remaining,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
