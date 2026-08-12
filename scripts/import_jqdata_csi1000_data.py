#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import db, init_db  # noqa: E402
from app.services.data import fetch_and_import_symbol  # noqa: E402
from app.services.jqdata_adapter import jqdata_symbol  # noqa: E402
from app.services.pit_data import import_index_members  # noqa: E402


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"' ")
        if key and key not in os.environ:
            os.environ[key] = value


def _normalize_member(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("code", "symbol", "sec_code", "ts_code"):
            candidate = value.get(key)
            if candidate:
                value = candidate
                break
    text = str(value).strip().upper()
    if not text:
        return None
    if "." in text:
        text = text.split(".", 1)[0]
    text = "".join(ch for ch in text if ch.isdigit())
    if len(text) < 6:
        text = text.zfill(6)
    if len(text) != 6:
        return None
    if text.startswith(("4", "8", "9")):
        return None
    return text


def _parse_members(raw: Any) -> list[str]:
    if raw is None:
        return []
    if hasattr(raw, "to_dict"):
        try:
            columns = set(getattr(raw, "columns", ()))
            if "code" in columns:
                raw = raw["code"].tolist()
            else:
                raw = raw.to_dict("records")
        except Exception:
            pass
    if hasattr(raw, "to_list"):
        raw = raw.to_list()
    if isinstance(raw, dict):
        raw = raw.values()
    if isinstance(raw, tuple):
        raw = list(raw)
    if not isinstance(raw, list):
        if hasattr(raw, "__iter__"):
            raw = list(raw)
        else:
            return [x for x in (_normalize_member(raw),) if x]
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw:
        symbol = _normalize_member(item)
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def _auth_jqdata() -> Any:
    try:
        import jqdatasdk as jq  # type: ignore
    except Exception as exc:
        raise RuntimeError("jqdatasdk is not installed. Install it in web/backend .venv.") from exc

    token = os.environ.get("JQDATA_TOKEN")
    username = os.environ.get("JQDATA_USERNAME")
    password = os.environ.get("JQDATA_PASSWORD")
    if token:
        jq.auth_by_token(token)
    elif username and password:
        jq.auth(username, password)
    else:
        raise RuntimeError("Missing JQData credentials. Set JQDATA_TOKEN or JQDATA_USERNAME/JQDATA_PASSWORD.")
    if hasattr(jq, "is_auth") and not jq.is_auth():
        raise RuntimeError("JQData authentication failed.")
    return jq


def _parse_date(value: str) -> str:
    value = value.strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def _count_db_rows(symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """
            select
                count(*) as rows,
                min(trade_date) as firstDate,
                max(trade_date) as lastDate
            from market_daily_bars
            where asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade' and symbol = ?
              and source = 'jqdata'
              and adjust = 'raw'
              and trade_date between ? and ?
            """,
            (symbol, start_date, end_date),
        ).fetchone()
    if row is None:
        return {"rows": 0, "firstDate": None, "lastDate": None}
    return {"rows": int(row["rows"] or 0), "firstDate": row["firstDate"], "lastDate": row["lastDate"]}


def _import_membership(universe_code: str, index_symbol: str, members: list[str], source: str, start_date: str, end_date: str) -> dict[str, Any]:
    if not members:
        return {"count": 0}
    records = []
    for symbol in members:
        records.append(
            {
                "universe_code": universe_code,
                "symbol": symbol,
                "name": symbol,
                "start_date": start_date,
                "end_date": end_date,
                "source": f"{source}:membership:{index_symbol}",
            }
        )
    imported = import_index_members(records, source=f"{source}:membership:{index_symbol}")
    return imported


def main() -> int:
    parser = argparse.ArgumentParser(description="Import A-share CSI1000 components daily data from JQData entitlement window.")
    parser.add_argument("--index", default="000852", help="Index symbol, default: 000852")
    parser.add_argument("--universe-code", default="CSI1000", help="Universe code used for optional membership writeback.")
    parser.add_argument("--start-date", default=os.environ.get("JQDATA_DATA_RANGE_START", "2025-03-29"))
    parser.add_argument("--end-date", default=os.environ.get("JQDATA_DATA_RANGE_END", date.today().isoformat()))
    parser.add_argument("--import-membership", action="store_true", help="Persist CSI1000 membership into universe_membership.")
    parser.add_argument("--import-benchmark", action="store_true", help="Also import CSI1000 index bar data.")
    parser.add_argument("--no-overwrite", action="store_true", help="Keep existing local LEAN files instead of overwriting.")
    parser.add_argument("--max-symbols", type=int, default=0, help="Limit number of component symbols (0 = no limit). Useful for smoke checks.")
    parser.add_argument("--allow-missing-trade-dates", action="store_true")
    parser.add_argument("--repair-ohlc-errors", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    args = parser.parse_args()

    _load_env(ROOT / ".env")

    init_db()

    start_date = _parse_date(args.start_date)
    end_date = _parse_date(args.end_date)
    if end_date < start_date:
        message = {"status": "failed", "reason": "end-date-before-start-date", "startDate": start_date, "endDate": end_date}
        print(json.dumps(message, ensure_ascii=False, indent=2))
        return 2

    entitlement_start = _parse_date(os.environ.get("JQDATA_DATA_RANGE_START", "2025-03-29"))
    entitlement_end = _parse_date(os.environ.get("JQDATA_DATA_RANGE_END", "2026-04-05"))
    if start_date < entitlement_start or end_date > entitlement_end:
        message = {
            "status": "failed",
            "reason": "window_outside_jqdata_entitlement",
            "requested": {"startDate": start_date, "endDate": end_date},
            "entitlement": {"startDate": entitlement_start, "endDate": entitlement_end},
        }
        print(json.dumps(message, ensure_ascii=False, indent=2))
        return 3

    index_symbol = _normalize_member(args.index) or "000852"

    try:
        jq = _auth_jqdata()
        csi1000_raw = jq.get_index_stocks(jqdata_symbol(index_symbol), date=end_date)
    except Exception as exc:
        payload = {
            "status": "failed",
            "reason": "jqdata_index_fetch_failed",
            "error": str(exc),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    members = _parse_members(csi1000_raw)
    if not members:
        payload = {
            "status": "failed",
            "reason": "empty_index_members",
            "index": index_symbol,
            "provider": "jqdata",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    if args.max_symbols > 0:
        members = members[: args.max_symbols]

    success: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    symbols = [index_symbol] if args.import_benchmark else []
    symbols.extend(members)

    for symbol in symbols:
        try:
            fetch_and_import_symbol(
                symbol,
                "jqdata",
                market="china",
                asset_class="equity",
                venue="china",
                resolution="daily",
                data_type="trade",
                overwrite=not args.no_overwrite,
                start_date=start_date,
                end_date=end_date,
                adjust="raw",
                allow_missing_trade_dates=args.allow_missing_trade_dates,
                repair_ohlc_errors=args.repair_ohlc_errors,
            )
            count = _count_db_rows(symbol, start_date, end_date)
            success.append({"symbol": symbol, "source": "jqdata", "rows": count["rows"], "firstDate": count["firstDate"], "lastDate": count["lastDate"]})
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
        if args.sleep_seconds > 0 and symbol != symbols[-1]:
            time.sleep(args.sleep_seconds)

    membership_summary = None
    if args.import_membership:
        membership_summary = _import_membership(
            args.universe_code,
            index_symbol,
            members,
            "jqdata",
            start_date,
            end_date,
        )

    payload = {
        "status": "ok" if not failures else ("warning" if len(success) > 0 else "failed"),
        "provider": "jqdata",
        "indexSymbol": index_symbol,
        "universeCode": args.universe_code,
        "window": {"startDate": start_date, "endDate": end_date},
        "entitlement": {"startDate": entitlement_start, "endDate": entitlement_end},
        "memberCount": len(members),
        "requestedSymbols": len(symbols),
        "success": success,
        "failureCount": len(failures),
        "failures": failures,
        "membership": membership_summary,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not failures:
        return 0
    if not success:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
