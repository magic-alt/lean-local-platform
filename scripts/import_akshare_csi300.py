#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import database_descriptor, db, init_db  # noqa: E402
from app.services import market_lake  # noqa: E402
from app.lean import LeanPlatformError, normalize_symbol  # noqa: E402
from app.services.ashare_repository import universe_as_of  # noqa: E402
from app.services.data import fetch_and_import_symbol  # noqa: E402
from app.services.pit_data import import_index_members  # noqa: E402


def _akshare_module():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed. Run: cd web/backend && .venv/bin/python -m pip install -r requirements.txt") from exc
    return ak


def _record_value(record: dict[str, Any], candidates: list[str]) -> Any:
    for key in candidates:
        if key in record and record[key] not in (None, ""):
            return record[key]
    lowered = {str(key).strip().lower(): value for key, value in record.items()}
    for key in candidates:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _clean_date(value: Any, fallback: str) -> str:
    if value in (None, ""):
        return fallback
    text = str(value).strip()[:10]
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def fetch_csi300_members() -> list[dict[str, Any]]:
    ak = _akshare_module()
    errors = []
    for name in ("index_stock_cons_csindex", "index_stock_cons_sina", "index_stock_cons"):
        try:
            frame = getattr(ak, name)(symbol="000300")
            if frame is None or getattr(frame, "empty", True):
                raise RuntimeError("empty dataframe")
            records = frame.to_dict("records")
            members = []
            for record in records:
                raw_symbol = _record_value(record, ["品种代码", "成分券代码", "证券代码", "code", "symbol"])
                if raw_symbol in (None, ""):
                    continue
                symbol = normalize_symbol(str(raw_symbol), "china")
                members.append(
                    {
                        "symbol": symbol,
                        "name": _record_value(record, ["品种名称", "成分券名称", "证券名称", "name"]) or symbol,
                        "start_date": _clean_date(_record_value(record, ["日期", "纳入日期", "入选日期", "start_date"]), date.today().isoformat()),
                        "universe_code": "CSI300",
                        "source": f"akshare:csi300:{name}",
                    }
                )
            if members:
                return sorted({item["symbol"]: item for item in members}.values(), key=lambda item: item["symbol"])
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Could not fetch CSI300 constituents from AKShare: " + "; ".join(errors))


def replace_akshare_csi300_membership() -> None:
    with db() as connection:
        connection.execute(
            """
            delete from universe_membership
            where universe_code = 'CSI300' and source like 'akshare:%'
            """
        )


def summarize_database(symbols: list[str], start: str, end: str, membership_as_of: str) -> dict[str, Any]:
    placeholders = ",".join("?" for _ in symbols)
    if not placeholders:
        return {"symbols": 0, "bars": 0, "firstDate": None, "lastDate": None, "assets": 0, "csi300Members": 0}
    bars = market_lake.aggregate(
        kind="bars", asset_class="equity", market="china", venue="china",
        columns="count(*) as rows,count(distinct symbol) as symbols,min(trade_date) as first_date,max(trade_date) as last_date",
        predicates=(f"symbol in ({placeholders})", "trade_date>=?", "trade_date<=?"),
        parameters=[*symbols, start, end],
    )
    with db() as connection:
        assets = connection.execute(
            f"""
            select count(*) as rows
            from data_assets
            where symbol in ({placeholders}) and asset_class = 'equity' and venue = 'china'
            """,
            symbols,
        ).fetchone()
    csi300_members = universe_as_of("CSI300", membership_as_of)
    return {
        "symbols": bars["symbols"] if bars else 0,
        "bars": bars["rows"] if bars else 0,
        "firstDate": bars["first_date"] if bars else None,
        "lastDate": bars["last_date"] if bars else None,
        "assets": assets["rows"] if assets else 0,
        "csi300Members": len(csi300_members),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Import CSI300 current constituents and A-share daily bars from AKShare.")
    parser.add_argument("--start", default="2024-01-01", help="Start date, YYYY-MM-DD. Default: 2024-01-01")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date, YYYY-MM-DD. Default: today")
    parser.add_argument("--adjust", default="raw", choices=["raw", "qfq", "hfq"], help="AKShare adjustment mode. Default: raw")
    parser.add_argument("--limit", type=int, default=0, help="Import only the first N CSI300 symbols, for smoke tests.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols to import after fetching CSI300 membership.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between symbols. Default: 0.2")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing LEAN zip files.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on first symbol import failure.")
    parser.add_argument("--keep-membership", action="store_true", help="Do not delete prior AKShare CSI300 membership rows before import.")
    parser.add_argument(
        "--allow-missing-trade-dates",
        action="store_true",
        help="Store symbols with missing trade dates as warning-only. Use only for public data gaps or suspension-like gaps.",
    )
    parser.add_argument(
        "--repair-ohlc-errors",
        action="store_true",
        help="Repair malformed provider high/low rows by expanding high/low around open/high/low/close and record a QA warning.",
    )
    args = parser.parse_args()

    init_db()
    members = fetch_csi300_members()
    if not args.keep_membership:
        replace_akshare_csi300_membership()
    import_index_members(members, source="akshare:csi300")
    membership_as_of = max(item["start_date"] for item in members)
    selected = members
    if args.symbols.strip():
        wanted = {normalize_symbol(item.strip(), "china") for item in args.symbols.split(",") if item.strip()}
        selected = [item for item in members if item["symbol"] in wanted]
    if args.limit > 0:
        selected = selected[: args.limit]

    print(f"database={json.dumps(database_descriptor(), ensure_ascii=False)}")
    print(
        f"csi300_members={len(members)} membership_as_of={membership_as_of} "
        f"selected={len(selected)} start={args.start} end={args.end} adjust={args.adjust}"
    )

    successes: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, member in enumerate(selected, start=1):
        symbol = member["symbol"]
        name = member.get("name") or symbol
        try:
            asset = fetch_and_import_symbol(
                symbol,
                "akshare",
                market="china",
                asset_class="equity",
                venue="china",
                resolution="daily",
                data_type="trade",
                overwrite=args.overwrite,
                start_date=args.start,
                end_date=args.end,
                adjust=args.adjust,
                allow_missing_trade_dates=args.allow_missing_trade_dates,
                repair_ohlc_errors=args.repair_ohlc_errors,
            )
            successes.append(asset)
            print(f"[{index:03d}/{len(selected):03d}] OK {symbol} {name} rows={asset.get('rows')} first={asset.get('first_date')} last={asset.get('last_date')}")
        except (Exception, LeanPlatformError) as exc:
            failures.append({"symbol": symbol, "name": str(name), "error": str(exc)})
            print(f"[{index:03d}/{len(selected):03d}] FAIL {symbol} {name}: {exc}", file=sys.stderr)
            if args.stop_on_error:
                break
        if args.sleep > 0:
            time.sleep(args.sleep)

    summary = summarize_database([item["symbol"] for item in selected], args.start, args.end, membership_as_of)
    print(
        "summary "
        f"success={len(successes)} failed={len(failures)} "
        f"db_symbols={summary['symbols']} bars={summary['bars']} "
        f"first={summary['firstDate']} last={summary['lastDate']} "
        f"assets={summary['assets']} csi300_members={summary['csi300Members']}"
    )
    if failures:
        print("failures:")
        for failure in failures[:50]:
            print(f"- {failure['symbol']} {failure['name']}: {failure['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
