from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..db import db, json_dump, rows_to_dicts, utc_now


INSTRUMENT_NAMESPACE = uuid.UUID("ed487062-bcf1-47c6-8f1a-1973b5f9edb0")


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
        return float(value)
    except (TypeError, ValueError):
        return None


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
                name = coalesce(excluded.name, instruments.name),
                exchange = coalesce(excluded.exchange, instruments.exchange),
                venue = excluded.venue,
                currency = coalesce(excluded.currency, instruments.currency),
                base_currency = coalesce(excluded.base_currency, instruments.base_currency),
                quote_currency = coalesce(excluded.quote_currency, instruments.quote_currency),
                underlying_symbol = coalesce(excluded.underlying_symbol, instruments.underlying_symbol),
                listed_date = coalesce(excluded.listed_date, instruments.listed_date),
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
) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    first_symbol = symbol or str(rows[0].get("symbol") or rows[0].get("code") or rows[0].get("ts_code") or "").upper()
    if not first_symbol:
        raise ValueError("symbol is required for market_daily_bars.")
    item_id = upsert_instrument(
        symbol=first_symbol,
        asset_class=asset_class,
        market=market,
        venue=venue or market,
        source=source,
        status="active",
    )
    now = utc_now()
    count = 0
    with db() as connection:
        for row in rows:
            trade_date = normalize_date(row.get("trade_date") or row.get("tradeDate") or row.get("date") or row.get("timestamp"), "trade_date")
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                     open, high, low, close, settle, volume, amount, turnover_rate, open_interest,
                     prev_close, pct_change, adjust, adj_factor, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(instrument_id, trade_date, resolution, data_type, adjust, source) do update set
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    settle = excluded.settle,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    turnover_rate = excluded.turnover_rate,
                    open_interest = excluded.open_interest,
                    prev_close = excluded.prev_close,
                    pct_change = excluded.pct_change,
                    adj_factor = excluded.adj_factor,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    item_id,
                    first_symbol,
                    asset_class.lower(),
                    market.lower(),
                    (venue or market).lower(),
                    trade_date,
                    resolution,
                    data_type,
                    optional_float(row.get("open")),
                    optional_float(row.get("high")),
                    optional_float(row.get("low")),
                    optional_float(row.get("close")),
                    optional_float(row.get("settle") or row.get("settle_price")),
                    optional_float(row.get("volume")),
                    optional_float(row.get("amount")),
                    optional_float(row.get("turnover_rate") or row.get("turnoverRate")),
                    optional_float(row.get("open_interest") or row.get("openInterest")),
                    optional_float(row.get("prev_close") or row.get("pre_close") or row.get("prevClose")),
                    optional_float(row.get("pct_change") or row.get("pctChange")),
                    adjust or "raw",
                    optional_float(row.get("adj_factor") or row.get("adjFactor")),
                    source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    return {"instrumentId": item_id, "count": count}


def upsert_market_trade_status(
    rows: list[dict[str, Any]],
    *,
    symbol: str,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    source: str,
    batch_id: str | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    item_id = upsert_instrument(symbol=symbol, asset_class=asset_class, market=market, venue=venue or market, source=source)
    now = utc_now()
    count = 0
    with db() as connection:
        for row in rows:
            trade_date = normalize_date(row.get("trade_date") or row.get("tradeDate") or row.get("date"), "trade_date")
            can_buy = bool_int(row.get("can_buy", row.get("canBuy", True)), default=True)
            can_sell = bool_int(row.get("can_sell", row.get("canSell", True)), default=True)
            is_suspended = bool_int(row.get("is_suspended", row.get("isSuspended", False)))
            connection.execute(
                """
                insert into market_trade_status
                    (instrument_id, symbol, asset_class, market, venue, trade_date, is_tradeable, is_suspended,
                     can_buy, can_sell, limit_up, limit_down, status, reason, source, batch_id, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(instrument_id, trade_date, source) do update set
                    is_tradeable = excluded.is_tradeable,
                    is_suspended = excluded.is_suspended,
                    can_buy = excluded.can_buy,
                    can_sell = excluded.can_sell,
                    limit_up = excluded.limit_up,
                    limit_down = excluded.limit_down,
                    status = excluded.status,
                    reason = excluded.reason,
                    batch_id = excluded.batch_id,
                    updated_at = excluded.updated_at
                """,
                (
                    item_id,
                    symbol,
                    asset_class.lower(),
                    market.lower(),
                    (venue or market).lower(),
                    trade_date,
                    1 if can_buy or can_sell else 0,
                    is_suspended,
                    can_buy,
                    can_sell,
                    optional_float(row.get("limit_up") or row.get("limitUp")),
                    optional_float(row.get("limit_down") or row.get("limitDown")),
                    row.get("status"),
                    row.get("reason"),
                    source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    return {"instrumentId": item_id, "count": count}


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
