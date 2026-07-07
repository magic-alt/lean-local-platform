from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from typing import Any

from ..db import db, rows_to_dicts, row_to_dict, utc_now
from ..lean_engine.symbols import normalize_symbol


IDENTIFIER_NAMESPACE = uuid.UUID("218a4045-7221-4d43-ac4f-f196fc3bf4ea")
INDEX_SYMBOLS = {"000300", "000905", "000852", "000016", "399300"}
REQUIRED_IDENTIFIER_TYPES = {"raw_symbol", "exchange_symbol", "ts_code", "lean_symbol", "provider_symbol"}


def _normalize_candidate_symbol(symbol: str) -> str | None:
    value = str(symbol or "").strip().upper()
    if not value:
        return None
    if "." in value:
        value = value.split(".", 1)[0]
    if value.startswith(("SH", "SZ", "BJ")):
        value = value[2:]
    if value.isdigit() and len(value) <= 6:
        return value.zfill(6)
    try:
        return normalize_symbol(value, "china")
    except Exception:
        return None


def exchange_for_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.startswith(("SH", "SZ", "BJ")):
        return value[:2]
    normalized = _normalize_candidate_symbol(value) or value
    if normalized in INDEX_SYMBOLS:
        return "SH" if normalized.startswith("0") else "SZ"
    if value.startswith("6") or value.startswith("9"):
        return "SH"
    if value.startswith(("0", "3")):
        return "SZ"
    if value.startswith("8"):
        return "BJ"
    return "CN"


def _canonical_exchange(exchange: str | None, symbol: str) -> str:
    value = str(exchange or "").strip().upper()
    aliases = {
        "SSE": "SH",
        "XSHG": "SH",
        "SHSE": "SH",
        "SH": "SH",
        "SZSE": "SZ",
        "XSHE": "SZ",
        "SZ": "SZ",
        "BSE": "BJ",
        "XBSE": "BJ",
        "BJ": "BJ",
    }
    return aliases.get(value, exchange_for_symbol(symbol))


def ts_code(symbol: str) -> str:
    exchange = exchange_for_symbol(symbol)
    suffix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ", "CSI": "SH"}.get(exchange, exchange)
    return f"{symbol}.{suffix}"


def instrument_id_for(symbol: str, *, asset_class: str = "equity", market: str = "china", venue: str = "china") -> str:
    return str(uuid.uuid5(IDENTIFIER_NAMESPACE, f"{asset_class}:{market}:{venue}:{symbol}"))


def candidate_instruments(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    if symbols:
        selected = sorted({value for symbol in symbols if (value := _normalize_candidate_symbol(symbol))})
        return [{"symbol": symbol, "sources": ["cli"], "reason": None} for symbol in selected]
    with db() as connection:
        queries = {
            "securities": "select symbol from securities",
            "instruments": "select symbol from instruments where asset_class = 'equity' and market = 'china'",
            "ashare_daily_bars": "select distinct symbol from ashare_daily_bars",
            "market_daily_bars": "select distinct symbol from market_daily_bars where asset_class = 'equity' and market = 'china'",
        }
        found: dict[str, set[str]] = defaultdict(set)
        invalid: Counter[str] = Counter()
        for source_name, sql in queries.items():
            for row in connection.execute(sql).fetchall():
                raw = row["symbol"]
                normalized = _normalize_candidate_symbol(raw)
                if normalized:
                    found[normalized].add(source_name)
                elif raw:
                    invalid[source_name] += 1
    return [
        {"symbol": symbol, "sources": sorted(sources), "reason": None}
        for symbol, sources in sorted(found.items())
    ] + [
        {"symbol": f"__invalid__:{source_name}", "sources": [source_name], "reason": f"invalid_symbol_count:{count}"}
        for source_name, count in sorted(invalid.items())
        if count
    ]


def _candidate_symbols(symbols: list[str] | None = None) -> list[str]:
    return [item["symbol"] for item in candidate_instruments(symbols) if not str(item["symbol"]).startswith("__invalid__:")]


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
    exchange = _canonical_exchange(security_item.get("exchange"), symbol)
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
    exchange = _canonical_exchange(instrument.get("exchange"), symbol)
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
    candidates = candidate_instruments(symbols)
    selected = [item["symbol"] for item in candidates if not str(item["symbol"]).startswith("__invalid__:")]
    rows: list[dict[str, Any]] = []
    for symbol in selected:
        instrument = _instrument_row(symbol)
        rows.extend(_identifier_rows(symbol, instrument, source=source, batch_id=batch_id))
    conflicts = identifier_conflicts(proposed_rows=rows)
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
        "conflicts": conflicts,
        "candidateSources": {item["symbol"]: item["sources"] for item in candidates if not str(item["symbol"]).startswith("__invalid__:")},
        "invalidCandidates": [item for item in candidates if str(item["symbol"]).startswith("__invalid__:")],
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
    missing_reasons: dict[str, str] = {}
    counts: dict[str, int] = {}
    type_counts: dict[str, dict[str, int]] = {}
    for symbol in selected:
        item = identifiers_for_symbol(symbol)
        counts[symbol] = item["count"]
        types = Counter(str(row.get("identifier_type") or row.get("id_type")) for row in item["items"])
        type_counts[symbol] = dict(types)
        missing_types = sorted(REQUIRED_IDENTIFIER_TYPES - set(types))
        if item["count"] == 0:
            missing.append(symbol)
            missing_reasons[symbol] = "no_identifiers"
        elif missing_types:
            missing.append(symbol)
            missing_reasons[symbol] = "missing_identifier_types:" + ",".join(missing_types)
    total = len(selected)
    covered = total - len(missing)
    return {
        "total": total,
        "covered": covered,
        "missing": len(missing),
        "totalInstruments": total,
        "coveredInstruments": covered,
        "missingInstruments": len(missing),
        "coverageRatio": covered / total if total else 1.0,
        "missingSymbols": missing[:50],
        "missingReasons": missing_reasons,
        "counts": counts,
        "typeCounts": type_counts,
    }


def identifier_conflicts(proposed_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    with db() as connection:
        rows = connection.execute(
            """
            select instrument_id, provider, identifier_type, identifier_value, valid_from
            from instrument_identifiers
            where provider is not null and identifier_type is not null and identifier_value is not null
            """
        ).fetchall()
    for row in rows_to_dicts(rows):
        key = (
            str(row.get("provider") or ""),
            str(row.get("identifier_type") or ""),
            str(row.get("identifier_value") or ""),
            str(row.get("valid_from") or ""),
        )
        grouped[key].add(str(row.get("instrument_id") or ""))
    for row in proposed_rows or []:
        key = (
            str(row.get("provider") or ""),
            str(row.get("identifier_type") or ""),
            str(row.get("identifier_value") or ""),
            str(row.get("valid_from") or ""),
        )
        grouped[key].add(str(row.get("instrument_id") or ""))
    conflicts = [
        {
            "provider": key[0],
            "identifierType": key[1],
            "identifierValue": key[2],
            "validFrom": key[3],
            "instrumentIds": sorted(ids),
        }
        for key, ids in sorted(grouped.items())
        if len(ids) > 1
    ]
    return {"count": len(conflicts), "items": conflicts[:100]}
