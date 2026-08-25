#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a file-level CycloneDX SBOM for a native LEAN runtime.")
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--lean-commit", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    root = Path(args.runtime_root).resolve()
    if not root.is_dir():
        raise SystemExit("runtime root does not exist")

    components = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        components.append(
            {
                "type": "file",
                "name": relative,
                "bom-ref": f"file:{relative}",
                "hashes": [{"alg": "SHA-256", "content": sha256(path)}],
            }
        )

    payload = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.sha256((args.runtime_id + args.artifact_sha256).encode()).hexdigest()[:32]}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "QuantConnect LEAN native runtime",
                "version": args.runtime_id,
                "properties": [
                    {"name": "lean.commit", "value": args.lean_commit},
                ],
            },
            "properties": [
                {"name": "lean.runtime.id", "value": args.runtime_id},
                {"name": "lean.runtime.sha256", "value": args.artifact_sha256.lower()},
                {"name": "lean.commit", "value": args.lean_commit.lower()},
            ],
        },
        "components": components,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())