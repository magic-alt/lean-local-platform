#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import init_db  # noqa: E402
from app.services.instrument_identity import identifier_coverage, identifier_conflicts, upsert_instrument_identifiers  # noqa: E402


def _symbols(value: str | None) -> list[str] | None:
    items = [item.strip() for item in (value or "").split(",") if item.strip()]
    return items or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill canonical instrument identifier mappings.")
    parser.add_argument("--all", action="store_true", help="Scan all A-share instruments from local database tables.")
    parser.add_argument("--symbols", help="Optional comma-separated symbols. Defaults to all canonical A-share symbols.")
    parser.add_argument("--source", default="jqdata")
    parser.add_argument("--batch-id")
    parser.add_argument("--min-coverage-ratio", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    symbols = _symbols(args.symbols)
    if args.all:
        symbols = None
    result = upsert_instrument_identifiers(
        symbols=symbols,
        source=args.source,
        batch_id=args.batch_id,
        dry_run=args.dry_run,
    )
    coverage = identifier_coverage(symbols)
    conflicts = identifier_conflicts()
    meets_threshold = float(coverage["coverageRatio"]) >= float(args.min_coverage_ratio)
    payload = {
        **result,
        "coverage": coverage,
        "conflicts": conflicts,
        "minCoverageRatio": args.min_coverage_ratio,
        "meetsCoverageThreshold": meets_threshold,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(
            f"status={payload['status']} symbols={payload['symbols']} identifiers={payload['identifiers']} "
            f"coverage={coverage['covered']}/{coverage['total']} dryRun={args.dry_run}"
        )
    return 0 if meets_threshold and conflicts["count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
