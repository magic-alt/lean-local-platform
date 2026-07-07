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
from app.services.provider_certification import provider_availability_report  # noqa: E402


def _csv(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check A-share provider adapter availability and certification state.")
    parser.add_argument("--providers", default="jqdata,akshare,tushare,rqdata,baostock,adata")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    payload = provider_availability_report(_csv(args.providers), start_date=args.start_date, end_date=args.end_date, persist=args.persist)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"severity={payload['severity']} providers={payload['count']}")
    return 2 if payload["severity"] == "critical" else 0


if __name__ == "__main__":
    raise SystemExit(main())
