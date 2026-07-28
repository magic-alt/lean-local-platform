from __future__ import annotations

from typing import Any

from ..db import db, rows_to_dicts
from ..lean_engine.symbols import normalize_symbol


def canonical_security_symbol(value: Any, market: str | None = None) -> str:
    if isinstance(value, dict):
        value = (
            value.get("value")
            or value.get("Value")
            or value.get("symbol")
            or value.get("Symbol")
            or ""
        )
    text = str(value or "").strip().upper()
    market_value = str(market or "").strip().lower()
    if market_value in {"china", "cn", "a", "ashare"} and text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    if market_value in {"hongkong", "hk", "hkg"} and text.isdigit() and len(text) <= 5:
        return text.zfill(5)
    try:
        return normalize_symbol(text, market_value) if text and market_value else text
    except Exception:
        return text


def resolve_security_identities(
    symbols: list[Any],
    *,
    market: str | None = None,
    asset_class: str = "equity",
) -> dict[str, dict[str, Any]]:
    normalized = list(dict.fromkeys(
        canonical_security_symbol(symbol, market)
        for symbol in symbols
        if str(symbol or "").strip()
    ))
    if not normalized:
        return {}
    placeholders = ",".join("?" for _ in normalized)
    parameters = tuple(normalized)
    try:
        with db() as connection:
            securities = rows_to_dicts(connection.execute(
                f"""
                select symbol,name,market,exchange
                from securities
                where symbol in ({placeholders})
                """,
                parameters,
            ).fetchall())
            instruments = rows_to_dicts(connection.execute(
                f"""
                select symbol,name,market,exchange
                from instruments
                where asset_class=? and symbol in ({placeholders})
                order by updated_at desc
                """,
                (asset_class, *parameters),
            ).fetchall())
    except Exception:
        securities = []
        instruments = []

    identities: dict[str, dict[str, Any]] = {
        symbol: {
            "symbol": symbol,
            "name": None,
            "market": market,
            "exchange": None,
            "display": symbol,
        }
        for symbol in normalized
    }
    for row in [*instruments, *securities]:
        symbol = canonical_security_symbol(row.get("symbol"), row.get("market") or market)
        if symbol not in identities:
            continue
        current = identities[symbol]
        name = str(row.get("name") or "").strip()
        if name and name != symbol:
            current["name"] = name
        current["market"] = row.get("market") or current.get("market")
        current["exchange"] = row.get("exchange") or current.get("exchange")
    for identity in identities.values():
        identity["display"] = " ".join(
            value for value in (identity["symbol"], identity.get("name")) if value
        )
    return identities


def enrich_symbol_records(
    rows: list[dict[str, Any]],
    *,
    market: str | None = None,
    asset_class: str = "equity",
) -> list[dict[str, Any]]:
    identities = resolve_security_identities(
        [row.get("symbol") for row in rows],
        market=market,
        asset_class=asset_class,
    )
    enriched = []
    for row in rows:
        symbol = canonical_security_symbol(row.get("symbol"), market)
        identity = identities.get(symbol) or {
            "symbol": symbol,
            "name": None,
            "display": symbol,
        }
        enriched.append({
            **row,
            "symbol": symbol,
            "securityName": identity.get("name"),
            "symbolDisplay": identity.get("display") or symbol,
        })
    return enriched
