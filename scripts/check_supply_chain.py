#!/usr/bin/env python3
"""Fail closed on mutable runtime dependencies and emit an auditable report."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILES = (ROOT / "web" / "backend" / "Dockerfile",)
REQUIREMENTS = ROOT / "web" / "backend" / "requirements.txt"
PACKAGE_LOCK = ROOT / "web" / "frontend" / "package-lock.json"

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

    payload = {
        "schemaVersion": 1,
        "status": "passed" if not failures else "failed",
        "checks": checks,
        "failures": failures,
        "remainingReleaseGates": [
            "python_transitive_hash_lock",
            "sbom_vulnerability_policy",
            "publisher_or_release_signature_verification",
        ],
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
