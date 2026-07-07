from __future__ import annotations

import uuid
from typing import Any

from ..db import db, rows_to_dicts, row_to_dict, utc_now
from ..lean_engine.symbols import normalize_symbol


IDENTIFIER_NAMESPACE = uuid.UUID("218a4045-7221-4d43-ac4f-f196fc3bf4ea")


def exchange_for_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.startswith(("SH", "SZ", "BJ")):
        return value[:2]
    if value.startswith("6") or value.startswith("9"):
        return "SH"
    if value.startswith(("0", "3")):
        return "SZ"
    if value.startswith("8"):
        return "BJ"
    if value == "000300":
        return "CSI"
    return "CN"


def ts_code(symbol: str) -> str:
    exchange = exchange_for_symbol(symbol)
    suffix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ", "CSI": "SH"}.get(exchange, exchange)
    return f"{symbol}.{suffix}"


def instrument_id_for(symbol: str, *, asset_class: str = "equity", market: str = "china", venue: str = "china") -> str:
    return str(uuid.uuid5(IDENTIFIER_NAMESPACE, f"{asset_class}:{market}:{venue}:{symbol}"))


def _candidate_symbols(symbols: list[str] | None = None) -> list[str]:
    if symbols:
        return sorted({normalize_symbol(symbol, "china") for symbol in symbols})
    with db() as connection:
        rows = connection.execute(
            """
            select symbol from securities
            union
            select symbol from instruments where asset_class = 'equity' and market = 'china'
            union
            select distinct symbol from ashare_daily_bars
            union
            select distinct symbol from market_daily_bars where asset_class = 'equity' and market = 'china'
            order by symbol
            """
        ).fetchall()
    return [row["symbol"] for row in rows if row["symbol"]]


def _instrument_row(symbol: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """
            select * from instruments
            where symbol = ? and asset_class = 'equity' and market = 'china'
            order by updated_at desc
            limit 1
            """,
            (symbol,),
        ).fetchone()
        security = connection.execute("select * from securities where symbol = ?", (symbol,)).fetchone()
    item = row_to_dict(row)
    if item:
        return item
    security_item = row_to_dict(security) or {}
    exchange = security_item.get("exchange") or exchange_for_symbol(symbol)
    return {
        "instrument_id": instrument_id_for(symbol, venue="china"),
        "symbol": symbol,
        "normalized_symbol": symbol,
        "name": security_item.get("name") or symbol,
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "exchange": exchange,
        "listed_date": security_item.get("listed_date"),
        "delisted_date": security_item.get("delisted_date"),
        "status": security_item.get("status") or "active",
        "source": "canonical",
    }


def _identifier_rows(symbol: str, instrument: dict[str, Any], *, source: str, batch_id: str | None) -> list[dict[str, Any]]:
    exchange = instrument.get("exchange") or exchange_for_symbol(symbol)
    lean_symbol = normalize_symbol(symbol, "china")
    valid_from = instrument.get("listed_date") or "1900-01-01"
    valid_to = instrument.get("delisted_date")
    values = [
        ("canonical", "raw_symbol", symbol, True),
        ("canonical", "exchange_symbol", f"{exchange}{symbol}", False),
        ("tushare", "ts_code", ts_code(symbol), False),
        ("lean", "lean_symbol", lean_symbol, True),
        (source, "provider_symbol", symbol, True),
    ]
    return [
        {
            "instrument_id": instrument["instrument_id"],
            "provider": provider,
            "identifier_type": identifier_type,
            "identifier_value": identifier_value,
            "exchange": exchange,
            "market": "china",
            "valid_from": valid_from,
            "valid_to": valid_to,
            "is_primary": is_primary,
            "source": source,
            "batch_id": batch_id,
        }
        for provider, identifier_type, identifier_value, is_primary in values
    ]


def upsert_instrument_identifiers(
    *,
    symbols: list[str] | None = None,
    source: str = "akshare",
    batch_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    selected = _candidate_symbols(symbols)
    rows: list[dict[str, Any]] = []
    for symbol in selected:
        instrument = _instrument_row(symbol)
        rows.extend(_identifier_rows(symbol, instrument, source=source, batch_id=batch_id))
    if not dry_run:
        with db() as connection:
            for row in rows:
                connection.execute(
                    """
                    delete from instrument_identifiers
                    where coalesce(provider, '') = ? and coalesce(identifier_type, '') = ?
                      and coalesce(identifier_value, '') = ? and coalesce(valid_from, '') = ?
                    """,
                    (row["provider"], row["identifier_type"], row["identifier_value"], row["valid_from"]),
                )
                connection.execute(
                    """
                    insert into instrument_identifiers
                        (instrument_id, id_type, id_value, start_date, end_date, source, created_at,
                         provider, identifier_type, identifier_value, exchange, market, valid_from,
                         valid_to, is_primary, batch_id, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["instrument_id"],
                        row["identifier_type"],
                        row["identifier_value"],
                        row["valid_from"],
                        row["valid_to"],
                        row["source"],
                        now,
                        row["provider"],
                        row["identifier_type"],
                        row["identifier_value"],
                        row["exchange"],
                        row["market"],
                        row["valid_from"],
                        row["valid_to"],
                        1 if row["is_primary"] else 0,
                        row["batch_id"],
                        now,
                    ),
                )
    return {
        "status": "planned" if dry_run else "ok",
        "symbols": len(selected),
        "identifiers": len(rows),
        "dryRun": dry_run,
        "source": source,
        "sample": rows[:20],
    }


def identifiers_for_symbol(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol, "china")
    exchange_symbol = f"{exchange_for_symbol(normalized)}{normalized}"
    candidates = (normalized, exchange_symbol, ts_code(normalized))
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from instrument_identifiers
            where identifier_value in (?, ?, ?)
               or id_value in (?, ?, ?)
            order by is_primary desc, provider asc, identifier_type asc
            """,
            (*candidates, *candidates),
        ).fetchall()
    return {"symbol": normalized, "items": rows_to_dicts(rows), "count": len(rows)}


def identifier_coverage(symbols: list[str] | None = None) -> dict[str, Any]:
    selected = _candidate_symbols(symbols)
    missing: list[str] = []
    counts: dict[str, int] = {}
    for symbol in selected:
        item = identifiers_for_symbol(symbol)
        counts[symbol] = item["count"]
        if item["count"] == 0:
            missing.append(symbol)
    total = len(selected)
    covered = total - len(missing)
    return {
        "total": total,
        "covered": covered,
        "missing": len(missing),
        "coverageRatio": covered / total if total else 1.0,
        "missingSymbols": missing[:50],
        "counts": counts,
    }
