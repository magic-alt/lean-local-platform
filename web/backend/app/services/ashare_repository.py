from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


def _bool(value: Any) -> int:
    return 1 if bool(value) else 0


def infer_exchange(symbol: str) -> str:
    value = symbol.strip()
    if value.startswith(("6", "9")):
        return "SSE"
    if value.startswith(("4", "8")):
        return "BSE"
    return "SZSE"


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


def upsert_universe_membership(
    universe_code: str,
    symbol: str,
    start_date: str,
    end_date: str | None,
    source: str,
    batch_id: str | None = None,
    weight: float | None = None,
) -> None:
    with db() as connection:
        connection.execute(
            """
            insert into universe_membership
                (universe_code, symbol, start_date, end_date, weight, source, batch_id)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(universe_code, symbol, start_date) do update set
                end_date = excluded.end_date,
                weight = excluded.weight,
                source = excluded.source,
                batch_id = excluded.batch_id
            """,
            (universe_code, symbol, start_date, end_date, weight, source, batch_id),
        )


def universe_as_of(universe_code: str, as_of_date: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select u.universe_code, u.symbol, u.start_date, u.end_date, u.weight,
                   s.name, s.exchange, s.status, s.is_st, s.industry
            from universe_membership u
            left join securities s on s.symbol = u.symbol
            where u.universe_code = ?
              and u.start_date <= ?
              and (u.end_date is null or u.end_date >= ?)
              and (s.delisted_date is null or s.delisted_date > ?)
            order by u.symbol
            """,
            (universe_code, as_of_date, as_of_date, as_of_date),
        ).fetchall()
    return rows_to_dicts(rows)


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
    return {row["symbol"]: row_to_dict(row) or {} for row in rows}


def is_tradeable(symbol: str, trade_date: str, side: str) -> tuple[bool, str]:
    security = get_security(symbol)
    if not security:
        return False, "security_not_found"
    if security.get("delisted_date") and security["delisted_date"] <= trade_date:
        return False, "delisted"
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
