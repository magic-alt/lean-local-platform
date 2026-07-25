from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any

from ..core.errors import LeanWebError, NotFoundError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.symbols import parse_date
from .intraday import import_intraday_bars
from .market_repository import upsert_instrument, upsert_market_daily_bars
from .tqsdk_adapter import download_tqsdk_klines, exchange_from_tq_symbol, contract_code_from_tq_symbol


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


def set_fee_schedule(
    *,
    product: str,
    exchange: str,
    open_rate: float = 0,
    close_rate: float = 0,
    close_today_rate: float = 0,
    per_contract: float = 0,
    slippage_ticks: float = 0,
    currency: str = "CNY",
    version: str = "manual-v1",
    source: str = "manual",
) -> dict[str, Any]:
    values = {
        "open_rate": _number(open_rate) or 0.0,
        "close_rate": _number(close_rate) or 0.0,
        "close_today_rate": _number(close_today_rate) or 0.0,
        "per_contract": _number(per_contract) or 0.0,
        "slippage_ticks": _number(slippage_ticks) or 0.0,
    }
    if any(value < 0 for value in values.values()):
        raise LeanWebError("Futures fee rates, per-contract fees, and slippage ticks cannot be negative.")
    product_key = _product(product)
    exchange_key = str(exchange or "").strip().upper()
    if not exchange_key:
        raise LeanWebError("exchange is required.")
    version_key = str(version or "").strip()
    if not version_key:
        raise LeanWebError("A versioned futures fee schedule is required.")
    with db() as connection:
        connection.execute(
            """
            insert into futures_fee_schedules
                (product,exchange,open_rate,close_rate,close_today_rate,per_contract,
                 slippage_ticks,currency,version,source,updated_at)
            values (?,?,?,?,?,?,?,?,?,?,?)
            on conflict(product,exchange) do update set
                open_rate=excluded.open_rate,
                close_rate=excluded.close_rate,
                close_today_rate=excluded.close_today_rate,
                per_contract=excluded.per_contract,
                slippage_ticks=excluded.slippage_ticks,
                currency=excluded.currency,
                version=excluded.version,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                product_key,
                exchange_key,
                values["open_rate"],
                values["close_rate"],
                values["close_today_rate"],
                values["per_contract"],
                values["slippage_ticks"],
                str(currency or "CNY").strip().upper(),
                version_key,
                source,
                utc_now(),
            ),
        )
    return fee_schedule(product_key, exchange_key) or {}


def fee_schedule(product: str, exchange: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from futures_fee_schedules where product=? and exchange=?",
            (_product(product), str(exchange or "").strip().upper()),
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


def refresh_main_mapping(
    *,
    product: str,
    start_date: str,
    end_date: str,
    exchange: str | None = None,
    source: str = "derived",
) -> dict[str, Any]:
    product_key = _product(product)
    start = _date(start_date, "start_date")
    end = _date(end_date, "end_date")
    values: list[Any] = [product_key, start, end]
    exchange_clause = ""
    if exchange:
        exchange_clause = "and c.exchange = ?"
        values.append(str(exchange).strip().upper())
    with db() as connection:
        rows = connection.execute(
            f"""
            select distinct d.trade_date
            from futures_daily_bars d
            join futures_contracts c on c.contract_code = d.contract_code
            where c.product = ? and d.trade_date between ? and ?
              {exchange_clause}
            order by d.trade_date asc
            """,
            values,
        ).fetchall()
    dates = [row["trade_date"] for row in rows]
    batch_id = str(uuid.uuid4())
    now = utc_now()
    inserted = 0
    missing: list[str] = []
    rule = _rule_for(product_key, exchange)
    min_days = max(1, int(rule.get("min_open_interest_days") or 1))
    roll_days = max(0, int(rule.get("roll_days_before_expiry") or 0))
    candidates: list[tuple[str, dict[str, Any]]] = []
    for trade_date in dates:
        item = main_contract(product_key, trade_date, exchange)
        if item:
            candidates.append((trade_date, item))
        else:
            missing.append(trade_date)
    with db() as connection:
        contract_rows = connection.execute(
            "select contract_code,exchange,last_trade_date from futures_contracts where product=?",
            (product_key,),
        ).fetchall()
        bar_rows = connection.execute(
            """
            select distinct d.trade_date,d.contract_code
            from futures_daily_bars d
            join futures_contracts c on c.contract_code=d.contract_code
            where c.product=? and d.trade_date between ? and ?
            """,
            (product_key, start, end),
        ).fetchall()
    contracts_by_code = {row["contract_code"]: dict(row) for row in contract_rows}
    available_bars = {(row["trade_date"], row["contract_code"]) for row in bar_rows}
    stabilized: list[tuple[str, str]] = []
    current: str | None = None
    pending: str | None = None
    pending_days = 0
    for trade_date, item in candidates:
        candidate = str(item["contract_code"])
        if current is None:
            current = candidate
        elif candidate == current:
            pending = None
            pending_days = 0
        else:
            current_meta = contracts_by_code.get(current) or {}
            expiry = _optional_date(current_meta.get("last_trade_date"))
            cutoff = (parse_date(trade_date) + timedelta(days=roll_days)).isoformat()
            forced = bool(expiry and expiry <= cutoff) or (trade_date, current) not in available_bars
            if pending == candidate:
                pending_days += 1
            else:
                pending = candidate
                pending_days = 1
            if forced or pending_days >= min_days:
                current = candidate
                pending = None
                pending_days = 0
        if current is None or (trade_date, current) not in available_bars:
            missing.append(trade_date)
            continue
        stabilized.append((trade_date, current))
    with db() as connection:
        for trade_date, contract_code in stabilized:
            contract_meta = contracts_by_code.get(contract_code) or {}
            exchange_key = str(contract_meta.get("exchange") or exchange or "").upper()
            continuous_symbol = f"KQ.m@{exchange_key}.{product_key.lower()}" if exchange_key else None
            connection.execute(
                """
                insert into futures_main_mapping
                    (product, exchange, trade_date, main_symbol, continuous_symbol, rule,
                     source, batch_id, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(product, exchange, trade_date, source) do update set
                    main_symbol = excluded.main_symbol,
                    continuous_symbol = excluded.continuous_symbol,
                    rule = excluded.rule,
                    batch_id = excluded.batch_id,
                    updated_at = excluded.updated_at
                """,
                (
                    product_key,
                    exchange_key,
                    trade_date,
                    contract_code,
                    continuous_symbol,
                    str(rule.get("rule_type") or "open_interest"),
                    source,
                    batch_id,
                    now,
                ),
            )
            inserted += 1
    return {
        "batchId": batch_id,
        "product": product_key,
        "startDate": start,
        "endDate": end,
        "count": inserted,
        "missing": sorted(set(missing)),
        "rule": rule,
    }


def _latest_contract_close(contract_code: str, trade_date: str) -> float | None:
    with db() as connection:
        row = connection.execute(
            """
            select close from futures_daily_bars
            where contract_code=? and trade_date=? and close is not null
            order by created_at desc limit 1
            """,
            (contract_code, trade_date),
        ).fetchone()
    return float(row["close"]) if row and row["close"] is not None else None


def _transaction_cost(
    *,
    price: float,
    multiplier: float,
    contracts: float,
    rate: float,
    per_contract: float,
    tick_size: float,
    slippage_ticks: float,
) -> tuple[float, float]:
    quantity = abs(contracts)
    commission = quantity * per_contract + quantity * price * multiplier * rate
    slippage = quantity * tick_size * multiplier * slippage_ticks
    return commission, slippage


def _continuous_rows(
    *,
    mapping_batch_id: str,
    contracts: float,
    schedule: dict[str, Any],
    strict_metadata: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    with db() as connection:
        rows = connection.execute(
            """
            select m.trade_date,m.main_symbol,d.open,d.close,d.created_at,
                   c.multiplier,c.margin_rate,c.tick_size
            from futures_main_mapping m
            join futures_contracts c on c.contract_code=m.main_symbol
            join futures_daily_bars d
              on d.contract_code=m.main_symbol and d.trade_date=m.trade_date
            where m.batch_id=?
            order by m.trade_date asc,d.created_at desc
            """,
            (mapping_batch_id,),
        ).fetchall()
    selected: dict[str, dict[str, Any]] = {}
    for item in rows_to_dicts(rows):
        selected.setdefault(item["trade_date"], item)
    series = list(selected.values())
    if not series:
        raise LeanWebError("The main-contract mapping produced no priced continuous-contract rows.")
    output: list[dict[str, Any]] = []
    rolls: list[dict[str, Any]] = []
    cumulative = 0.0
    previous: dict[str, Any] | None = None
    for item in series:
        contract_code = str(item["main_symbol"])
        close = _number(item.get("close"))
        multiplier = _number(item.get("multiplier"))
        margin_rate = _number(item.get("margin_rate"))
        tick_size = _number(item.get("tick_size"))
        missing = [
            field
            for field, value in (
                ("close", close),
                ("multiplier", multiplier),
                ("margin_rate", margin_rate),
                ("tick_size", tick_size),
            )
            if value is None
        ]
        if strict_metadata and missing:
            raise LeanWebError(f"{contract_code} is missing required futures metadata: {', '.join(missing)}.")
        if close is None:
            continue
        multiplier = multiplier or 1.0
        margin_rate = margin_rate or 0.0
        tick_size = tick_size or 0.0
        if strict_metadata and (multiplier <= 0 or margin_rate <= 0 or tick_size <= 0):
            raise LeanWebError(
                f"{contract_code} requires positive multiplier, margin rate, and tick size in strict mode."
            )
        if multiplier <= 0 or margin_rate < 0 or tick_size < 0:
            raise LeanWebError(f"{contract_code} has invalid multiplier, margin rate, or tick size.")
        notional = abs(contracts) * close * multiplier
        is_roll = bool(previous and previous["contract_code"] != contract_code)
        variation_pnl = 0.0
        roll_gap: float | None = None
        roll_yield: float | None = None
        commission = 0.0
        slippage = 0.0
        old_close_today: float | None = None
        if previous is None:
            commission, slippage = _transaction_cost(
                price=close,
                multiplier=multiplier,
                contracts=contracts,
                rate=float(schedule.get("open_rate") or 0),
                per_contract=float(schedule.get("per_contract") or 0),
                tick_size=tick_size,
                slippage_ticks=float(schedule.get("slippage_ticks") or 0),
            )
        elif not is_roll:
            variation_pnl = (
                close - float(previous["raw_close"])
            ) * multiplier * contracts
        else:
            old_close_today = _latest_contract_close(previous["contract_code"], item["trade_date"])
            if old_close_today is None:
                if strict_metadata:
                    raise LeanWebError(
                        f"Cannot attribute roll on {item['trade_date']}: "
                        f"{previous['contract_code']} has no same-day close."
                    )
                old_close_today = float(previous["raw_close"])
            variation_pnl = (
                old_close_today - float(previous["raw_close"])
            ) * float(previous["multiplier"]) * contracts
            roll_gap = close - old_close_today
            roll_yield = (old_close_today - close) / old_close_today if old_close_today else 0.0
            close_commission, close_slippage = _transaction_cost(
                price=old_close_today,
                multiplier=float(previous["multiplier"]),
                contracts=contracts,
                rate=float(schedule.get("close_rate") or 0),
                per_contract=float(schedule.get("per_contract") or 0),
                tick_size=float(previous["tick_size"]),
                slippage_ticks=float(schedule.get("slippage_ticks") or 0),
            )
            open_commission, open_slippage = _transaction_cost(
                price=close,
                multiplier=multiplier,
                contracts=contracts,
                rate=float(schedule.get("open_rate") or 0),
                per_contract=float(schedule.get("per_contract") or 0),
                tick_size=tick_size,
                slippage_ticks=float(schedule.get("slippage_ticks") or 0),
            )
            commission = close_commission + open_commission
            slippage = close_slippage + open_slippage
        net_pnl = variation_pnl - commission - slippage
        cumulative += net_pnl
        row = {
            "trade_date": item["trade_date"],
            "contract_code": contract_code,
            "raw_open": _number(item.get("open")),
            "raw_close": close,
            "multiplier": multiplier,
            "margin_rate": margin_rate,
            "tick_size": tick_size,
            "notional": notional,
            "margin_required": notional * margin_rate,
            "variation_pnl": variation_pnl,
            "commission": commission,
            "slippage": slippage,
            "net_pnl": net_pnl,
            "cumulative_net_pnl": cumulative,
            "is_roll": is_roll,
            "roll_gap": roll_gap,
            "roll_yield": roll_yield,
        }
        if is_roll and previous is not None and old_close_today is not None:
            rolls.append(
                {
                    "trade_date": item["trade_date"],
                    "from_contract": previous["contract_code"],
                    "to_contract": contract_code,
                    "from_price": old_close_today,
                    "to_price": close,
                    "roll_gap": roll_gap or 0.0,
                    "roll_yield": roll_yield or 0.0,
                    "market_pnl": variation_pnl,
                    "commission": commission,
                    "slippage": slippage,
                    "net_pnl": net_pnl,
                }
            )
        output.append(row)
        previous = row
    return output, rolls


def _apply_continuous_adjustment(rows: list[dict[str, Any]], adjustment: str) -> None:
    if adjustment not in {"none", "backward_ratio", "backward_difference"}:
        raise LeanWebError("adjustment must be none, backward_ratio, or backward_difference.")
    ratio = 1.0
    difference = 0.0
    for row in reversed(rows):
        if adjustment == "backward_ratio":
            row["adjustment_factor"] = ratio
            row["adjusted_close"] = row["raw_close"] * ratio
        elif adjustment == "backward_difference":
            row["adjustment_factor"] = difference
            row["adjusted_close"] = row["raw_close"] + difference
        else:
            row["adjustment_factor"] = 1.0
            row["adjusted_close"] = row["raw_close"]
        if row["is_roll"] and row.get("roll_gap") is not None:
            old_price = row["raw_close"] - row["roll_gap"]
            if adjustment == "backward_ratio" and old_price:
                ratio *= row["raw_close"] / old_price
            elif adjustment == "backward_difference":
                difference += row["roll_gap"]


def build_continuous_contract(
    *,
    product: str,
    start_date: str,
    end_date: str,
    exchange: str,
    adjustment: str = "backward_ratio",
    contracts: float = 1.0,
    strict_metadata: bool = True,
) -> dict[str, Any]:
    product_key = _product(product)
    exchange_key = str(exchange or "").strip().upper()
    if not exchange_key:
        raise LeanWebError("exchange is required.")
    start = _date(start_date, "start_date")
    end = _date(end_date, "end_date")
    if start > end:
        raise LeanWebError("start_date cannot be after end_date.")
    contract_count = _number(contracts)
    if contract_count is None or contract_count == 0:
        raise LeanWebError("contracts must be a non-zero finite number.")
    schedule = fee_schedule(product_key, exchange_key)
    if schedule is None:
        if strict_metadata:
            raise LeanWebError(f"No versioned futures fee schedule exists for {product_key}/{exchange_key}.")
        schedule = {
            "version": "unspecified-zero-cost",
            "open_rate": 0,
            "close_rate": 0,
            "close_today_rate": 0,
            "per_contract": 0,
            "slippage_ticks": 0,
            "currency": "CNY",
        }
    mapping = refresh_main_mapping(
        product=product_key,
        exchange=exchange_key,
        start_date=start,
        end_date=end,
        source="continuous-builder",
    )
    rows, rolls = _continuous_rows(
        mapping_batch_id=mapping["batchId"],
        contracts=contract_count,
        schedule=schedule,
        strict_metadata=strict_metadata,
    )
    _apply_continuous_adjustment(rows, adjustment)
    build_id = str(uuid.uuid4())
    summary = {
        "bars": len(rows),
        "rolls": len(rolls),
        "totalVariationPnl": sum(row["variation_pnl"] for row in rows),
        "totalCommission": sum(row["commission"] for row in rows),
        "totalSlippage": sum(row["slippage"] for row in rows),
        "totalNetPnl": sum(row["net_pnl"] for row in rows),
        "maxMarginRequired": max((row["margin_required"] for row in rows), default=0.0),
        "averageMarginRequired": (
            sum(row["margin_required"] for row in rows) / len(rows) if rows else 0.0
        ),
        "cumulativeRollYield": sum(event["roll_yield"] for event in rolls),
    }
    config = {
        "strictMetadata": strict_metadata,
        "feeSchedule": schedule,
        "mappingRule": _rule_for(product_key, exchange_key),
    }
    with db() as connection:
        connection.execute(
            """
            insert into futures_continuous_builds
                (id,product,exchange,start_date,end_date,adjustment,contracts,mapping_batch_id,
                 fee_schedule_version,config_json,summary_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                build_id,
                product_key,
                exchange_key,
                start,
                end,
                adjustment,
                contract_count,
                mapping["batchId"],
                schedule["version"],
                json_dump(config),
                json_dump(summary),
                utc_now(),
            ),
        )
        connection.executemany(
            """
            insert into futures_continuous_bars
                (build_id,trade_date,contract_code,raw_open,raw_close,adjusted_close,
                 adjustment_factor,multiplier,margin_rate,notional,margin_required,
                 variation_pnl,commission,slippage,net_pnl,cumulative_net_pnl,
                 is_roll,roll_gap,roll_yield)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    build_id,
                    row["trade_date"],
                    row["contract_code"],
                    row["raw_open"],
                    row["raw_close"],
                    row["adjusted_close"],
                    row["adjustment_factor"],
                    row["multiplier"],
                    row["margin_rate"],
                    row["notional"],
                    row["margin_required"],
                    row["variation_pnl"],
                    row["commission"],
                    row["slippage"],
                    row["net_pnl"],
                    row["cumulative_net_pnl"],
                    int(row["is_roll"]),
                    row["roll_gap"],
                    row["roll_yield"],
                )
                for row in rows
            ],
        )
        connection.executemany(
            """
            insert into futures_roll_events
                (id,build_id,trade_date,from_contract,to_contract,from_price,to_price,
                 roll_gap,roll_yield,market_pnl,commission,slippage,net_pnl)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    str(uuid.uuid4()),
                    build_id,
                    event["trade_date"],
                    event["from_contract"],
                    event["to_contract"],
                    event["from_price"],
                    event["to_price"],
                    event["roll_gap"],
                    event["roll_yield"],
                    event["market_pnl"],
                    event["commission"],
                    event["slippage"],
                    event["net_pnl"],
                )
                for event in rolls
            ],
        )
    return continuous_contract(build_id)


def continuous_contract(build_id: str) -> dict[str, Any]:
    with db() as connection:
        build = connection.execute(
            "select * from futures_continuous_builds where id=?",
            (build_id,),
        ).fetchone()
        rows = connection.execute(
            "select * from futures_continuous_bars where build_id=? order by trade_date",
            (build_id,),
        ).fetchall()
        rolls = connection.execute(
            "select * from futures_roll_events where build_id=? order by trade_date",
            (build_id,),
        ).fetchall()
    payload = row_to_dict(build)
    if payload is None:
        raise NotFoundError("Futures continuous-contract build not found.")
    payload["bars"] = rows_to_dicts(rows)
    payload["rollEvents"] = rows_to_dicts(rolls)
    return payload


def import_tqsdk_klines(
    *,
    symbols: list[str],
    start_date: str,
    end_date: str,
    duration_seconds: int = 86400,
    tq_account: str | None = None,
    tq_password: str | None = None,
) -> dict[str, Any]:
    imports: list[dict[str, Any]] = []
    for symbol in symbols:
        rows = download_tqsdk_klines(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            duration_seconds=duration_seconds,
            tq_account=tq_account,
            tq_password=tq_password,
        )
        contract_code = contract_code_from_tq_symbol(symbol)
        exchange = exchange_from_tq_symbol(symbol) or "future"
        product = _infer_product(contract_code)
        import_contracts(
            [
                {
                    "contract_code": contract_code,
                    "product": product,
                    "exchange": exchange,
                    "source": "tqsdk",
                }
            ],
            source="tqsdk",
        )
        if duration_seconds >= 86400:
            daily_rows = [
                {
                    "contract_code": row["contract_code"],
                    "trade_date": row["trade_date"],
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "open_interest": row.get("open_interest"),
                }
                for row in rows
            ]
            result = import_daily_bars(daily_rows, source="tqsdk")
        else:
            result = import_intraday_bars(
                rows,
                symbol=contract_code,
                asset_class="future",
                market="future",
                venue=exchange,
                frequency=f"{int(duration_seconds // 60)}m",
                source="tqsdk",
            )
        imports.append({"symbol": symbol, "contractCode": contract_code, "exchange": exchange, "rows": len(rows), "result": result})
    return {"count": len(imports), "imports": imports}
