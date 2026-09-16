#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
APP_ROOT = BACKEND / "app"
sys.path.insert(0, str(BACKEND))

from app.architecture.module_boundaries import architecture_violations  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when audited modular-monolith boundaries are violated."
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output.")
    args = parser.parse_args(argv)

    violations = architecture_violations(APP_ROOT)
    result = {
        "schemaVersion": "1.0",
        "ok": not violations,
        "violationCount": len(violations),
        "violations": violations,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif violations:
        print("Architecture boundary validation failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
    else:
        print("Architecture boundary validation passed.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
