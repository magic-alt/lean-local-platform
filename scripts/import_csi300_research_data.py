#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.csi300_data_pipeline import run_csi300_research_import  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CSI300 TuShare Pro research data into local SQLite and LEAN files.")
    parser.add_argument("--mode", default="daily", choices=["daily", "incremental", "backfill"])
    parser.add_argument("--start", help="Start date, YYYY-MM-DD. Required for backfill unless startDate is configured.")
    parser.add_argument("--end", help="End date, YYYY-MM-DD. Defaults to today for daily/incremental.")
    parser.add_argument("--datasets", default="research-core", help="Comma-separated dataset names or research-core.")
    parser.add_argument("--limit", type=int, default=0, help="Limit imported CSI300 symbols for smoke tests.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between symbols.")
    parser.add_argument("--strict-market-data", action="store_true", help="Fail immediately on market data dataset degradation.")
    parser.add_argument("--strict-research", action="store_true", help="Fail on optional research dataset degradation.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and summarize without writing local data.")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite existing LEAN zip files.")
    args = parser.parse_args()

    if args.mode == "backfill" and (not args.start or not args.end):
        parser.error("--mode backfill requires --start and --end.")

    result = run_csi300_research_import(
        {
            "mode": args.mode,
            "start": args.start,
            "end": args.end,
            "datasets": args.datasets,
            "limit": args.limit,
            "sleep": args.sleep,
            "strict_market_data": args.strict_market_data,
            "strict_research": args.strict_research,
            "dry_run": args.dry_run,
            "overwrite": not args.no_overwrite,
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
