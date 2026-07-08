#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db, rows_to_dicts  # noqa: E402
from app.services.source_gate import PRIMARY_DATA_SOURCE  # noqa: E402
from app.services.universe_certification import certified_symbols  # noqa: E402


def _csv(value: str | None) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in (value or "").split(",") if item.strip()]


def _tier(source: str | None) -> str:
    value = (source or "").lower()
    if "official" in value:
        return "official"
    if any(key in value for key in ("tushare", "akshare", "eastmoney", "baostock", "adata")):
        return "provider"
    if "inferred" in value or "ohlcv" in value:
        return "inferred"
    if "fallback" in value:
        return "fallback"
    return "unknown"


def _coverage(symbols: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    if not symbols:
        return {"symbols": [], "summary": {}}
    placeholders = ", ".join("?" for _ in symbols)
    with db() as connection:
        rows = connection.execute(
            f"""
            select *
            from ashare_trade_status
            where symbol in ({placeholders}) and trade_date between ? and ?
            order by symbol, trade_date
            """,
            (*symbols, start_date, end_date),
        ).fetchall()
    by_symbol: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    for row in rows_to_dicts(rows):
        by_symbol.setdefault(row["symbol"], []).append(row)
    items = []
    for symbol, records in sorted(by_symbol.items()):
        tiers: dict[str, int] = {}
        for record in records:
            tiers[_tier(record.get("source"))] = tiers.get(_tier(record.get("source")), 0) + 1
        items.append(
            {
                "symbol": symbol,
                "rows": len(records),
                "sourceTiers": tiers,
                "stRows": sum(1 for row in records if row.get("is_st")),
                "suspendedRows": sum(1 for row in records if row.get("is_suspended")),
                "limitUpRows": sum(1 for row in records if row.get("is_limit_up")),
                "limitDownRows": sum(1 for row in records if row.get("is_limit_down")),
                "oneWordLimitUpRows": sum(1 for row in records if row.get("is_one_word_limit_up")),
                "oneWordLimitDownRows": sum(1 for row in records if row.get("is_one_word_limit_down")),
                "canBuyRows": sum(1 for row in records if row.get("can_buy")),
                "canSellRows": sum(1 for row in records if row.get("can_sell")),
            }
        )
    missing = [item["symbol"] for item in items if item["rows"] == 0]
    return {
        "symbols": items,
        "summary": {
            "symbolCount": len(symbols),
            "coveredSymbols": len(symbols) - len(missing),
            "missingSymbols": missing,
            "coverageRatio": (len(symbols) - len(missing)) / len(symbols) if symbols else 1.0,
        },
    }


def _infer_missing(symbols: list[str], source: str, start_date: str, end_date: str) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    inserted = 0
    with db() as connection:
        for symbol in symbols:
            rows = connection.execute(
                """
                select symbol, trade_date, open, high, low, close
                from ashare_daily_bars
                where symbol = ? and source = ? and adjust = 'raw' and trade_date between ? and ?
                  and trade_date not in (select trade_date from ashare_trade_status where symbol = ?)
                order by trade_date
                """,
                (symbol, source, start_date, end_date, symbol),
            ).fetchall()
            for row in rows:
                close = float(row["close"] or 0)
                limit_up = round(close * 1.1, 2) if close else None
                limit_down = round(close * 0.9, 2) if close else None
                connection.execute(
                    """
                    insert into ashare_trade_status
                        (symbol, trade_date, is_suspended, limit_up, limit_down, is_limit_up,
                         is_limit_down, is_one_word_limit_up, is_one_word_limit_down,
                         can_buy, can_sell, is_st, source, batch_id)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        row["trade_date"],
                        0,
                        limit_up,
                        limit_down,
                        0,
                        0,
                        0,
                        0,
                        1,
                        1,
                        0,
                        "ohlcv_inferred",
                        batch_id,
                    ),
                )
                inserted += 1
    return {"batchId": batch_id, "inserted": inserted, "sourceTier": "inferred"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import or validate A-share trade reference coverage.")
    parser.add_argument("--symbols")
    parser.add_argument("--universe-code")
    parser.add_argument("--source", default=PRIMARY_DATA_SOURCE)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--infer-missing", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    symbols = certified_symbols(args.universe_code) if args.universe_code else []
    if args.symbols:
        symbols = _csv(args.symbols)
    if not symbols:
        payload = {"status": "failed", "severity": "critical", "error": "--symbols or --universe-code is required"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    inferred = _infer_missing(symbols, args.source, args.start_date, args.end_date) if args.infer_missing else None
    coverage = _coverage(symbols, args.start_date, args.end_date)
    severity = "critical" if coverage["summary"]["missingSymbols"] else ("warning" if any(item["sourceTiers"].get("inferred") for item in coverage["symbols"]) else "ok")
    payload = {"status": "ok" if severity != "critical" else "failed", "severity": severity, "coverage": coverage, "inferred": inferred}
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if severity == "ok" else (1 if severity == "warning" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
