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

from app.db import init_db
from app.services.parquet_lake import rebuild_all_market_parquet


def _sources(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild all matching market_daily_bars Parquet datasets and emit a consistency report.")
    parser.add_argument("--asset-class")
    parser.add_argument("--market")
    parser.add_argument("--venue")
    parser.add_argument("--resolution")
    parser.add_argument("--data-type")
    parser.add_argument("--adjust")
    parser.add_argument("--sources", help="Comma-separated source names. Omit to rebuild every stored source.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--no-persist-report", action="store_true")
    args = parser.parse_args()

    init_db()
    result = rebuild_all_market_parquet(
        asset_class=args.asset_class,
        market=args.market,
        venue=args.venue,
        resolution=args.resolution,
        data_type=args.data_type,
        adjust=args.adjust,
        sources=_sources(args.sources),
        start_date=args.start_date,
        end_date=args.end_date,
        continue_on_error=not args.fail_fast,
        persist_report=not args.no_persist_report,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["consistencyReport"]["severity"] == "critical" or result["errorCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
