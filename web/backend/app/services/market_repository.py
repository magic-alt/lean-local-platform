from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .alerts import emit_alert
from . import market_lake
from .source_gate import invalidate_source_certification


INSTRUMENT_NAMESPACE = uuid.UUID("ed487062-bcf1-47c6-8f1a-1973b5f9edb0")
WRITE_BATCH_SIZE = 5_000


def _record_certification_revocation(
    *,
    source: str,
    asset_class: str,
    market: str,
    venue: str,
) -> None:
    emit_alert(
        "source_certification_revoked",
        severity="critical",
        title="Production source certification revoked",
        message=f"{source}:{asset_class}:{market}:{venue} requires derived-layer revalidation.",
        source="source_gate",
        related_id=f"{source}:{asset_class}:{market}:{venue}",
        details={
            "source": source,
            "assetClass": asset_class,
            "market": market,
            "venue": venue,
            "automaticRecovery": "lean_web.recover_source_certifications",
        },
        dedupe_key=f"source_certification_revoked:{source}:{asset_class}:{market}:{venue}",
    )


def _chunks(values: list[Any], size: int = WRITE_BATCH_SIZE) -> list[list[Any]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


def normalize_date(value: Any, field: str = "date") -> str:
    if value in (None, ""):
        raise ValueError(f"{field} is required.")
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            raw = text if fmt == "%Y-%m-%d" else str(value).strip()[:8]
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Invalid {field}: {value!r}")


def optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def bool_int(value: Any, default: bool = False) -> int:
    if value in (None, ""):
        return 1 if default else 0
    return 1 if bool(value) else 0


def instrument_id(asset_class: str, market: str, symbol: str, venue: str | None = None) -> str:
    key = f"{asset_class.lower()}:{market.lower()}:{(venue or market).lower()}:{symbol.upper()}"
    return str(uuid.uuid5(INSTRUMENT_NAMESPACE, key))


def upsert_instrument(
    *,
    symbol: str,
    asset_class: str,
    market: str,
    venue: str | None = None,
    name: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
    base_currency: str | None = None,
    quote_currency: str | None = None,
    underlying_symbol: str | None = None,
    listed_date: str | None = None,
    delisted_date: str | None = None,
    expiry_date: str | None = None,
    status: str = "active",
    lot_size: float | None = None,
    tick_size: float | None = None,
    contract_multiplier: float | None = None,
    margin_rate: float | None = None,
    metadata: dict[str, Any] | None = None,
    source: str = "manual",
) -> str:
    now = utc_now()
    asset_class = asset_class.lower()
    market = market.lower()
    venue = (venue or market).lower()
    symbol = symbol.upper()
    item_id = instrument_id(asset_class, market, symbol, venue)
    with db() as connection:
        connection.execute(
            """
            insert into instruments
                (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange, venue,
                 currency, base_currency, quote_currency, underlying_symbol, listed_date, delisted_date,
                 expiry_date, status, lot_size, tick_size, contract_multiplier, margin_rate,
                 metadata_json, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(instrument_id) do update set
                symbol = excluded.symbol,
                normalized_symbol = excluded.normalized_symbol,
                name = case
                    when excluded.name = excluded.symbol and instruments.name <> instruments.symbol
                    then instruments.name
                    else coalesce(excluded.name, instruments.name)
                end,
                exchange = coalesce(excluded.exchange, instruments.exchange),
                venue = excluded.venue,
                currency = coalesce(excluded.currency, instruments.currency),
                base_currency = coalesce(excluded.base_currency, instruments.base_currency),
                quote_currency = coalesce(excluded.quote_currency, instruments.quote_currency),
                underlying_symbol = coalesce(excluded.underlying_symbol, instruments.underlying_symbol),
                listed_date = case
                    when instruments.listed_date is null then excluded.listed_date
                    when excluded.listed_date is null then instruments.listed_date
                    else min(instruments.listed_date, excluded.listed_date)
                end,
                delisted_date = excluded.delisted_date,
                expiry_date = coalesce(excluded.expiry_date, instruments.expiry_date),
                status = excluded.status,
                lot_size = coalesce(excluded.lot_size, instruments.lot_size),
                tick_size = coalesce(excluded.tick_size, instruments.tick_size),
                contract_multiplier = coalesce(excluded.contract_multiplier, instruments.contract_multiplier),
                margin_rate = coalesce(excluded.margin_rate, instruments.margin_rate),
                metadata_json = excluded.metadata_json,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                item_id,
                symbol,
                symbol,
                name or symbol,
                asset_class,
                market,
                exchange,
                venue,
                currency,
                base_currency,
                quote_currency,
                underlying_symbol,
                listed_date,
                delisted_date,
                expiry_date,
                status,
                lot_size,
                tick_size,
                contract_multiplier,
                margin_rate,
                json_dump(metadata or {}),
                source,
                now,
                now,
            ),
        )
    return item_id


def upsert_market_daily_bars(
    rows: list[dict[str, Any]],
    *,
    symbol: str | None = None,
    asset_class: str = "equity",
    market: str = "usa",
    venue: str | None = None,
    source: str,
    batch_id: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    bulk: bool = False,
) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    first_symbol = symbol or str(rows[0].get("symbol") or rows[0].get("code") or rows[0].get("ts_code") or "").upper()
    if not first_symbol:
        raise ValueError("symbol is required for market bars.")
    item_id = upsert_instrument(
        symbol=first_symbol,
        asset_class=asset_class,
        market=market,
        venue=venue or market,
        source=source,
        status="active",
    )
    prepared = [
        {
            **row,
            "instrument_id": item_id,
            "symbol": first_symbol,
            "batch_id": batch_id,
            "settle": row.get("settle") or row.get("settle_price"),
            "turnover_rate": row.get("turnover_rate") or row.get("turnoverRate"),
            "open_interest": row.get("open_interest") or row.get("openInterest"),
            "prev_close": row.get("prev_close") or row.get("pre_close") or row.get("prevClose"),
            "pct_change": row.get("pct_change") or row.get("pctChange"),
            "adj_factor": row.get("adj_factor") or row.get("adjFactor"),
        }
        for row in rows
    ]
    lake_result = market_lake.upsert_rows(
        prepared, kind="bars", asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
    )
    with db() as connection:
        certification_revoked = invalidate_source_certification(
            source, asset_class=asset_class, market=market, venue=venue or market,
            connection=connection,
        )
    if certification_revoked:
        _record_certification_revocation(
            source=source,
            asset_class=asset_class.lower(),
            market=market.lower(),
            venue=(venue or market).lower(),
        )
    return {"instrumentId": item_id, "count": len(prepared), **lake_result}


def upsert_market_daily_bars_batch(
    rows: list[dict[str, Any]],
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    source: str,
    batch_id: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    bulk: bool = False,
) -> dict[str, Any]:
    """Write many symbols directly to the canonical Parquet market lake."""
    if not rows:
        return {"count": 0, "symbols": 0}
    target_venue = (venue or market).lower()
    symbols = sorted({str(row.get("symbol") or "").upper() for row in rows if row.get("symbol")})
    if not symbols:
        raise ValueError("symbol is required for market bars.")
    placeholders = ",".join("?" for _ in symbols)
    with db() as connection:
        existing = connection.execute(
            f"""
            select instrument_id,symbol from instruments
            where asset_class=? and market=? and venue=? and symbol in ({placeholders})
            """,
            [asset_class.lower(), market.lower(), target_venue, *symbols],
        ).fetchall()
    instrument_ids = {str(item["symbol"]): str(item["instrument_id"]) for item in existing}
    for symbol in symbols:
        if symbol not in instrument_ids:
            instrument_ids[symbol] = upsert_instrument(
                symbol=symbol,
                asset_class=asset_class,
                market=market,
                venue=target_venue,
                source=source,
                status="active",
            )
    prepared = []
    for row in rows:
        symbol = str(row["symbol"]).upper()
        prepared.append(
            {
                **row, "symbol": symbol, "instrument_id": instrument_ids[symbol],
                "batch_id": batch_id,
                "settle": row.get("settle") or row.get("settle_price"),
                "turnover_rate": row.get("turnover_rate") or row.get("turnoverRate"),
                "open_interest": row.get("open_interest") or row.get("openInterest"),
                "prev_close": row.get("prev_close") or row.get("pre_close") or row.get("prevClose"),
                "pct_change": row.get("pct_change") or row.get("pctChange"),
                "adj_factor": row.get("adj_factor") or row.get("adjFactor"),
            }
        )
    lake_result = market_lake.upsert_rows(
        prepared, kind="bars", asset_class=asset_class, market=market, venue=target_venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
    )
    with db() as connection:
        certification_revoked = invalidate_source_certification(
            source, asset_class=asset_class, market=market, venue=target_venue,
            connection=connection,
        )
    if certification_revoked:
        _record_certification_revocation(
            source=source,
            asset_class=asset_class.lower(),
            market=market.lower(),
            venue=target_venue,
        )
    return {"count": len(prepared), "symbols": len(symbols), **lake_result}


def upsert_market_trade_status(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    source: str,
    batch_id: str | None = None,
    bulk: bool = False,
) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    normalized_rows = [{**row, "symbol": symbol} for row in rows]
    result = upsert_market_trade_status_batch(
        normalized_rows,
        asset_class=asset_class,
        market=market,
        venue=venue,
        source=source,
        batch_id=batch_id,
        bulk=bulk,
    )
    return {"instrumentId": instrument_id(asset_class, market, symbol, venue or market), **result}


def upsert_market_trade_status_batch(
    rows: list[dict[str, Any]],
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    source: str,
    batch_id: str | None = None,
    bulk: bool = False,
) -> dict[str, Any]:
    """Write trade status for many instruments with one connection/transaction."""
    if not rows:
        return {"count": 0, "instruments": 0}
    asset_class = asset_class.lower()
    market = market.lower()
    venue = (venue or market).lower()
    now = utc_now()
    symbols = sorted(
        {
            str(row.get("symbol") or row.get("code") or row.get("ts_code") or "").split(".", 1)[0].upper()
            for row in rows
        }
        - {""}
    )
    if not symbols:
        raise ValueError("symbol is required for market trade status.")
    ids = {symbol: instrument_id(asset_class, market, symbol, venue) for symbol in symbols}
    parameters = []
    for row in rows:
        row_symbol = str(row.get("symbol") or row.get("code") or row.get("ts_code") or "").split(".", 1)[0].upper()
        if not row_symbol:
            raise ValueError("symbol is required for market trade status.")
        trade_date = normalize_date(
            row.get("trade_date") or row.get("tradeDate") or row.get("date"),
            "trade_date",
        )
        can_buy = bool_int(row.get("can_buy", row.get("canBuy", True)), default=True)
        can_sell = bool_int(row.get("can_sell", row.get("canSell", True)), default=True)
        is_suspended = bool_int(row.get("is_suspended", row.get("isSuspended", False)))
        parameters.append(
            (
                ids[row_symbol],
                row_symbol,
                asset_class,
                market,
                venue,
                trade_date,
                1 if can_buy or can_sell else 0,
                is_suspended,
                can_buy,
                can_sell,
                optional_float(row.get("limit_up") or row.get("limitUp")),
                optional_float(row.get("limit_down") or row.get("limitDown")),
                bool_int(row.get("is_limit_up", row.get("isLimitUp", False))),
                bool_int(row.get("is_limit_down", row.get("isLimitDown", False))),
                bool_int(row.get("is_one_word_limit_up", row.get("isOneWordLimitUp", False))),
                bool_int(row.get("is_one_word_limit_down", row.get("isOneWordLimitDown", False))),
                bool_int(row.get("is_st", row.get("isSt", False))),
                row.get("status"),
                row.get("reason"),
                source,
                batch_id,
                now,
            )
        )
    with db() as connection:
        connection.executemany(
            """
            insert into instruments
                (instrument_id,symbol,normalized_symbol,name,asset_class,market,venue,status,
                 metadata_json,source,created_at,updated_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(instrument_id) do update set updated_at=excluded.updated_at
            """,
            [
                (
                    ids[item], item, item, item, asset_class, market, venue, "active",
                    json_dump({}), source, now, now,
                )
                for item in symbols
            ],
        )
    prepared = [dict(zip(market_lake.STATUS_COLUMNS, values, strict=True)) for values in parameters]
    result = market_lake.upsert_rows(
        prepared, kind="trade_status", asset_class=asset_class, market=market,
        venue=venue, resolution="daily", data_type="status", adjust="raw", source=source,
    )
    return {"count": len(parameters), "instruments": len(symbols), **result}


def list_instruments(asset_class: str | None = None, market: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    clauses = []
    values: list[Any] = []
    if asset_class:
        clauses.append("asset_class = ?")
        values.append(asset_class.lower())
    if market:
        clauses.append("market = ?")
        values.append(market.lower())
    sql = "select * from instruments"
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by asset_class, market, symbol limit ?"
    values.append(limit)
    with db() as connection:
        rows = connection.execute(sql, values).fetchall()
    return rows_to_dicts(rows)


def get_instrument(symbol: str, *, asset_class: str = "equity", market: str, venue: str | None = None) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from instruments
            where symbol = ? and asset_class = ? and market = ? and venue = ?
            limit 1
            """,
            (symbol.upper(), asset_class.lower(), market.lower(), (venue or market).lower()),
        ).fetchone()
    return row_to_dict(row)


def market_data_coverage(
    symbol: str,
    start: str,
    end: str,
    *,
    asset_class: str = "equity",
    market: str,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str | None = None,
) -> dict[str, Any]:
    selected_source = source or "tushare"
    item = market_lake.aggregate(
        kind="bars", asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=selected_source,
        columns="count(distinct trade_date) as row_count, min(trade_date) as first_date, max(trade_date) as last_date",
        predicates=("symbol = ?", "trade_date between ? and ?"),
        parameters=(symbol.upper(), start, end),
    )
    return {
        "bar_count": int(item.get("row_count") or 0),
        "first_date": item.get("first_date"),
        "last_date": item.get("last_date"),
    }
