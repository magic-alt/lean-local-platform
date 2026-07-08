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
    if key in {"usa", "crypto", "crypto_future", "future"}:
        value = symbol.strip().upper().replace("_", ".")
        return value.replace("-", ".")

    if key == "china":
        value = symbol.strip().upper().replace("_", ".")
        normalized = _normalize_china_symbol(value)
        if not (normalized.isdigit() or normalized.startswith(("SH", "SZ", "SS", "BJ", "HK"))):
            raise LeanPlatformError("A-share symbols must be in a recognized format, e.g. 600519 or SH600519.")
        if normalized.startswith(("SH", "SZ", "SS", "BJ", "HK")):
            return normalized
        if normalized.isdigit() and len(normalized) != 6:
            raise LeanPlatformError("A-share symbols must be 6 digits, e.g. 600519 or 000001.")
        if not normalized.isdigit():
            raise LeanPlatformError("A-share symbols must be 6 digits, e.g. 600519 or 000001.")
        return normalized

    if key == "hongkong":
        value = symbol.strip().upper().replace("_", "")
        value = value.replace("HK", "").replace(".", "")
        if not value.isdigit():
            raise LeanPlatformError("Hong Kong symbols must be numeric, e.g. 00700.")
        if len(value) > 5:
            raise LeanPlatformError("Hong Kong symbols must be 5 digits max, e.g. 00700.")
        return value.zfill(5)

    return symbol.strip().upper()


def _normalize_china_symbol(value: str) -> str:
    value = value.upper()
    if value.startswith(("SH.", "SZ.", "SS.", "BJ.")):
        stripped = value[3:]
        if stripped.isdigit() and len(stripped) in {5, 6}:
            return stripped
        raise LeanPlatformError(f"Invalid A-share symbol: {value!r}")
    if value.startswith("SH") or value.startswith("SZ") or value.startswith("SS") or value.startswith("BJ"):
        stripped = value[2:]
        if stripped.isdigit() and len(stripped) in {5, 6}:
            return stripped
        raise LeanPlatformError(f"Invalid A-share symbol: {value!r}")
    if "." in value:
        base, suffix = value.rsplit(".", 1)
        suffix = suffix.upper()
        if suffix in {"T", "KS", "KQ", "TW", "TWO"} and base.isdigit() and 4 <= len(base) <= 6:
            return f"{base}.{suffix}"
        if suffix in {"HK"} and base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"
        if suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit() and len(base) == 6:
            return base
        if base.upper() in {"SH", "SZ", "SS", "BJ"} and suffix.isdigit():
            return suffix
        if suffix.isdigit():
            raise LeanPlatformError(f"Invalid A-share suffix format: {value!r}")
    return value


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise LeanPlatformError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc
