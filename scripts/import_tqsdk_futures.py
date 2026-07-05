#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import init_db
from app.services.futures import import_tqsdk_klines


def main() -> int:
    parser = argparse.ArgumentParser(description="Import futures K-lines through the optional TqSdk adapter.")
    parser.add_argument("--symbols", required=True, help="Comma-separated TqSdk symbols, e.g. DCE.m2409,KQ.m@SHFE.rb.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--duration-seconds", type=int, default=86400)
    parser.add_argument("--tq-account", default=os.environ.get("TQSDK_ACCOUNT"))
    parser.add_argument("--tq-password", default=os.environ.get("TQSDK_PASSWORD"))
    args = parser.parse_args()

    init_db()
    result = import_tqsdk_klines(
        symbols=[item.strip() for item in args.symbols.split(",") if item.strip()],
        start_date=args.start_date,
        end_date=args.end_date,
        duration_seconds=args.duration_seconds,
        tq_account=args.tq_account,
        tq_password=args.tq_password,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
