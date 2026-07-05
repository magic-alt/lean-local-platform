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
from app.services.ashare_multisource import compare_ashare_daily_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare stored A-share daily bars across multiple local sources.")
    parser.add_argument("symbol", help="A-share symbol, e.g. 600519.")
    parser.add_argument("--sources", default="akshare,adata,baostock", help="Comma-separated stored source names.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--adjust", default="raw")
    parser.add_argument("--price-abs-tolerance", type=float, default=0.02)
    parser.add_argument("--price-rel-tolerance-bps", type=float, default=5.0)
    parser.add_argument("--volume-rel-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    init_db()
    result = compare_ashare_daily_sources(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        sources=[item.strip() for item in args.sources.split(",") if item.strip()],
        adjust=args.adjust,
        price_abs_tolerance=args.price_abs_tolerance,
        price_rel_tolerance_bps=args.price_rel_tolerance_bps,
        volume_rel_tolerance_pct=args.volume_rel_tolerance_pct,
        persist=not args.no_persist,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
