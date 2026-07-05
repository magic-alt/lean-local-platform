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
from app.services.free_data_pipeline import import_ashare_daily_sample


def main() -> int:
    parser = argparse.ArgumentParser(description="Import an A-share daily sample from free public providers.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. 600519,000001.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--providers", default="akshare,baostock,adata")
    parser.add_argument("--adjust", default="raw")
    parser.add_argument("--primary-provider", default="akshare")
    parser.add_argument("--no-parquet", action="store_true")
    parser.add_argument("--no-compare", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    args = parser.parse_args()

    init_db()
    result = import_ashare_daily_sample(
        symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
        start_date=args.start_date,
        end_date=args.end_date,
        providers=[item.strip() for item in args.providers.split(",") if item.strip()],
        adjust=args.adjust,
        primary_provider=args.primary_provider,
        export_parquet=not args.no_parquet,
        compare_sources=not args.no_compare,
        continue_on_error=not args.fail_fast,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["errorCount"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
