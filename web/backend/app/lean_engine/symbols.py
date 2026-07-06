from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .errors import LeanPlatformError

MARKET_CONFIG: dict[str, dict[str, Any]] = {
    "usa": {
        "name": "US Equity",
        "currency": "USD",
        "timezone": "America/New_York",
        "open": "09:30:00",
        "close": "16:00:00",
        "lot_size": "1",
        "tick_size": "0.01",
        "market_id": 1,
    },
    "china": {
        "name": "China A Share",
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
        "open": "09:30:00",
        "close": "15:00:00",
        "lot_size": "100",
        "tick_size": "0.01",
        "market_id": 101,
    },
    "hongkong": {
        "name": "Hong Kong Equity",
        "currency": "HKD",
        "timezone": "Asia/Hong_Kong",
        "open": "09:30:00",
        "close": "16:00:00",
        "lot_size": "100",
        "tick_size": "0.01",
        "market_id": 102,
    },
}


def market_key(market: str | None = None) -> str:
    value = (market or "usa").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "us": "usa",
        "usa": "usa",
        "america": "usa",
        "cn": "china",
        "a": "china",
        "ashare": "china",
        "china": "china",
        "zh": "china",
        "hk": "hongkong",
        "hkg": "hongkong",
        "hongkong": "hongkong",
    }
    key = aliases.get(value, value)
    if key not in MARKET_CONFIG:
        raise LeanPlatformError(f"Unsupported market: {market!r}")
    return key


def symbol_key(symbol: str) -> str:
    cleaned = symbol.strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in ".-" for ch in cleaned):
        raise LeanPlatformError(f"Invalid symbol: {symbol!r}")
    return cleaned


def normalize_symbol(symbol: str, market: str | None = None) -> str:
    key = market_key(market)
    value = symbol_key(symbol).upper().replace("_", ".")
    if key == "usa":
        return value.replace("-", ".")
    if key == "china":
        value = value.replace("SH", "").replace("SZ", "").replace("BJ", "").replace(".", "")
        if not value.isdigit() or len(value) != 6:
            raise LeanPlatformError("A-share symbols must be 6 digits, e.g. 600519 or 000001.")
        return value
    if key == "hongkong":
        value = value.replace("HK", "").replace(".", "")
        if not value.isdigit():
            raise LeanPlatformError("Hong Kong symbols must be numeric, e.g. 00700.")
        return value.zfill(5)
    return value


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise LeanPlatformError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc
