#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a reviewable native runtime lock after immutable artifacts are published.")
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--lean-commit", required=True)
    parser.add_argument("--platform", default="windows-x64")
    parser.add_argument("--artifact-url", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--signature-url", required=True)
    parser.add_argument("--sbom-url", required=True)
    parser.add_argument("--launcher", default="Launcher/bin/Release/QuantConnect.Lean.Launcher.dll")
    parser.add_argument("--python-home", default="python")
    parser.add_argument("--python-library", default="python/python311.dll")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if len(args.lean_commit) != 40 or any(ch not in "0123456789abcdef" for ch in args.lean_commit.lower()):
        raise SystemExit("lean commit must be a 40-character hexadecimal SHA")
    if len(args.artifact_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in args.artifact_sha256.lower()):
        raise SystemExit("artifact sha256 must be a 64-character hexadecimal digest")
    for url in (args.artifact_url, args.signature_url, args.sbom_url):
        if not url.startswith("https://"):
            raise SystemExit("runtime artifact URLs must use HTTPS")

    payload = {
        "schemaVersion": 1,
        "supported": True,
        "runtimeId": args.runtime_id,
        "leanCommit": args.lean_commit.lower(),
        "dotnetRuntime": "10.0",
        "pythonRuntime": "3.11.11",
        "launcher": args.launcher,
        "pythonHome": args.python_home,
        "artifacts": {
            args.platform: {
                "url": args.artifact_url,
                "sha256": args.artifact_sha256.lower(),
                "signatureUrl": args.signature_url,
                "sbomUrl": args.sbom_url,
                "launcher": args.launcher,
                "pythonHome": args.python_home,
                "pythonLibrary": args.python_library,
            }
        },
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())