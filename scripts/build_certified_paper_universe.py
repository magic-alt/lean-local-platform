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
from app.services.universe_certification import build_certified_universe  # noqa: E402


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and persist a certified Level3+ A-share paper universe.")
    parser.add_argument("--universe-code", required=True)
    parser.add_argument("--source", default="jqdata")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--target-size", type=int, default=50)
    parser.add_argument("--min-size", type=int, default=20)
    parser.add_argument("--symbols", help="Optional comma-separated candidate symbols.")
    parser.add_argument("--allow-warning-codes", default="")
    parser.add_argument("--warning-expiry-days", type=int, default=30)
    parser.add_argument("--approved-by", default="level3plus-cli")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    try:
        payload = build_certified_universe(
            universe_code=args.universe_code,
            source=args.source,
            benchmark=args.benchmark,
            start_date=args.start_date,
            end_date=args.end_date,
            target_size=args.target_size,
            min_size=args.min_size,
            candidates=_csv(args.symbols) or None,
            allow_warning_codes=_csv(args.allow_warning_codes),
            warning_expiry_days=args.warning_expiry_days,
            approved_by=args.approved_by,
        )
    except Exception as exc:
        payload = {"status": "failed", "severity": "critical", "error": str(exc), "universeCode": args.universe_code}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"status={payload.get('status')} symbols={payload.get('symbolCount', 0)} severity={payload.get('severity')}")
    if payload.get("status") == "certified":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
