from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def _date(value: Any, field: str = "date") -> str:
    if value in (None, ""):
        raise LeanWebError(f"{field} is required.")
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text if fmt == "%Y-%m-%d" else str(value).strip()[:8], fmt).date().isoformat()
        except ValueError:
            pass
    raise LeanWebError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD or YYYYMMDD.")


def _optional_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return _date(value)


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(value: Any) -> str:
    raw = str(value or "listed").strip().lower()
    aliases = {
        "l": "listed",
        "list": "listed",
        "上市": "listed",
        "normal": "listed",
        "d": "delisted",
        "delist": "delisted",
        "退市": "delisted",
        "p": "pending",
        "pending": "pending",
        "暂停上市": "suspended",
        "s": "suspended",
    }
    return aliases.get(raw, raw or "listed")


def _symbol(record: dict[str, Any]) -> str:
    raw = record.get("symbol") or record.get("ts_code") or record.get("code")
    if raw in (None, ""):
        raise LeanWebError("symbol is required.")
    value = str(raw).strip().upper()
    if "." in value:
        value = value.split(".")[0]
    if not value.isdigit() or len(value) != 6:
        raise LeanWebError(f"A-share symbol must be 6 digits: {raw!r}.")
    return value


def infer_exchange(symbol: str) -> str:
    value = symbol.strip()
    if value.startswith(("6", "9")):
        return "SSE"
    if value.startswith(("4", "8")):
        return "BSE"
    return "SZSE"


def import_security_master(
    records: list[dict[str, Any]],
    *,
    source: str = "manual",
    universe_code: str = "ALL_A",
) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    imported = 0
    for record in records:
        symbol = _symbol(record)
        listed_date = _date(record.get("listed_date") or record.get("list_date") or record.get("listDate"), "listed_date")
        delisted_date = _optional_date(record.get("delisted_date") or record.get("delist_date") or record.get("delistDate"))
        status = _status(record.get("status") or record.get("list_status"))
        if delisted_date and status == "listed":
            status = "delisted"
        upsert_security(
            symbol=symbol,
            name=record.get("name") or record.get("symbol_name") or record.get("stock_name") or symbol,
            exchange=record.get("exchange") or record.get("exchange_code") or infer_exchange(symbol),
            listed_date=listed_date,
            delisted_date=delisted_date,
            status=status,
            is_st=bool(record.get("is_st", False)),
            industry=record.get("industry"),
            concepts=record.get("concepts") if isinstance(record.get("concepts"), list) else None,
        )
        upsert_universe_membership(
            universe_code.upper(),
            symbol,
            listed_date,
            delisted_date,
            source=record.get("source") or source,
            batch_id=batch_id,
            announce_date=_optional_date(record.get("announce_date") or record.get("announceDate")) or listed_date,
            effective_date=_optional_date(record.get("effective_date") or record.get("effectiveDate")) or listed_date,
        )
        imported += 1
    return {"batchId": batch_id, "universe": universe_code.upper(), "count": imported}


def create_import_batch(provider: str, market: str, asset_class: str, config: dict[str, Any]) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    with db() as connection:
        connection.execute(
            """
            insert into data_import_batches
                (id, provider, market, asset_class, status, config_json, started_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (batch_id, provider, market, asset_class, "running", json_dump(config), utc_now()),
        )
    return get_import_batch(batch_id) or {}


def finish_import_batch(batch_id: str, status: str, qa_report: dict[str, Any] | None = None, error: str | None = None) -> None:
    with db() as connection:
        connection.execute(
            """
            update data_import_batches
            set status = ?, qa_report_json = ?, error = ?, finished_at = ?
            where id = ?
            """,
            (status, json_dump(qa_report or {}), error, utc_now(), batch_id),
        )


def list_import_batches() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from data_import_batches order by started_at desc").fetchall()
    return rows_to_dicts(rows)


def get_import_batch(batch_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from data_import_batches where id = ?", (batch_id,)).fetchone()
    return row_to_dict(row)


def upsert_security(
    *,
    symbol: str,
    name: str | None = None,
    exchange: str | None = None,
    listed_date: str,
    delisted_date: str | None = None,
    status: str = "listed",
    is_st: bool = False,
    industry: str | None = None,
    concepts: list[str] | None = None,
) -> None:
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into securities
                (symbol, name, exchange, market, listed_date, delisted_date, status, is_st,
                 industry, concepts_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol) do update set
                name = excluded.name,
                exchange = excluded.exchange,
                listed_date = min(securities.listed_date, excluded.listed_date),
                delisted_date = excluded.delisted_date,
                status = excluded.status,
                is_st = excluded.is_st,
                industry = coalesce(excluded.industry, securities.industry),
                concepts_json = coalesce(excluded.concepts_json, securities.concepts_json),
                updated_at = excluded.updated_at
            """,
            (
                symbol,
                name or symbol,
                exchange or infer_exchange(symbol),
                "china",
                listed_date,
                delisted_date,
                status,
                _bool(is_st),
                industry,
                json_dump(concepts or []),
                now,
                now,
            ),
        )


def get_security(symbol: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from securities where symbol = ?", (symbol,)).fetchone()
    return row_to_dict(row)


def upsert_trade_calendar(market: str, trade_dates: list[str], source: str, batch_id: str | None = None) -> None:
    unique_dates = sorted(set(trade_dates))
    with db() as connection:
        for index, trade_date in enumerate(unique_dates):
            prev_date = unique_dates[index - 1] if index > 0 else None
            next_date = unique_dates[index + 1] if index + 1 < len(unique_dates) else None
            connection.execute(
                """
                insert into trade_calendar
                    (market, trade_date, is_open, prev_trade_date, next_trade_date, source, batch_id)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(market, trade_date) do update set
                    is_open = excluded.is_open,
                    prev_trade_date = coalesce(excluded.prev_trade_date, trade_calendar.prev_trade_date),
                    next_trade_date = coalesce(excluded.next_trade_date, trade_calendar.next_trade_date),
                    source = excluded.source,
                    batch_id = excluded.batch_id
                """,
                (market, trade_date, 1, prev_date, next_date, source, batch_id),
            )


def trade_dates_between(market: str, start: str, end: str) -> list[str]:
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date from trade_calendar
            where market = ? and is_open = 1 and trade_date >= ? and trade_date <= ?
            order by trade_date asc
            """,
            (market, start, end),
        ).fetchall()
    return [row["trade_date"] for row in rows]


def upsert_daily_bars(rows: list[dict[str, Any]], source: str, batch_id: str, adjust: str) -> None:
    now = utc_now()
    with db() as connection:
        for row in rows:
            connection.execute(
                """
                insert into ashare_daily_bars
                    (symbol, trade_date, open, high, low, close, volume, amount, turnover_rate,
                     prev_close, pct_change, adj_factor, adjust, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, trade_date, adjust, source) do update set
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    turnover_rate = excluded.turnover_rate,
                    prev_close = excluded.prev_close,
                    pct_change = excluded.pct_change,
                    adj_factor = excluded.adj_factor,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    row["symbol"],
                    row["trade_date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row.get("amount"),
                    row.get("turnover_rate"),
                    row.get("prev_close"),
                    row.get("pct_change"),
                    row.get("adj_factor"),
                    adjust,
                    source,
                    batch_id,
                    now,
                ),
            )


def upsert_trade_status(rows: list[dict[str, Any]], source: str, batch_id: str) -> None:
    with db() as connection:
        for row in rows:
            connection.execute(
                """
                insert into ashare_trade_status
                    (symbol, trade_date, is_suspended, limit_up, limit_down, is_limit_up, is_limit_down,
                     is_one_word_limit_up, is_one_word_limit_down, can_buy, can_sell, is_st, source, batch_id)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, trade_date) do update set
                    is_suspended = excluded.is_suspended,
                    limit_up = excluded.limit_up,
                    limit_down = excluded.limit_down,
                    is_limit_up = excluded.is_limit_up,
                    is_limit_down = excluded.is_limit_down,
                    is_one_word_limit_up = excluded.is_one_word_limit_up,
                    is_one_word_limit_down = excluded.is_one_word_limit_down,
                    can_buy = excluded.can_buy,
                    can_sell = excluded.can_sell,
                    is_st = excluded.is_st,
                    source = excluded.source,
                    batch_id = excluded.batch_id
                """,
                (
                    row["symbol"],
                    row["trade_date"],
                    _bool(row.get("is_suspended")),
                    row.get("limit_up"),
                    row.get("limit_down"),
                    _bool(row.get("is_limit_up")),
                    _bool(row.get("is_limit_down")),
                    _bool(row.get("is_one_word_limit_up")),
                    _bool(row.get("is_one_word_limit_down")),
                    _bool(row.get("can_buy", True)),
                    _bool(row.get("can_sell", True)),
                    _bool(row.get("is_st")),
                    source,
                    batch_id,
                ),
            )


def import_trade_status(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    rows = []
    for record in records:
        symbol = _symbol(record)
        trade_date = _date(record.get("trade_date") or record.get("tradeDate"), "trade_date")
        is_suspended = bool(record.get("is_suspended", record.get("isSuspended", False)))
        is_limit_up = bool(record.get("is_limit_up", record.get("isLimitUp", False)))
        is_limit_down = bool(record.get("is_limit_down", record.get("isLimitDown", False)))
        can_buy = record.get("can_buy", record.get("canBuy"))
        can_sell = record.get("can_sell", record.get("canSell"))
        rows.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "is_suspended": is_suspended,
                "limit_up": _float(record.get("limit_up") or record.get("limitUp")),
                "limit_down": _float(record.get("limit_down") or record.get("limitDown")),
                "is_limit_up": is_limit_up,
                "is_limit_down": is_limit_down,
                "is_one_word_limit_up": bool(record.get("is_one_word_limit_up", record.get("isOneWordLimitUp", False))),
                "is_one_word_limit_down": bool(record.get("is_one_word_limit_down", record.get("isOneWordLimitDown", False))),
                "can_buy": bool(can_buy) if can_buy is not None else not is_suspended and not is_limit_up,
                "can_sell": bool(can_sell) if can_sell is not None else not is_suspended and not is_limit_down,
                "is_st": bool(record.get("is_st", record.get("isSt", False))),
            }
        )
    upsert_trade_status(rows, source=source, batch_id=batch_id)
    return {"batchId": batch_id, "count": len(rows)}


def upsert_adjustment_factors(rows: list[dict[str, Any]], source: str, batch_id: str) -> None:
    values = [row for row in rows if row.get("adj_factor") is not None]
    with db() as connection:
        for row in values:
            connection.execute(
                """
                insert into adjustment_factors (symbol, trade_date, adj_factor, source, batch_id)
                values (?, ?, ?, ?, ?)
                on conflict(symbol, trade_date, source) do update set
                    adj_factor = excluded.adj_factor,
                    batch_id = excluded.batch_id
                """,
                (row["symbol"], row["trade_date"], row["adj_factor"], source, batch_id),
            )


def import_adjustment_factors(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    rows = []
    symbols: set[str] = set()
    for record in records:
        symbol = _symbol(record)
        adj_factor = _float(record.get("adj_factor") or record.get("adjFactor"))
        if adj_factor is None or adj_factor <= 0:
            raise LeanWebError("adj_factor must be positive.")
        rows.append(
            {
                "symbol": symbol,
                "trade_date": _date(record.get("trade_date") or record.get("tradeDate"), "trade_date"),
                "adj_factor": adj_factor,
            }
        )
        symbols.add(symbol)
    upsert_adjustment_factors(rows, source=source, batch_id=batch_id)
    factor_files = {}
    from ..lean import write_equity_factor_file

    for symbol in sorted(symbols):
        factors = adjustment_factors(symbol)
        if factors:
            factor_files[symbol] = write_equity_factor_file(symbol, factors, market="china")
    return {"batchId": batch_id, "count": len(rows), "factorFiles": factor_files}


def upsert_corporate_actions(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    now = utc_now()
    count = 0
    with db() as connection:
        for record in records:
            symbol = _symbol(record)
            action_type = str(record.get("action_type") or record.get("actionType") or "dividend").strip().lower()
            if not action_type:
                raise LeanWebError("action_type is required.")
            connection.execute(
                """
                insert into corporate_actions
                    (symbol, ex_date, action_type, cash_dividend, stock_dividend, split_ratio,
                     allotment_ratio, allotment_price, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, ex_date, action_type, source) do update set
                    cash_dividend = excluded.cash_dividend,
                    stock_dividend = excluded.stock_dividend,
                    split_ratio = excluded.split_ratio,
                    allotment_ratio = excluded.allotment_ratio,
                    allotment_price = excluded.allotment_price,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    symbol,
                    _date(record.get("ex_date") or record.get("exDate"), "ex_date"),
                    action_type,
                    _float(record.get("cash_dividend") or record.get("cashDividend")),
                    _float(record.get("stock_dividend") or record.get("stockDividend")),
                    _float(record.get("split_ratio") or record.get("splitRatio")),
                    _float(record.get("allotment_ratio") or record.get("allotmentRatio")),
                    _float(record.get("allotment_price") or record.get("allotmentPrice")),
                    record.get("source") or source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    return {"batchId": batch_id, "count": count}


def adjustment_factors(symbol: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    clauses = ["symbol = ?"]
    values: list[Any] = [symbol]
    if start:
        clauses.append("trade_date >= ?")
        values.append(start)
    if end:
        clauses.append("trade_date <= ?")
        values.append(end)
    with db() as connection:
        rows = connection.execute(
            f"""
            select symbol, trade_date, adj_factor, source, batch_id
            from adjustment_factors
            where {" and ".join(clauses)}
            order by trade_date asc, source desc
            """,
            values,
        ).fetchall()
    result = []
    seen: set[str] = set()
    for row in rows_to_dicts(rows):
        if row["trade_date"] in seen:
            continue
        seen.add(row["trade_date"])
        result.append(row)
    return result


def corporate_actions(symbol: str, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    clauses = ["symbol = ?"]
    values: list[Any] = [symbol]
    if start:
        clauses.append("ex_date >= ?")
        values.append(start)
    if end:
        clauses.append("ex_date <= ?")
        values.append(end)
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from corporate_actions
            where {" and ".join(clauses)}
            order by ex_date asc, action_type asc
            """,
            values,
        ).fetchall()
    return rows_to_dicts(rows)


def upsert_universe_membership(
    universe_code: str,
    symbol: str,
    start_date: str,
    end_date: str | None,
    source: str,
    batch_id: str | None = None,
    weight: float | None = None,
    announce_date: str | None = None,
    effective_date: str | None = None,
) -> None:
    with db() as connection:
        connection.execute(
            """
            insert into universe_membership
                (universe_code, symbol, start_date, end_date, announce_date, effective_date, weight, source, batch_id)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(universe_code, symbol, start_date) do update set
                end_date = excluded.end_date,
                announce_date = excluded.announce_date,
                effective_date = excluded.effective_date,
                weight = excluded.weight,
                source = excluded.source,
                batch_id = excluded.batch_id
            """,
            (
                universe_code,
                symbol,
                start_date,
                end_date,
                announce_date,
                effective_date or start_date,
                weight,
                source,
                batch_id,
            ),
        )


def universe_as_of(universe_code: str, as_of_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select u.universe_code, u.symbol, u.start_date, u.end_date, u.weight,
                   s.name, s.exchange, s.listed_date, s.delisted_date, s.status, s.is_st, s.industry
            from universe_membership u
            join securities s on s.symbol = u.symbol
            where u.universe_code = ?
              and u.start_date <= ?
              and (u.end_date is null or u.end_date >= ?)
              and (u.announce_date is null or u.announce_date <= ?)
              and (u.effective_date is null or u.effective_date <= ?)
              and s.listed_date <= ?
              and (s.delisted_date is null or s.delisted_date > ?)
            order by u.symbol
            """,
            (universe_code, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date, as_of_date),
        ).fetchall()
    return rows_to_dicts(rows)


def tradable_universe_as_of(
    universe_code: str,
    as_of_date: str,
    *,
    min_listed_days: int = 0,
    exclude_st: bool = True,
) -> list[dict[str, Any]]:
    as_of = _date(as_of_date, "as_of_date")
    items = universe_as_of(universe_code, as_of)
    filtered = []
    as_of_day = date.fromisoformat(as_of)
    for item in items:
        listed_date = item.get("listed_date")
        if listed_date:
            listed_days = (as_of_day - date.fromisoformat(listed_date)).days
            if listed_days < max(0, int(min_listed_days)):
                continue
            item["listed_days"] = listed_days
        if exclude_st and item.get("is_st"):
            continue
        status = str(item.get("status") or "").lower()
        delisted_date = item.get("delisted_date")
        is_pre_delist = status == "delisted" and delisted_date and delisted_date > as_of
        if status not in {"listed", "normal"} and not is_pre_delist:
            continue
        filtered.append(item)
    return filtered


def trade_status_as_of(symbols: list[str], as_of_date: str) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from ashare_trade_status
            where trade_date = ? and symbol in ({placeholders})
            """,
            [as_of_date, *symbols],
        ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    bool_fields = {
        "is_suspended",
        "is_limit_up",
        "is_limit_down",
        "is_one_word_limit_up",
        "is_one_word_limit_down",
        "can_buy",
        "can_sell",
        "is_st",
    }
    for row in rows:
        item = row_to_dict(row) or {}
        for field in bool_fields:
            if field in item:
                item[field] = bool(item[field])
        result[row["symbol"]] = item
    return result


def is_tradeable(symbol: str, trade_date: str, side: str) -> tuple[bool, str]:
    security = get_security(symbol)
    if not security:
        return False, "security_not_found"
    if security.get("listed_date") and security["listed_date"] > trade_date:
        return False, "not_listed"
    if security.get("delisted_date") and security["delisted_date"] <= trade_date:
        return False, "delisted"
    if str(security.get("status") or "").lower() not in {"listed", "normal"} and not security.get("delisted_date"):
        return False, "not_active"
    with db() as connection:
        row = connection.execute(
            "select * from ashare_trade_status where symbol = ? and trade_date = ?",
            (symbol, trade_date),
        ).fetchone()
    status = row_to_dict(row)
    if not status:
        return False, "trade_status_missing"
    if status.get("is_suspended"):
        return False, "suspended"
    if side == "buy" and not status.get("can_buy"):
        return False, "blocked_buy"
    if side == "sell" and not status.get("can_sell"):
        return False, "blocked_sell"
    return True, "ok"


def latest_batch_for_symbol(symbol: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select b.* from data_import_batches b
            join ashare_daily_bars d on d.batch_id = b.id
            where d.symbol = ?
            order by b.started_at desc
            limit 1
            """,
            (symbol,),
        ).fetchone()
    return row_to_dict(row)


def data_coverage(symbol: str, start: str, end: str, adjust: str = "raw") -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """
            select count(*) as count, min(trade_date) as first_date, max(trade_date) as last_date
            from ashare_daily_bars
            where symbol = ? and adjust = ? and trade_date >= ? and trade_date <= ?
            """,
            (symbol, adjust, start, end),
        ).fetchone()
        status_row = connection.execute(
            """
            select count(*) as count from ashare_trade_status
            where symbol = ? and trade_date >= ? and trade_date <= ?
            """,
            (symbol, start, end),
        ).fetchone()
    return {
        "bar_count": row["count"] if row else 0,
        "first_date": row["first_date"] if row else None,
        "last_date": row["last_date"] if row else None,
        "status_count": status_row["count"] if status_row else 0,
    }


def status_payload(symbol: str, start: str, end: str) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from ashare_trade_status
            where symbol = ? and trade_date >= ? and trade_date <= ?
            order by trade_date asc
            """,
            (symbol, start, end),
        ).fetchall()
    return {
        symbol: {
            row["trade_date"]: {
                "is_suspended": bool(row["is_suspended"]),
                "limit_up": row["limit_up"],
                "limit_down": row["limit_down"],
                "is_limit_up": bool(row["is_limit_up"]),
                "is_limit_down": bool(row["is_limit_down"]),
                "can_buy": bool(row["can_buy"]),
                "can_sell": bool(row["can_sell"]),
                "is_st": bool(row["is_st"]),
            }
            for row in rows
        }
    }


def assert_ashare_ready(symbol: str, start: str, end: str, adjust: str = "raw") -> None:
    if not get_security(symbol):
        raise LeanWebError(f"A-share security master is missing for {symbol}. Import or register the security first.")
    trade_dates = trade_dates_between("china", start, end)
    if not trade_dates:
        raise LeanWebError(f"A-share trade calendar is missing for {start} -> {end}.")
    coverage = data_coverage(symbol, start, end, adjust)
    if coverage["bar_count"] <= 0:
        raise LeanWebError(f"A-share daily bars are missing for {symbol} in {start} -> {end}.")
    if coverage["bar_count"] < len(trade_dates):
        raise LeanWebError(
            f"A-share daily bars are incomplete for {symbol} in {start} -> {end}: "
            f"{coverage['bar_count']} bars for {len(trade_dates)} trade dates."
        )
    if coverage["status_count"] < coverage["bar_count"]:
        raise LeanWebError(f"A-share trade status is incomplete for {symbol} in {start} -> {end}.")
    batch = latest_batch_for_symbol(symbol)
    if not batch:
        raise LeanWebError(f"A-share import batch is missing for {symbol}.")
    qa_report = batch.get("qa_report") or {}
    if batch.get("status") != "success" or not qa_report.get("passed", False):
        raise LeanWebError(f"Latest A-share data QA failed for {symbol}: {qa_report or batch.get('error')}")
