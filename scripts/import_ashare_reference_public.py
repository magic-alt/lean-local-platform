#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from numbers import Number
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db  # noqa: E402
from app.services.ashare_repository import import_security_master, import_trade_status, upsert_corporate_actions  # noqa: E402


def _akshare_module():
    import akshare as ak  # type: ignore

    return ak


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    if hasattr(frame, "to_dict"):
        return [dict(item) for item in frame.to_dict("records")]
    return []


def _blank(value: Any) -> bool:
    if value in (None, ""):
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"nan", "nat", "none", "null", "-"}:
        return True
    return False


def _first(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row and not _blank(row[key]):
            return row[key]
        value = lowered.get(key.lower())
        if not _blank(value):
            return value
    return None


def _symbol(value: Any) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(6)[-6:]


def _date(value: Any) -> str | None:
    if _blank(value):
        return None
    if isinstance(value, Number) and math.isfinite(float(value)):
        number = int(float(value))
        if number > 10_000_000_000:
            number = number // 1000
        if number > 1_000_000_000:
            return datetime.fromtimestamp(number, tz=timezone.utc).date().isoformat()
    raw = str(value).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 12:
        timestamp = int(digits)
        if timestamp > 10_000_000_000:
            timestamp = timestamp // 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()
    text = str(value).strip()[:10]
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _float(value: Any) -> float | None:
    if _blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_st_name(value: Any) -> bool:
    name = str(value or "").strip().upper().replace(" ", "")
    return name.startswith(("ST", "*ST", "S*ST", "SST")) or "退" in name


def _mark_security_st(symbols: list[str]) -> None:
    if not symbols:
        return
    placeholders = ",".join("?" for _ in symbols)
    with db() as connection:
        connection.execute(f"update securities set is_st = 1, updated_at = updated_at where symbol in ({placeholders})", symbols)


def fetch_delisted_records(ak: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    sources = [
        ("stock_info_sh_delist", ak.stock_info_sh_delist, {"symbol": "全部"}, ("公司代码", "证券代码", "代码"), ("公司简称", "证券简称", "名称"), "暂停上市日期"),
        ("stock_info_sz_delist", ak.stock_info_sz_delist, {"symbol": "终止上市公司"}, ("证券代码", "公司代码", "代码"), ("证券简称", "公司简称", "名称"), "终止上市日期"),
    ]
    for name, func, kwargs, code_keys, name_keys, delisted_key in sources:
        try:
            for row in _records(func(**kwargs)):
                symbol = _symbol(_first(row, *code_keys))
                listed_date = _date(_first(row, "上市日期", "首发上市日期"))
                delisted_date = _date(_first(row, delisted_key, "终止上市日期", "暂停上市日期"))
                if not symbol or not listed_date:
                    continue
                security_name = _first(row, *name_keys) or symbol
                records.append(
                    {
                        "symbol": symbol,
                        "name": security_name,
                        "listed_date": listed_date,
                        "delisted_date": delisted_date,
                        "status": "delisted",
                        "is_st": _is_st_name(security_name),
                        "source": f"akshare:{name}",
                    }
                )
        except Exception as exc:
            errors.append({"source": name, "error": str(exc)})
    return records, errors


def fetch_st_status_records(ak: Any, as_of_date: str) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    symbols: list[str] = []
    try:
        rows = _records(ak.stock_zh_a_st_em())
        for row in rows:
            symbol = _symbol(_first(row, "代码", "证券代码", "股票代码"))
            if not symbol:
                continue
            symbols.append(symbol)
            records.append({"symbol": symbol, "tradeDate": as_of_date, "isSt": True, "canBuy": True, "canSell": True})
    except Exception as exc:
        errors.append({"source": "stock_zh_a_st_em", "error": str(exc)})
    return records, symbols, errors


def fetch_suspended_status_records(ak: Any, as_of_date: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    records: list[dict[str, Any]] = []
    try:
        rows = _records(ak.stock_zh_a_stop_em())
        for row in rows:
            symbol = _symbol(_first(row, "代码", "证券代码", "股票代码"))
            if not symbol:
                continue
            records.append(
                {
                    "symbol": symbol,
                    "tradeDate": as_of_date,
                    "isSuspended": True,
                    "canBuy": False,
                    "canSell": False,
                    "isSt": _is_st_name(_first(row, "名称", "证券简称", "股票简称")),
                }
            )
    except Exception as exc:
        errors.append({"source": "stock_zh_a_stop_em", "error": str(exc)})
    if records:
        return records, errors

    try:
        rows = _records(ak.stock_tfp_em(date=as_of_date.replace("-", "")))
        for row in rows:
            symbol = _symbol(_first(row, "代码", "证券代码", "股票代码"))
            if not symbol:
                continue
            suspend_date = _date(_first(row, "停牌时间", "停牌日期", "SUSPEND_START_DATE"))
            resume_date = _date(_first(row, "预计复牌时间", "复牌时间", "RESUME_DATE"))
            records.append(
                {
                    "symbol": symbol,
                    "tradeDate": as_of_date,
                    "isSuspended": True,
                    "canBuy": False,
                    "canSell": False,
                    "isSt": _is_st_name(_first(row, "名称", "证券简称", "股票简称")),
                    "suspendDate": suspend_date,
                    "resumeDate": resume_date,
                }
            )
    except Exception as exc:
        errors.append({"source": "stock_tfp_em", "error": str(exc)})
    return records, errors


def fetch_dividend_records(ak: Any, symbols: list[str], start_date: str | None, end_date: str | None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            rows = _records(ak.stock_dividend_cninfo(symbol=symbol))
            for row in rows:
                ex_date = _date(_first(row, "除权日", "除权除息日"))
                if not ex_date:
                    continue
                if start_date and ex_date < start_date:
                    continue
                if end_date and ex_date > end_date:
                    continue
                cash = _float(_first(row, "派息比例", "现金分红-现金分红比例"))
                bonus = _float(_first(row, "送股比例", "送转股份-送股比例")) or 0.0
                conversion = _float(_first(row, "转增比例", "送转股份-转股比例")) or 0.0
                records.append(
                    {
                        "symbol": symbol,
                        "exDate": ex_date,
                        "actionType": "dividend",
                        "cashDividend": cash / 10.0 if cash is not None else None,
                        "stockDividend": (bonus + conversion) / 10.0 if bonus or conversion else None,
                        "source": "akshare:stock_dividend_cninfo",
                    }
                )
        except Exception as exc:
            errors.append({"symbol": symbol, "source": "stock_dividend_cninfo", "error": str(exc)})
    return records, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Import public A-share reference data into MySQL canonical tables.")
    parser.add_argument("--symbols", default="600519,000001", help="Comma-separated symbols for per-symbol corporate actions.")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--no-delisted", action="store_true")
    parser.add_argument("--no-st", action="store_true")
    parser.add_argument("--no-suspended", action="store_true")
    parser.add_argument("--no-dividends", action="store_true")
    args = parser.parse_args()

    init_db()
    ak = _akshare_module()
    symbols = [item.strip().zfill(6)[-6:] for item in args.symbols.split(",") if item.strip()]
    errors: list[dict[str, str]] = []
    result: dict[str, Any] = {
        "source": "akshare",
        "asOfDate": args.as_of_date,
        "symbols": symbols,
        "delisted": {"count": 0},
        "st": {"count": 0},
        "suspended": {"count": 0},
        "corporateActions": {"count": 0},
        "errors": errors,
    }

    if not args.no_delisted:
        records, source_errors = fetch_delisted_records(ak)
        errors.extend(source_errors)
        if records:
            result["delisted"] = import_security_master(records, source="akshare:delist", universe_code="ALL_A")
            result["delisted"]["count"] = len(records)

    if not args.no_st:
        records, st_symbols, source_errors = fetch_st_status_records(ak, args.as_of_date)
        errors.extend(source_errors)
        if st_symbols:
            _mark_security_st(st_symbols)
        if records:
            result["st"] = import_trade_status(records, source="akshare:st")

    if not args.no_suspended:
        records, source_errors = fetch_suspended_status_records(ak, args.as_of_date)
        errors.extend(source_errors)
        if records:
            result["suspended"] = import_trade_status(records, source="akshare:suspended")

    if not args.no_dividends:
        records, source_errors = fetch_dividend_records(ak, symbols, args.start_date, args.end_date)
        errors.extend(source_errors)
        if records:
            result["corporateActions"] = upsert_corporate_actions(records, source="akshare:stock_dividend_cninfo")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["delisted"]["count"] or result["st"]["count"] or result["suspended"]["count"] or result["corporateActions"]["count"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
