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
from app.services.benchmark import import_csi300_benchmark_from_akshare


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CSI300 benchmark daily bars and LEAN cache from AKShare.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    args = parser.parse_args()
    init_db()
    result = import_csi300_benchmark_from_akshare(start_date=args.start_date, end_date=args.end_date)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
