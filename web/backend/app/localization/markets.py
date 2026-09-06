"""Market-localization profiles layered on top of upstream LEAN.

These profiles describe local data/symbol conventions. They do not replace LEAN's
security, order, portfolio, brokerage, or algorithm engines. Execution support must
remain fail-closed when a profile declares per-security metadata as required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


MARKET_PROFILES: dict[str, dict[str, Any]] = {
    "usa": {
        "name": "US Equity",
        "currency": "USD",
        "timezone": "America/New_York",
        "open": "09:30:00",
        "close": "16:00:00",
        "sessions": (("09:30:00", "16:00:00"),),
        "lot_size": "1",
        "tick_size": "0.01",
        "market_id": 1,
        "implementation_status": "upstream",
        "execution_scope": "upstream",
        "lot_size_policy": "upstream_symbol_properties",
        "tick_size_policy": "upstream_symbol_properties",
        "symbol_properties_required": False,
    },
    "china": {
        "name": "China A Share",
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
        "open": "09:30:00",
        "close": "15:00:00",
        "sessions": (("09:30:00", "11:30:00"), ("13:00:00", "15:00:00")),
        "lot_size": "100",
        "tick_size": "0.01",
        "market_id": 101,
        "implementation_status": "implemented",
        "execution_scope": "daily_localized",
        "lot_size_policy": "board_lot_100_with_security_overrides",
        "tick_size_policy": "security_properties_override_supported",
        "symbol_properties_required": False,
        "symbol_formats": ("600519", "SH600519", "000001.SZ"),
        "notes": (
            "Daily A-share localization is implemented, but release certification is governed separately. "
            "Lunch break is represented explicitly in generated LEAN market hours."
        ),
    },
    "hongkong": {
        "name": "Hong Kong Equity",
        "currency": "HKD",
        "timezone": "Asia/Hong_Kong",
        "open": "09:30:00",
        "close": "16:10:00",
        "sessions": (("09:30:00", "12:00:00"), ("13:00:00", "16:10:00")),
        "lot_size": "1",
        "tick_size": "0.01",
        "market_id": 102,
        "implementation_status": "partial",
        "execution_scope": "preview_only",
        "lot_size_policy": "per_security_board_lot_required",
        "tick_size_policy": "per_security_price_tier_required",
        "symbol_properties_required": True,
        "symbol_formats": ("00700", "HK00700", "0700.HK"),
        "notes": (
            "Symbol normalization and LEAN data layout are available. Authoritative execution remains preview-only "
            "until per-security board-lot/tick metadata, exchange calendar coverage, fees and validation evidence are certified."
        ),
    },
}


def public_market_profiles() -> list[dict[str, Any]]:
    """Return JSON-safe localization capabilities without internal numeric IDs."""
    result: list[dict[str, Any]] = []
    for key, raw in MARKET_PROFILES.items():
        item = deepcopy(raw)
        item.pop("market_id", None)
        item["key"] = key
        item["sessions"] = [list(session) for session in item.get("sessions", ())]
        item["symbol_formats"] = list(item.get("symbol_formats", ()))
        result.append(item)
    return result


def market_profile(market: str) -> dict[str, Any]:
    key = str(market).strip().lower()
    if key not in MARKET_PROFILES:
        raise KeyError(f"Unknown localization market: {market}")
    return deepcopy(MARKET_PROFILES[key])
