#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TRACKED_PREFIXES = ("results/", "runs/", "Data/", "parquet/", "var/", "web/runtime/")
PORTABLE_MANIFEST_DIR = ROOT / "config" / "data-sources"


def tracked_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [value.decode("utf-8") for value in completed.stdout.split(b"\0") if value]


def absolute_strings(value: Any, path: str = "$") -> list[str]:
    if isinstance(value, dict):
        found: list[str] = []
        for key, item in value.items():
            found.extend(absolute_strings(item, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, item in enumerate(value):
            found.extend(absolute_strings(item, f"{path}[{index}]"))
        return found
    if isinstance(value, str) and (value.startswith("/") or value.startswith("~")):
        return [f"{path}={value}"]
    return []


def hygiene_errors(files: list[str] | None = None) -> list[str]:
    tracked = files if files is not None else tracked_files()
    errors = [
        f"generated path is tracked: {path}"
        for path in tracked
        if path.startswith(FORBIDDEN_TRACKED_PREFIXES)
    ]
    if PORTABLE_MANIFEST_DIR.is_dir():
        for manifest in sorted(PORTABLE_MANIFEST_DIR.glob("*.json")):
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            errors.extend(f"non-portable manifest value in {manifest.relative_to(ROOT)}: {item}" for item in absolute_strings(payload))
    return errors


def main() -> int:
    errors = hygiene_errors()
    if not errors:
        print("repository hygiene: ok")
        return 0
    for error in errors:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
