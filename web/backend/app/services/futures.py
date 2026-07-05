from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..lean import parse_date
from .market_repository import upsert_instrument, upsert_market_daily_bars


DEFAULT_AGRI_PRODUCTS = [
    "A",
    "M",
    "Y",
    "P",
    "C",
    "CS",
    "JD",
    "LH",
    "SR",
    "CF",
    "RM",
    "OI",
    "AP",
    "CJ",
    "PK",
]


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


def _contract_code(value: Any) -> str:
    code = str(value).strip().upper().replace(".", "")
    if not code or not code.isalnum():
        raise LeanWebError("Invalid futures contract_code.")
    return code


def _product(value: Any) -> str:
    product = str(value).strip().upper()
    if not product or not product.isalpha():
        raise LeanWebError("Invalid futures product.")
    return product


def _infer_product(contract_code: str) -> str:
    letters = []
    for char in contract_code.upper():
        if char.isalpha():
            letters.append(char)
        else:
            break
    return _product("".join(letters))


def import_contracts(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    now = utc_now()
    count = 0
    instruments: list[dict[str, Any]] = []
    with db() as connection:
        for record in records:
            contract_code = _contract_code(record.get("contract_code") or record.get("contractCode"))
            product = _product(record.get("product") or _infer_product(contract_code))
            exchange = str(record.get("exchange") or "DCE").strip().upper()
            listed_date = _optional_date(record.get("listed_date") or record.get("listedDate"))
            last_trade_date = _optional_date(record.get("last_trade_date") or record.get("lastTradeDate"))
            multiplier = _number(record.get("multiplier"))
            margin_rate = _number(record.get("margin_rate") or record.get("marginRate"))
            tick_size = _number(record.get("tick_size") or record.get("tickSize"))
            connection.execute(
                """
                insert into futures_contracts
                    (contract_code, product, exchange, name, multiplier, margin_rate, tick_size,
                     delivery_month, listed_date, last_trade_date, source, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(contract_code) do update set
                    product = excluded.product,
                    exchange = excluded.exchange,
                    name = excluded.name,
                    multiplier = excluded.multiplier,
                    margin_rate = excluded.margin_rate,
                    tick_size = excluded.tick_size,
                    delivery_month = excluded.delivery_month,
                    listed_date = excluded.listed_date,
                    last_trade_date = excluded.last_trade_date,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    contract_code,
                    product,
                    exchange,
                    record.get("name") or contract_code,
                    multiplier,
                    margin_rate,
                    tick_size,
                    record.get("delivery_month") or record.get("deliveryMonth"),
                    listed_date,
                    last_trade_date,
                    record.get("source") or source,
                    now,
                ),
            )
            count += 1
            instruments.append(
                {
                    "symbol": contract_code,
                    "name": record.get("name") or contract_code,
                    "asset_class": "future",
                    "market": "future",
                    "venue": exchange,
                    "exchange": exchange,
                    "underlying_symbol": product,
                    "listed_date": listed_date,
                    "expiry_date": last_trade_date,
                    "status": "active",
                    "contract_multiplier": multiplier,
                    "margin_rate": margin_rate,
                    "tick_size": tick_size,
                    "metadata": {"product": product, "delivery_month": record.get("delivery_month") or record.get("deliveryMonth")},
                    "source": record.get("source") or source,
                }
            )
    for instrument in instruments:
        upsert_instrument(**instrument)
    return {"count": count}


def import_daily_bars(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    now = utc_now()
    count = 0
    with db() as connection:
        for record in records:
            contract_code = _contract_code(record.get("contract_code") or record.get("contractCode"))
            low = _number(record.get("low"))
            high = _number(record.get("high"))
            if high is not None and low is not None and high < low:
                raise LeanWebError("Futures high cannot be lower than low.")
            connection.execute(
                """
                insert into futures_daily_bars
                    (contract_code, trade_date, open, high, low, close, volume, open_interest,
                     source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(contract_code, trade_date, source) do update set
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    open_interest = excluded.open_interest,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    contract_code,
                    _date(record.get("trade_date") or record.get("tradeDate"), "trade_date"),
                    _number(record.get("open")),
                    high,
                    low,
                    _number(record.get("close")),
                    _number(record.get("volume")),
                    _number(record.get("open_interest") or record.get("openInterest")),
                    record.get("source") or source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    grouped: dict[str, list[dict[str, Any]]] = {}
    contract_exchanges: dict[str, str] = {}
    with db() as connection:
        contract_rows = connection.execute("select contract_code, exchange from futures_contracts").fetchall()
    for item in rows_to_dicts(contract_rows):
        contract_exchanges[item["contract_code"]] = item.get("exchange") or "future"
    for record in records:
        contract_code = _contract_code(record.get("contract_code") or record.get("contractCode"))
        grouped.setdefault(contract_code, []).append(
            {
                "symbol": contract_code,
                "trade_date": _date(record.get("trade_date") or record.get("tradeDate"), "trade_date"),
                "open": _number(record.get("open")),
                "high": _number(record.get("high")),
                "low": _number(record.get("low")),
                "close": _number(record.get("close")),
                "volume": _number(record.get("volume")),
                "open_interest": _number(record.get("open_interest") or record.get("openInterest")),
            }
        )
    for contract_code, symbol_rows in grouped.items():
        upsert_market_daily_bars(
            symbol_rows,
            symbol=contract_code,
            asset_class="future",
            market="future",
            venue=contract_exchanges.get(contract_code) or "future",
            source=source,
            batch_id=batch_id,
        )
    return {"batchId": batch_id, "count": count}


def set_main_rule(
    *,
    product: str,
    exchange: str,
    rule_type: str = "open_interest",
    roll_days_before_expiry: int = 0,
    min_open_interest_days: int = 1,
    source: str = "manual",
) -> dict[str, Any]:
    product_key = _product(product)
    exchange_key = str(exchange).strip().upper()
    rule = rule_type.strip().lower()
    if rule not in {"open_interest", "volume"}:
        raise LeanWebError("rule_type must be open_interest or volume.")
    with db() as connection:
        connection.execute(
            """
            insert into futures_main_rules
                (product, exchange, rule_type, roll_days_before_expiry,
                 min_open_interest_days, source, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(product, exchange) do update set
                rule_type = excluded.rule_type,
                roll_days_before_expiry = excluded.roll_days_before_expiry,
                min_open_interest_days = excluded.min_open_interest_days,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                product_key,
                exchange_key,
                rule,
                max(0, int(roll_days_before_expiry)),
                max(1, int(min_open_interest_days)),
                source,
                utc_now(),
            ),
        )
    return main_rule(product_key, exchange_key) or {}


def main_rule(product: str, exchange: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from futures_main_rules where product = ? and exchange = ?",
            (_product(product), str(exchange).strip().upper()),
        ).fetchone()
    return row_to_dict(row)


def _rule_for(product: str, exchange: str | None) -> dict[str, Any]:
    if exchange:
        rule = main_rule(product, exchange)
        if rule:
            return rule
    with db() as connection:
        row = connection.execute(
            "select * from futures_main_rules where product = ? order by updated_at desc limit 1",
            (_product(product),),
        ).fetchone()
    return row_to_dict(row) or {
        "product": _product(product),
        "exchange": str(exchange or "").upper() or None,
        "rule_type": "open_interest",
        "roll_days_before_expiry": 0,
        "min_open_interest_days": 1,
    }


def _with_days_to_expiry(item: dict[str, Any], as_of: str) -> dict[str, Any]:
    if item.get("last_trade_date"):
        item["daysToExpiry"] = (parse_date(item["last_trade_date"]) - parse_date(as_of)).days
    else:
        item["daysToExpiry"] = None
    return item


def main_contract(product: str, as_of_date: str, exchange: str | None = None) -> dict[str, Any] | None:
    product_key = _product(product)
    as_of = _date(as_of_date, "as_of_date")
    rule = _rule_for(product_key, exchange)
    roll_cutoff = (parse_date(as_of) + timedelta(days=int(rule.get("roll_days_before_expiry") or 0))).isoformat()
    values: list[Any] = [as_of, product_key, as_of, roll_cutoff]
    exchange_clause = ""
    if exchange:
        exchange_clause = "and c.exchange = ?"
        values.append(str(exchange).strip().upper())
    with db() as connection:
        rows = connection.execute(
            f"""
            select c.*, d.trade_date as bar_date, d.open, d.high, d.low, d.close,
                   d.volume, d.open_interest
            from futures_contracts c
            join (
                select contract_code, max(trade_date) as trade_date
                from futures_daily_bars
                where trade_date <= ?
                group by contract_code
            ) latest on latest.contract_code = c.contract_code
            join futures_daily_bars d
              on d.contract_code = latest.contract_code and d.trade_date = latest.trade_date
            where c.product = ?
              and (c.listed_date is null or c.listed_date <= ?)
              and (c.last_trade_date is null or c.last_trade_date >= ?)
              {exchange_clause}
            """,
            values,
        ).fetchall()
    candidates = [_with_days_to_expiry(item, as_of) for item in rows_to_dicts(rows)]
    if not candidates:
        return None
    key_name = "volume" if rule.get("rule_type") == "volume" else "open_interest"
    candidates.sort(
        key=lambda item: (
            float(item.get(key_name) or 0),
            float(item.get("volume") or 0),
            item.get("contract_code") or "",
        ),
        reverse=True,
    )
    winner = candidates[0]
    winner["asOfDate"] = as_of
    winner["rule"] = rule
    return winner


def agri_main_monitor(as_of_date: str, products: list[str] | None = None) -> dict[str, Any]:
    as_of = _date(as_of_date, "as_of_date")
    requested = [_product(item) for item in (products or DEFAULT_AGRI_PRODUCTS)]
    items = []
    missing = []
    for product in requested:
        contract = main_contract(product, as_of)
        if contract:
            items.append(contract)
        else:
            missing.append(product)
    return {"asOfDate": as_of, "count": len(items), "missing": missing, "items": items}
