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
from app.services.ashare_multisource import compare_ashare_daily_sources_batch
from app.services.provider_certification import provider_availability_report, warning_allowlist_status
from app.services.universe_certification import certified_symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="Run batch A-share local multi-source QA and emit an acceptance report.")
    parser.add_argument("--symbols", help="Comma-separated A-share symbols.")
    parser.add_argument("--universe-code", help="Certified paper universe code.")
    parser.add_argument("--sources", default="jqdata,akshare,tushare,rqdata,baostock,adata", help="Comma-separated stored source names.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--adjust", default="raw")
    parser.add_argument("--price-abs-tolerance", type=float, default=0.02)
    parser.add_argument("--price-rel-tolerance-bps", type=float, default=5.0)
    parser.add_argument("--volume-rel-tolerance-pct", type=float, default=5.0)
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--no-symbol-reports", action="store_true")
    parser.add_argument("--allow-accepted-warnings", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    symbols = certified_symbols(args.universe_code) if args.universe_code else []
    if args.symbols:
        symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    if not symbols:
        raise SystemExit("--symbols or --universe-code is required")
    sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    result = compare_ashare_daily_sources_batch(
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        sources=sources,
        adjust=args.adjust,
        price_abs_tolerance=args.price_abs_tolerance,
        price_rel_tolerance_bps=args.price_rel_tolerance_bps,
        volume_rel_tolerance_pct=args.volume_rel_tolerance_pct,
        persist=not args.no_persist,
        persist_symbol_reports=not args.no_symbol_reports,
    )
    warning_codes = []
    if result["warningCount"]:
        warning_codes.append("provider_secondary_missing")
    acceptance = warning_allowlist_status(
        warning_codes,
        affected_symbols=symbols,
        scope={"universeCode": args.universe_code, "sources": sources, "startDate": args.start_date, "endDate": args.end_date},
    ) if args.allow_accepted_warnings else {"acceptedWarnings": [], "expiredWarnings": [], "unacceptedWarnings": warning_codes, "passed": not warning_codes}
    providers = provider_availability_report(sources, start_date=args.start_date, end_date=args.end_date, persist=False)
    result.update(
        {
            "universeCode": args.universe_code,
            "passedSymbols": [report["symbol"] for report in result.get("reports", []) if report.get("severity") == "ok"],
            "acceptedWarnings": acceptance["acceptedWarnings"],
            "expiredWarnings": acceptance["expiredWarnings"],
            "unacceptedWarnings": acceptance["unacceptedWarnings"],
            "providerCoverage": {item["provider"]: item["coverage"] for item in providers["providers"]},
            "providerAvailability": providers,
            "warningCodes": warning_codes,
            "acceptedWarningGatePassed": acceptance["passed"],
        }
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["severity"] == "critical":
        return 2
    if result["expiredWarnings"] or result["unacceptedWarnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
