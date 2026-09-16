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

from app.services.etf_rotation_certification import (  # noqa: E402
    SCHEMA_VERSION,
    build_certification_report,
    run_regression_matrix,
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"unable to read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the machine-readable ETF rotation certification report used by "
            "Issue #67 acceptance work."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        help=(
            "Certification input JSON containing candidate, baseline, gates, and "
            "deterministicFingerprints."
        ),
    )
    parser.add_argument(
        "--regression-fixture",
        type=Path,
        help="Optional deterministic reference/regression fixture JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination for the certification JSON report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.input is None and args.regression_fixture is None:
        raise SystemExit("at least one of --input or --regression-fixture is required")

    output: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION}
    exit_code = 0

    if args.regression_fixture is not None:
        fixture = _load_json(args.regression_fixture)
        output["regressionMatrix"] = run_regression_matrix(fixture)

    if args.input is not None:
        payload = _load_json(args.input)
        report = build_certification_report(
            candidate=payload.get("candidate") or {},
            baseline=payload.get("baseline") or {},
            gates=payload.get("gates") or {},
            deterministic_fingerprints=payload.get("deterministicFingerprints") or [],
        )
        output["certification"] = report
        if not report["passed"]:
            exit_code = 2

    _write_json(args.output, output)
    print(
        json.dumps(
            {
                "schemaVersion": SCHEMA_VERSION,
                "output": str(args.output),
                "passed": output.get("certification", {}).get("passed"),
                "regressionFingerprint": output.get("regressionMatrix", {}).get(
                    "fingerprint"
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
