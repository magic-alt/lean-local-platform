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
from app.services.parquet_lake import export_market_daily_bars


def main() -> int:
    parser = argparse.ArgumentParser(description="Export normalized market_daily_bars to partitioned Parquet.")
    parser.add_argument("--asset-class", default="equity")
    parser.add_argument("--market", default="china")
    parser.add_argument("--venue", default="china")
    parser.add_argument("--resolution", default="daily")
    parser.add_argument("--data-type", default="trade")
    parser.add_argument("--adjust", default="raw")
    parser.add_argument("--source", default="jqdata", help="Provider/source already stored in market_daily_bars.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()

    init_db()
    result = export_market_daily_bars(
        asset_class=args.asset_class,
        market=args.market,
        venue=args.venue,
        resolution=args.resolution,
        data_type=args.data_type,
        adjust=args.adjust,
        source=args.source,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
