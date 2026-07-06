from __future__ import annotations

import math
import uuid
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, json_dump, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol, parse_date
from .market_repository import upsert_instrument, upsert_market_daily_bars


INACTIVE_CALL_STATUSES = {"cancelled", "expired", "withdrawn", "completed"}


def _date(value: Any, field: str) -> str:
    if value in (None, ""):
        raise LeanWebError(f"{field} is required.")
    return parse_date(str(value)[:10]).isoformat()


def _optional_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return parse_date(str(value)[:10]).isoformat()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if not math.isfinite(number):
        raise LeanWebError("Numeric values must be finite.")
    return number


def _bond_code(value: Any) -> str:
    code = str(value).strip().upper().replace(".", "")
    if not code:
        raise LeanWebError("bond_code is required.")
    return code


def _stock_symbol(value: Any) -> str:
    return normalize_symbol(str(value), "china").upper()


def _premium_decimal(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 2 else number


def import_cbond_terms(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    now = utc_now()
    count = 0
    instruments: list[dict[str, Any]] = []
    with db() as connection:
        for record in records:
            bond_code = _bond_code(record.get("bond_code") or record.get("bondCode"))
            stock_symbol = _stock_symbol(record.get("stock_symbol") or record.get("stockSymbol"))
            bond_name = str(record.get("bond_name") or record.get("bondName") or bond_code)
            listed_date = _optional_date(record.get("listed_date") or record.get("listedDate"))
            delisted_date = _optional_date(record.get("delisted_date") or record.get("delistedDate"))
            maturity_date = _optional_date(record.get("maturity_date") or record.get("maturityDate"))
            connection.execute(
                """
                insert into cbond_securities
                    (bond_code, bond_name, stock_symbol, listed_date, delisted_date, maturity_date,
                     rating, conversion_price, issue_size, remaining_size, terms_json, source, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(bond_code) do update set
                    bond_name = excluded.bond_name,
                    stock_symbol = excluded.stock_symbol,
                    listed_date = excluded.listed_date,
                    delisted_date = excluded.delisted_date,
                    maturity_date = excluded.maturity_date,
                    rating = excluded.rating,
                    conversion_price = excluded.conversion_price,
                    issue_size = excluded.issue_size,
                    remaining_size = excluded.remaining_size,
                    terms_json = excluded.terms_json,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    bond_code,
                    bond_name,
                    stock_symbol,
                    listed_date,
                    delisted_date,
                    maturity_date,
                    record.get("rating"),
                    _number(record.get("conversion_price") or record.get("conversionPrice")),
                    _number(record.get("issue_size") or record.get("issueSize")),
                    _number(record.get("remaining_size") or record.get("remainingSize")),
                    json_dump(record.get("terms") or {}),
                    record.get("source") or source,
                    now,
                ),
            )
            count += 1
            instruments.append(
                {
                    "symbol": bond_code,
                    "name": bond_name,
                    "asset_class": "cbond",
                    "market": "china",
                    "venue": "china",
                    "exchange": None,
                    "currency": "CNY",
                    "underlying_symbol": stock_symbol,
                    "listed_date": listed_date,
                    "delisted_date": delisted_date,
                    "expiry_date": maturity_date,
                    "status": "active",
                    "metadata": {"rating": record.get("rating"), "terms": record.get("terms") or {}},
                    "source": record.get("source") or source,
                }
            )
    for instrument in instruments:
        upsert_instrument(**instrument)
    return {"count": count}


def _term_conversion_price(bond_code: str) -> float | None:
    with db() as connection:
        row = connection.execute(
            "select conversion_price from cbond_securities where bond_code = ?",
            (bond_code,),
        ).fetchone()
    return float(row["conversion_price"]) if row and row["conversion_price"] is not None else None


def import_cbond_daily(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    now = utc_now()
    count = 0
    with db() as connection:
        for record in records:
            bond_code = _bond_code(record.get("bond_code") or record.get("bondCode"))
            trade_date = _date(record.get("trade_date") or record.get("tradeDate"), "trade_date")
            close = _number(record.get("close"))
            if close is None or close <= 0:
                raise LeanWebError("cbond close must be positive.")
            conversion_price = _number(record.get("conversion_price") or record.get("conversionPrice"))
            if conversion_price is None:
                conversion_price = _term_conversion_price(bond_code)
            stock_close = _number(record.get("stock_close") or record.get("stockClose"))
            conversion_value = _number(record.get("conversion_value") or record.get("conversionValue"))
            if conversion_value is None and stock_close is not None and conversion_price and conversion_price > 0:
                conversion_value = stock_close / conversion_price * 100.0
            premium_rate = _premium_decimal(record.get("premium_rate") or record.get("premiumRate"))
            if premium_rate is None and conversion_value and conversion_value > 0:
                premium_rate = close / conversion_value - 1.0
            double_low = _number(record.get("double_low") or record.get("doubleLow"))
            if double_low is None and premium_rate is not None:
                double_low = close + premium_rate * 100.0
            remaining_size = _number(record.get("remaining_size") or record.get("remainingSize"))
            connection.execute(
                """
                insert into cbond_daily_bars
                    (bond_code, trade_date, close, stock_close, conversion_price, conversion_value,
                     premium_rate, remaining_size, double_low, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(bond_code, trade_date, source) do update set
                    close = excluded.close,
                    stock_close = excluded.stock_close,
                    conversion_price = excluded.conversion_price,
                    conversion_value = excluded.conversion_value,
                    premium_rate = excluded.premium_rate,
                    remaining_size = excluded.remaining_size,
                    double_low = excluded.double_low,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    bond_code,
                    trade_date,
                    close,
                    stock_close,
                    conversion_price,
                    conversion_value,
                    premium_rate,
                    remaining_size,
                    double_low,
                    record.get("source") or source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        bond_code = _bond_code(record.get("bond_code") or record.get("bondCode"))
        grouped.setdefault(bond_code, []).append(
            {
                "symbol": bond_code,
                "trade_date": _date(record.get("trade_date") or record.get("tradeDate"), "trade_date"),
                "open": record.get("open") or record.get("close"),
                "high": record.get("high") or record.get("close"),
                "low": record.get("low") or record.get("close"),
                "close": record.get("close"),
                "volume": record.get("volume"),
                "amount": record.get("amount"),
            }
        )
    for bond_code, symbol_rows in grouped.items():
        upsert_market_daily_bars(
            symbol_rows,
            symbol=bond_code,
            asset_class="cbond",
            market="china",
            venue="china",
            source=source,
            batch_id=batch_id,
        )
    return {"batchId": batch_id, "count": count}


def import_call_events(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    now = utc_now()
    count = 0
    with db() as connection:
        for record in records:
            event_id = str(record.get("id") or uuid.uuid4())
            connection.execute(
                """
                insert into cbond_call_events
                    (id, bond_code, announce_date, trigger_date, status, call_price,
                     last_trade_date, source, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    bond_code = excluded.bond_code,
                    announce_date = excluded.announce_date,
                    trigger_date = excluded.trigger_date,
                    status = excluded.status,
                    call_price = excluded.call_price,
                    last_trade_date = excluded.last_trade_date,
                    source = excluded.source,
                    created_at = excluded.created_at
                """,
                (
                    event_id,
                    _bond_code(record.get("bond_code") or record.get("bondCode")),
                    _date(record.get("announce_date") or record.get("announceDate"), "announce_date"),
                    _optional_date(record.get("trigger_date") or record.get("triggerDate")),
                    str(record.get("status") or "announced").strip().lower(),
                    _number(record.get("call_price") or record.get("callPrice")),
                    _optional_date(record.get("last_trade_date") or record.get("lastTradeDate")),
                    record.get("source") or source,
                    now,
                ),
            )
            count += 1
    return {"count": count}


def call_risk_codes(as_of_date: str) -> set[str]:
    as_of = _date(as_of_date, "as_of_date")
    with db() as connection:
        rows = connection.execute(
            """
            select distinct bond_code, status from cbond_call_events
            where announce_date <= ?
              and (last_trade_date is null or last_trade_date >= ?)
            """,
            (as_of, as_of),
        ).fetchall()
    return {
        row["bond_code"]
        for row in rows
        if str(row["bond_code"]) and str(row["status"] or "").lower() not in INACTIVE_CALL_STATUSES
    }


def call_risk_monitor(as_of_date: str) -> dict[str, Any]:
    as_of = _date(as_of_date, "as_of_date")
    with db() as connection:
        rows = connection.execute(
            """
            select e.*, s.bond_name, s.stock_symbol, s.maturity_date, s.rating
            from cbond_call_events e
            left join cbond_securities s on s.bond_code = e.bond_code
            where e.announce_date <= ?
              and (e.last_trade_date is null or e.last_trade_date >= ?)
            order by e.announce_date desc, e.bond_code asc
            """,
            (as_of, as_of),
        ).fetchall()
    items = [
        item for item in rows_to_dicts(rows)
        if str(item.get("status") or "").lower() not in INACTIVE_CALL_STATUSES
    ]
    return {"asOfDate": as_of, "count": len(items), "items": items}


def double_low_pool(
    *,
    as_of_date: str,
    max_double_low: float = 130.0,
    exclude_call_risk: bool = True,
    limit: int = 100,
) -> dict[str, Any]:
    as_of = _date(as_of_date, "as_of_date")
    bounded_limit = max(1, min(int(limit), 1000))
    with db() as connection:
        rows = connection.execute(
            """
            select d.*, s.bond_name, s.stock_symbol, s.maturity_date, s.rating,
                   coalesce(d.remaining_size, s.remaining_size) as current_remaining_size
            from cbond_daily_bars d
            join (
                select bond_code, max(trade_date) as trade_date
                from cbond_daily_bars
                where trade_date <= ?
                group by bond_code
            ) latest on latest.bond_code = d.bond_code and latest.trade_date = d.trade_date
            left join cbond_securities s on s.bond_code = d.bond_code
            where d.double_low is not null and d.double_low <= ?
              and (s.delisted_date is null or s.delisted_date > ?)
            order by d.double_low asc, d.close asc
            limit ?
            """,
            (as_of, max_double_low, as_of, bounded_limit),
        ).fetchall()
    risk_codes = call_risk_codes(as_of) if exclude_call_risk else set()
    items = [
        item for item in rows_to_dicts(rows)
        if item["bond_code"] not in risk_codes
    ]
    return {
        "asOfDate": as_of,
        "maxDoubleLow": max_double_low,
        "excludeCallRisk": exclude_call_risk,
        "count": len(items),
        "items": items,
    }
