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
from app.services.paper import _replay_dates, create_session, create_signal, list_orders, run_replay  # noqa: E402


def _symbols(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic Paper Replay acceptance scenario with at least one fill and one rejection.")
    parser.add_argument("--symbols", default="600519,000001", help="Comma-separated symbols. First fills, second is blacklisted.")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--start-date", default="2026-06-01")
    parser.add_argument("--end-date", default="2026-06-30")
    parser.add_argument("--cash", type=float, default=1_000_000)
    parser.add_argument("--min-trading-days", type=int, default=10)
    args = parser.parse_args()

    init_db()
    symbols = _symbols(args.symbols)
    if len(symbols) < 2:
        raise SystemExit("--symbols must contain at least two symbols.")

    session = create_session(
        {
            "symbol": symbols[0],
            "symbols": symbols,
            "assetClass": "equity",
            "market": "china",
            "cash": args.cash,
            "benchmarkSymbol": args.benchmark,
            "executionPolicy": "next_open",
            "maxPositions": max(1, len(symbols)),
            "maxPositionWeight": 0.4,
            "blacklist": symbols[1],
            "watchlist": ",".join(symbols),
            "name": "Level 3 Paper Replay Acceptance",
        }
    )
    dates = _replay_dates(session, args.start_date, args.end_date)
    if len(dates) < max(2, args.min_trading_days):
        raise SystemExit(f"insufficient trading days: {len(dates)} < {args.min_trading_days}")

    signal_date = dates[0]
    create_signal(session["id"], trade_date=signal_date, side="buy", symbol=symbols[0], target_percent=0.3)
    create_signal(session["id"], trade_date=signal_date, side="buy", symbol=symbols[1], target_percent=0.3)

    result = run_replay(session["id"], args.start_date, args.end_date, auto_signal=False)
    orders = list_orders(session["id"])
    fills = [order for order in orders if order.get("status") == "filled"]
    rejects = [order for order in orders if order.get("status") == "rejected"]
    summary = {
        "sessionId": session["id"],
        "tradingDays": result["tradingDays"],
        "fills": len(fills),
        "rejects": len(rejects),
        "rejectReasons": sorted({order.get("reason") for order in rejects if order.get("reason")}),
        "reports": len(result.get("reports") or []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["fills"] > 0 and summary["rejects"] > 0 and summary["tradingDays"] >= args.min_trading_days else 1


if __name__ == "__main__":
    raise SystemExit(main())
