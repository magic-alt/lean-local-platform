#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "web" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.etf_rotation_execution_certification import (  # noqa: E402
    SCHEMA_VERSION,
    build_execution_certification,
)


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build fail-closed ETF real-execution certification evidence for Issue #67. "
            "This command audits existing evidence; it never submits live orders."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = _load(args.input)
    report = build_execution_certification(
        data_release_id=str(payload.get("dataReleaseId") or ""),
        candidate=payload.get("candidate") or {},
        baseline=payload.get("baseline") or {},
        walk_forward=payload.get("walkForward") or {},
        paper=payload.get("paper") or {},
        admission=payload.get("admission") or {},
        resources=payload.get("resources") or {},
        gates=payload.get("gates") or {},
        deterministic_fingerprints=payload.get("deterministicFingerprints") or [],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "certified": report["certified"],
                "failureReasons": report["failureReasons"],
                "artifactFingerprint": report["artifactFingerprint"],
                "output": str(args.output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["certified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
