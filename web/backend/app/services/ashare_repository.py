from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from ..core.errors import LeanWebError
from ..db import bulk_db, db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.errors import LeanPlatformError
from .market_repository import (
    instrument_id,
    upsert_instrument,
    upsert_market_daily_bars,
    upsert_market_daily_bars_batch,
    upsert_market_trade_status_batch,
)


WRITE_BATCH_SIZE = 5_000
LOOKUP_BATCH_SIZE = 400


def _trade_status_priority_sql(column: str = "source") -> str:
    """Rank canonical evidence without relying on a compatibility view."""
    return f"""
        case
            when lower({column}) like '%suspend%' or lower({column}) like '%daily_absence%' then 120
            when lower({column}) like '%official%' then 110
            when lower({column}) like '%inferred%' or lower({column}) like '%ohlcv%' then 10
            when lower({column}) like '%tushare%' or lower({column}) like '%jqdata%'
              or lower({column}) like '%rqdata%' or lower({column}) like '%ifind%'
              or lower({column}) like '%choice%' or lower({column}) like '%wind%'
              or lower({column}) like '%stk_limit%' then 100
            when lower({column}) like '%manual%' then 90
            when lower({column}) like '%adata%' or lower({column}) like '%baostock%'
              or lower({column}) like '%akshare%' or lower({column}) like '%sina%'
              or lower({column}) like '%eastmoney%' then 70
            else 50
        end
    """


def _chunks(values: list[Any], size: int) -> list[list[Any]]:
    return [values[offset : offset + size] for offset in range(0, len(values), size)]


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
    bulk: bool = False,
) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    if bulk and records:
        now = utc_now()
        security_parameters = []
        instrument_parameters = []
        membership_parameters = []
        for record in records:
            symbol = _symbol(record)
            listed_date = _date(record.get("listed_date") or record.get("list_date") or record.get("listDate"), "listed_date")
            delisted_date = _optional_date(record.get("delisted_date") or record.get("delist_date") or record.get("delistDate"))
            status = _status(record.get("status") or record.get("list_status"))
            if delisted_date and status == "listed":
                status = "delisted"
            name = record.get("name") or record.get("symbol_name") or record.get("stock_name") or symbol
            exchange = record.get("exchange") or record.get("exchange_code") or infer_exchange(symbol)
            is_st = bool(record.get("is_st", False))
            industry = record.get("industry")
            concepts = record.get("concepts") if isinstance(record.get("concepts"), list) else []
            record_source = record.get("source") or source
            security_parameters.append(
                (
                    symbol, name, exchange, "china", listed_date, delisted_date, status,
                    _bool(is_st), industry, json_dump(concepts), now, now,
                )
            )
            instrument_parameters.append(
                (
                    instrument_id("equity", "china", symbol, "china"), symbol, symbol, name,
                    "equity", "china", exchange, "china", "CNY", listed_date, delisted_date,
                    "delisted" if status == "delisted" else "active", 100, 0.01,
                    json_dump({"source_status": status, "is_st": is_st, "industry": industry, "concepts": concepts}),
                    "securities", now, now,
                )
            )
            membership_parameters.append(
                (
                    universe_code.upper(), symbol, listed_date, delisted_date,
                    _optional_date(record.get("announce_date") or record.get("announceDate")) or listed_date,
                    _optional_date(record.get("effective_date") or record.get("effectiveDate")) or listed_date,
                    None, record_source, batch_id,
                )
            )
        with bulk_db() as connection:
            connection.executemany(
                """
                insert into securities
                    (symbol,name,exchange,market,listed_date,delisted_date,status,is_st,
                     industry,concepts_json,created_at,updated_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(symbol) do update set
                    name=case when excluded.name=excluded.symbol and securities.name<>securities.symbol
                              then securities.name else excluded.name end,
                    exchange=excluded.exchange,
                    listed_date=min(securities.listed_date,excluded.listed_date),
                    delisted_date=excluded.delisted_date,
                    status=excluded.status,
                    is_st=excluded.is_st,
                    industry=coalesce(excluded.industry,securities.industry),
                    concepts_json=coalesce(excluded.concepts_json,securities.concepts_json),
                    updated_at=excluded.updated_at
                """,
                security_parameters,
            )
            connection.executemany(
                """
                insert into instruments
                    (instrument_id,symbol,normalized_symbol,name,asset_class,market,exchange,venue,
                     currency,listed_date,delisted_date,status,lot_size,tick_size,metadata_json,
                     source,created_at,updated_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(instrument_id) do update set
                    name=case when excluded.name=excluded.symbol and instruments.name<>instruments.symbol
                              then instruments.name else excluded.name end,
                    exchange=excluded.exchange,
                    listed_date=case when instruments.listed_date is null then excluded.listed_date
                                     else min(instruments.listed_date,excluded.listed_date) end,
                    delisted_date=excluded.delisted_date,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                instrument_parameters,
            )
            connection.executemany(
                """
                insert into universe_membership
                    (universe_code,symbol,start_date,end_date,announce_date,effective_date,
                     weight,source,batch_id)
                values (?,?,?,?,?,?,?,?,?)
                on conflict(universe_code,symbol,start_date) do update set
                    end_date=excluded.end_date,
                    announce_date=excluded.announce_date,
                    effective_date=excluded.effective_date,
                    weight=excluded.weight,
                    source=excluded.source,
                    batch_id=excluded.batch_id
                """,
                membership_parameters,
            )
        return {"batchId": batch_id, "universe": universe_code.upper(), "count": len(records)}
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
                name = case
                    when excluded.name = excluded.symbol and securities.name <> securities.symbol
                    then securities.name
                    else excluded.name
                end,
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
    upsert_instrument(
        symbol=symbol,
        name=name or symbol,
        asset_class="equity",
        market="china",
        venue="china",
        exchange=exchange or infer_exchange(symbol),
        currency="CNY",
        listed_date=listed_date,
        delisted_date=delisted_date,
        status="delisted" if status == "delisted" else "active",
        lot_size=100,
        tick_size=0.01,
        metadata={"source_status": status, "is_st": bool(is_st), "industry": industry, "concepts": concepts or []},
        source="securities",
    )


def get_security(symbol: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from securities where symbol = ?", (symbol,)).fetchone()
    return row_to_dict(row)


def upsert_data_gap_resolutions(
    *,
    market: str,
    symbol: str,
    classifications: dict[str, dict[str, Any]],
    batch_id: str,
) -> None:
    """Persist the evidence used to accept or reject each expected-session gap."""
    now = utc_now()
    with db() as connection:
        for trade_date, item in classifications.items():
            connection.execute(
                """
                insert into data_gap_resolutions
                    (id, market, symbol, trade_date, classification, status,
                     evidence_source, evidence_json, batch_id, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(market, symbol, trade_date) do update set
                    classification=excluded.classification,
                    status=excluded.status,
                    evidence_source=excluded.evidence_source,
                    evidence_json=excluded.evidence_json,
                    batch_id=excluded.batch_id,
                    updated_at=excluded.updated_at
                """,
                (
                    str(uuid.uuid4()),
                    market,
                    symbol,
                    trade_date,
                    str(item.get("classification") or "unresolved_source_gap"),
                    str(item.get("status") or "open"),
                    item.get("evidence_source"),
                    json_dump(item.get("evidence") or {}),
                    batch_id,
                    now,
                    now,
                ),
            )


def upsert_trade_calendar(market: str, trade_dates: list[str], source: str, batch_id: str | None = None) -> None:
    unique_dates = sorted(set(trade_dates))
    if not unique_dates:
        return
    parameters = [
        (
            market,
            trade_date,
            1,
            unique_dates[index - 1] if index > 0 else None,
            unique_dates[index + 1] if index + 1 < len(unique_dates) else None,
            source,
            batch_id,
        )
        for index, trade_date in enumerate(unique_dates)
    ]
    with db() as connection:
        connection.executemany(
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
            parameters,
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


def end_coverage_status(market: str, requested_end: str, actual_last_date: str | None) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            "select max(trade_date) as latest_date from trade_calendar where market = ? and is_open = 1",
            (market,),
        ).fetchone()
    calendar_latest = row["latest_date"] if row else None
    trade_dates = trade_dates_between(market, "1900-01-01", requested_end)
    expected_last = trade_dates[-1] if trade_dates else requested_end
    requested = datetime.fromisoformat(requested_end).date()
    calendar_date = datetime.fromisoformat(calendar_latest).date() if calendar_latest else None
    actual_date = datetime.fromisoformat(str(actual_last_date)).date() if actual_last_date else None
    calendar_lag_days = (requested - calendar_date).days if calendar_date and calendar_date < requested else 0
    # A Friday close legitimately covers a weekend end date. A longer gap means
    # the calendar itself is stale, so using its last row as the expected end
    # would silently bless a truncated backtest.
    # Exact bar coverage remains valid if a legacy dataset has no separate
    # calendar rows. The calendar is only mandatory when it is needed to prove
    # that an earlier bar date is the final trading day in the request window.
    calendar_complete = bool(actual_date and actual_date >= requested) or (
        bool(calendar_latest) and calendar_lag_days <= 3
    )
    data_complete = bool(actual_last_date) and str(actual_last_date) >= str(expected_last)
    return {
        "requestedEnd": requested_end,
        "expectedLastTradeDate": expected_last,
        "actualLastDate": actual_last_date,
        "calendarLatestDate": calendar_latest,
        "calendarLagDays": calendar_lag_days,
        "calendarComplete": calendar_complete,
        "dataComplete": data_complete,
        "passed": calendar_complete and data_complete,
        "truncated": not (calendar_complete and data_complete),
    }


def upsert_daily_bars(
    rows: list[dict[str, Any]],
    source: str,
    batch_id: str,
    adjust: str,
    *,
    bulk: bool = False,
) -> None:
    if bulk:
        upsert_market_daily_bars_batch(
            rows,
            asset_class="equity",
            market="china",
            venue="china",
            source=source,
            batch_id=batch_id,
            resolution="daily",
            data_type="trade",
            adjust=adjust,
            bulk=True,
        )
    else:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(str(row["symbol"]), []).append(row)
        for symbol, symbol_rows in grouped.items():
            upsert_market_daily_bars(
                symbol_rows,
                symbol=symbol,
                asset_class="equity",
                market="china",
                venue="china",
                source=source,
                batch_id=batch_id,
                resolution="daily",
                data_type="trade",
                adjust=adjust,
                bulk=bulk,
            )


def upsert_trade_status(
    rows: list[dict[str, Any]],
    source: str,
    batch_id: str,
    *,
    bulk: bool = False,
) -> None:
    upsert_market_trade_status_batch(
        rows,
        asset_class="equity",
        market="china",
        venue="china",
        source=source,
        batch_id=batch_id,
        bulk=bulk,
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


def upsert_adjustment_factors(
    rows: list[dict[str, Any]],
    source: str,
    batch_id: str,
    *,
    bulk: bool = False,
) -> None:
    values = [row for row in rows if row.get("adj_factor") is not None]
    if values:
        from ..db import bulk_db

        context = bulk_db if bulk else db
        with context() as connection:
            connection.executemany(
                """
                insert into adjustment_factors (symbol, trade_date, adj_factor, source, batch_id)
                values (?, ?, ?, ?, ?)
                on conflict(symbol, trade_date, source) do update set
                    adj_factor = excluded.adj_factor,
                    batch_id = excluded.batch_id
                """,
                [(row["symbol"], row["trade_date"], row["adj_factor"], source, batch_id) for row in values],
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
    from ..lean_engine.data_paths import write_equity_factor_file

    for symbol in sorted(symbols):
        factors = adjustment_factors(symbol)
        if factors:
            factor_files[symbol] = write_equity_factor_file(symbol, factors, market="china")
    return {"batchId": batch_id, "count": len(rows), "factorFiles": factor_files}


def upsert_corporate_actions(
    records: list[dict[str, Any]],
    source: str = "manual",
    batch_id: str | None = None,
    *,
    bulk: bool = False,
) -> dict[str, Any]:
    batch_id = batch_id or str(uuid.uuid4())
    now = utc_now()
    parameters = []
    for record in records:
        symbol = _symbol(record)
        action_type = str(record.get("action_type") or record.get("actionType") or "dividend").strip().lower()
        if not action_type:
            raise LeanWebError("action_type is required.")
        parameters.append(
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
            )
        )
    connection_factory = bulk_db if bulk else db
    with connection_factory() as connection:
        for chunk in _chunks(parameters, WRITE_BATCH_SIZE):
            connection.executemany(
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
                chunk,
            )
    return {"batchId": batch_id, "count": len(parameters)}


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


def upsert_index_weights(
    records: list[dict[str, Any]],
    source: str,
    batch_id: str | None = None,
    *,
    bulk: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    parameters = []
    for record in records:
        symbol = _symbol(record)
        universe_code = str(record.get("universe_code") or record.get("universeCode") or "CSI300").upper()
        trade_date = _date(record.get("trade_date") or record.get("tradeDate"), "trade_date")
        weight = _float(record.get("weight"))
        if weight is None:
            raise LeanWebError("index weight is required.")
        parameters.append((universe_code, symbol, trade_date, weight, record.get("source") or source, batch_id, now))
    connection_factory = bulk_db if bulk else db
    with connection_factory() as connection:
        for chunk in _chunks(parameters, WRITE_BATCH_SIZE):
            connection.executemany(
                """
                insert into index_weights
                    (universe_code, symbol, trade_date, weight, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(universe_code, symbol, trade_date, source) do update set
                    weight = excluded.weight,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                chunk,
            )
    return {"batchId": batch_id, "count": len(parameters)}


def index_weights(
    universe_code: str,
    trade_date: str,
    *,
    source: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["universe_code = ?", "trade_date = ?"]
    values: list[Any] = [universe_code.upper(), _date(trade_date, "trade_date")]
    if source:
        clauses.append("source = ?")
        values.append(source)
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from index_weights
            where {" and ".join(clauses)}
            order by weight desc, symbol asc
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
            select * from market_trade_status
            where asset_class='equity' and market='china' and venue='china'
              and trade_date = ? and symbol in ({placeholders})
            order by symbol,{_trade_status_priority_sql()} desc,updated_at desc
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
        result.setdefault(row["symbol"], item)
    return result


def effective_trade_status(symbol: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            f"""
            select * from market_trade_status
            where symbol = ? and trade_date = ? and asset_class='equity'
              and market='china' and venue='china'
            order by {_trade_status_priority_sql()} desc,updated_at desc limit 1
            """,
            (symbol, trade_date),
        ).fetchone()
    status = row_to_dict(row)
    if status:
        for field in (
            "is_tradeable", "is_suspended", "can_buy", "can_sell", "is_limit_up",
            "is_limit_down", "is_one_word_limit_up", "is_one_word_limit_down", "is_st",
        ):
            if field in status:
                status[field] = bool(status[field])
    return status


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
    status = effective_trade_status(symbol, trade_date)
    if not status:
        return False, "trade_status_missing"
    if status.get("is_suspended"):
        return False, "suspended"
    if side == "buy" and not status.get("can_buy"):
        return False, "blocked_buy"
    if side == "sell" and not status.get("can_sell"):
        return False, "blocked_sell"
    return True, "ok"


def latest_batch_for_symbol(symbol: str, source: str | None = None) -> dict[str, Any] | None:
    source_clause = "and d.source = ?" if source else ""
    params: list[Any] = [symbol]
    if source:
        params.append(source)
    with db() as connection:
        row = connection.execute(
            f"""
            select b.* from data_import_batches b
            join market_daily_bars d on d.batch_id = b.id
            where d.symbol = ?
              and d.asset_class='equity' and d.market='china' and d.venue='china'
              and d.resolution='daily' and d.data_type='trade'
              {source_clause}
              and b.status in ('success', 'failed')
            order by b.started_at desc
            limit 1
            """,
            params,
        ).fetchone()
    return row_to_dict(row)


def data_coverage(symbol: str, start: str, end: str, adjust: str = "raw", source: str | None = None) -> dict[str, Any]:
    source_clause = "and source = ?" if source else ""
    source_params: list[Any] = [source] if source else []
    with db() as connection:
        status_row = connection.execute(
            """
            select count(distinct trade_date) as count from market_trade_status
            where symbol = ? and asset_class='equity' and market='china' and venue='china'
              and trade_date >= ? and trade_date <= ?
            """,
            (symbol, start, end),
        ).fetchone()
        market_row = connection.execute(
            f"""
            select count(*) as raw_count,count(distinct trade_date) as count,
                   min(trade_date) as first_date,max(trade_date) as last_date
            from market_daily_bars
            where symbol = ? and asset_class = 'equity' and market = 'china' and venue='china'
              and resolution = 'daily' and data_type = 'trade' and adjust = ?
              and trade_date >= ? and trade_date <= ?
              {source_clause}
            """,
            (symbol, adjust, start, end, *source_params),
        ).fetchone()
    return {
        "bar_count": market_row["count"] if market_row else 0,
        "bar_raw_count": market_row["raw_count"] if market_row else 0,
        "first_date": market_row["first_date"] if market_row else None,
        "last_date": market_row["last_date"] if market_row else None,
        "status_count": status_row["count"] if status_row else 0,
        "market_bar_count": market_row["count"] if market_row else 0,
        "market_first_date": market_row["first_date"] if market_row else None,
        "market_last_date": market_row["last_date"] if market_row else None,
    }


def _execution_coverage_dates(
    symbol: str,
    start: str,
    end: str,
    adjust: str,
    source: str | None,
) -> tuple[set[str], dict[str, bool]]:
    source_clause = "and source = ?" if source else ""
    source_params: list[Any] = [source] if source else []
    with db() as connection:
        bar_rows = connection.execute(
            f"""
            select trade_date
            from market_daily_bars
            where symbol = ? and asset_class = 'equity' and market = 'china' and venue='china'
              and resolution = 'daily' and data_type = 'trade' and adjust = ?
              and trade_date >= ? and trade_date <= ?
              {source_clause}
            """,
            (
                symbol,
                adjust,
                start,
                end,
                *source_params,
            ),
        ).fetchall()
        status_rows = connection.execute(
            """
            select trade_date, max(is_suspended) as is_suspended
            from market_trade_status
            where symbol = ? and asset_class='equity' and market='china' and venue='china'
              and trade_date >= ? and trade_date <= ?
            group by trade_date
            """,
            (symbol, start, end),
        ).fetchall()
    return (
        {str(row["trade_date"]) for row in bar_rows},
        {str(row["trade_date"]): bool(row["is_suspended"]) for row in status_rows},
    )


def status_payload(symbol: str, start: str, end: str) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from market_trade_status
            where symbol = ? and asset_class='equity' and market='china' and venue='china'
              and trade_date >= ? and trade_date <= ?
            order by trade_date asc,{_trade_status_priority_sql()} desc,updated_at desc
            """,
            (symbol, start, end),
        ).fetchall()
    status_by_date: dict[str, dict[str, Any]] = {}
    for row in rows:
        status_by_date.setdefault(
            row["trade_date"],
            {
                "is_suspended": bool(row["is_suspended"]),
                "limit_up": row["limit_up"],
                "limit_down": row["limit_down"],
                "is_limit_up": bool(row["is_limit_up"]),
                "is_limit_down": bool(row["is_limit_down"]),
                "is_one_word_limit_up": bool(row["is_one_word_limit_up"]),
                "is_one_word_limit_down": bool(row["is_one_word_limit_down"]),
                "can_buy": bool(row["can_buy"]),
                "can_sell": bool(row["can_sell"]),
                "is_st": bool(row["is_st"]),
            },
        )
    return {symbol: status_by_date}


def reference_data_coverage(index_code: str = "CSI300") -> dict[str, Any]:
    code = index_code.strip().upper()
    with db() as connection:
        calendar = connection.execute(
            """
            select count(*) as total,
                   sum(case when is_open=1 then 1 else 0 end) as open_days,
                   min(trade_date) as start_date,
                   max(trade_date) as end_date
            from trade_calendar where market='china'
            """
        ).fetchone()
        securities = connection.execute(
            """
            select count(*) as total,
                   sum(case when status = 'delisted' or delisted_date is not null then 1 else 0 end) as delisted,
                   sum(case when is_st = 1 then 1 else 0 end) as st
            from securities
            """
        ).fetchone()
        trade_status = connection.execute(
            """
            select count(*) as total,
                   count(distinct symbol) as symbols,
                   sum(case when is_suspended = 1 then 1 else 0 end) as suspended_days,
                   sum(case when is_st = 1 then 1 else 0 end) as st_days,
                   min(trade_date) as start_date,
                   max(trade_date) as end_date
            from market_trade_status
            where asset_class='equity' and market='china' and venue='china'
            """
        ).fetchone()
        actions = connection.execute(
            """
            select count(*) as total,
                   count(distinct symbol) as symbols,
                   min(ex_date) as start_date,
                   max(ex_date) as end_date
            from corporate_actions
            """
        ).fetchone()
        pit = connection.execute(
            """
            select count(*) as total,
                   count(distinct symbol) as symbols,
                   min(start_date) as start_date,
                   max(coalesce(end_date, start_date)) as end_date
            from index_membership_pit
            where index_code = ?
            """,
            (code,),
        ).fetchone()
        reference_report = connection.execute(
            """
            select *
            from data_quality_reports
            where report_type = 'ashare_reference_public_import'
              and asset_class = 'equity'
              and market = 'china'
            order by created_at desc
            limit 1
            """
        ).fetchone()
    calendar = row_to_dict(calendar) or {}
    securities = row_to_dict(securities) or {}
    trade_status = row_to_dict(trade_status) or {}
    actions = row_to_dict(actions) or {}
    pit = row_to_dict(pit) or {}
    reference_report = row_to_dict(reference_report) or {}
    reference_result = reference_report.get("result") or {}
    warnings = list(dict.fromkeys(reference_result.get("warnings") or []))
    issues = []
    if int(calendar.get("open_days") or 0) == 0:
        issues.append("trade_calendar_missing")
    if int(securities["total"] or 0) == 0:
        issues.append("security_master_missing")
    if int(securities["delisted"] or 0) == 0:
        issues.append("delisted_security_missing")
    if int(securities["st"] or 0) == 0:
        issues.append("security_master_st_missing")
    if int(trade_status["suspended_days"] or 0) == 0:
        issues.append("suspended_trade_status_missing")
    if int(actions["total"] or 0) == 0:
        issues.append("corporate_actions_missing")
    if int(pit["total"] or 0) == 0:
        issues.append(f"{code.lower()}_pit_missing")
    severity = "critical" if any(issue.endswith("_missing") for issue in issues) else ("warning" if warnings else "ok")
    return {
        "indexCode": code,
        "severity": severity,
        "passed": severity != "critical",
        "issues": issues,
        "warnings": warnings,
        "referenceSources": reference_result.get("sourceStatus") or {},
        "tradeCalendar": {
            "rows": int(calendar.get("total") or 0),
            "openDays": int(calendar.get("open_days") or 0),
            "startDate": calendar.get("start_date"),
            "endDate": calendar.get("end_date"),
        },
        "securities": {
            "total": int(securities.get("total") or 0),
            "delisted": int(securities.get("delisted") or 0),
            "st": int(securities.get("st") or 0),
        },
        "tradeStatus": {
            "rows": int(trade_status.get("total") or 0),
            "symbols": int(trade_status.get("symbols") or 0),
            "suspendedDays": int(trade_status.get("suspended_days") or 0),
            "stDays": int(trade_status.get("st_days") or 0),
            "startDate": trade_status.get("start_date"),
            "endDate": trade_status.get("end_date"),
        },
        "corporateActions": {
            "rows": int(actions.get("total") or 0),
            "symbols": int(actions.get("symbols") or 0),
            "startDate": actions.get("start_date"),
            "endDate": actions.get("end_date"),
        },
        "pit": {
            "rows": int(pit.get("total") or 0),
            "symbols": int(pit.get("symbols") or 0),
            "startDate": pit.get("start_date"),
            "endDate": pit.get("end_date"),
        },
    }


def assert_ashare_ready(
    symbol: str,
    start: str,
    end: str,
    adjust: str = "raw",
    source: str | None = None,
    *,
    allow_truncated: bool = False,
) -> None:
    security = get_security(symbol)
    if not security:
        raise LeanWebError(f"A-share security master is missing for {symbol}. Import or register the security first.")
    required_start = max(start, str(security.get("listed_date") or start))
    delisted_date = security.get("delisted_date")
    last_listed_date = (
        (date.fromisoformat(str(delisted_date)) - timedelta(days=1)).isoformat()
        if delisted_date
        else end
    )
    required_end = min(end, last_listed_date)
    if required_start > required_end:
        return
    trade_dates = trade_dates_between("china", required_start, required_end)
    coverage = data_coverage(symbol, required_start, required_end, adjust, source=source)
    bar_count = max(int(coverage["bar_count"] or 0), int(coverage["market_bar_count"] or 0))
    if bar_count <= 0:
        suffix = f" source={source}" if source else ""
        raise LeanWebError(
            f"A-share daily bars are missing for {symbol} in {required_start} -> {required_end}{suffix}."
        )
    bar_dates, status_by_date = _execution_coverage_dates(
        symbol,
        required_start,
        required_end,
        adjust,
        source,
    )
    missing_status_dates = sorted(bar_dates - set(status_by_date))
    if missing_status_dates:
        raise LeanWebError(
            f"A-share trade status is incomplete for {symbol} in {required_start} -> {required_end}: "
            f"missing {len(missing_status_dates)} bar date(s), examples={missing_status_dates[:5]}."
        )
    unresolved_dates = sorted(
        trade_date
        for trade_date in trade_dates
        if trade_date not in bar_dates and not status_by_date.get(trade_date, False)
    )
    if unresolved_dates:
        raise LeanWebError(
            f"A-share daily bars are incomplete for {symbol} in {required_start} -> {required_end}: "
            f"{len(bar_dates)} bars for {len(trade_dates)} trade dates; "
            f"{len(unresolved_dates)} date(s) lack a bar or suspension status, "
            f"examples={unresolved_dates[:5]}."
        )
    end_status = end_coverage_status(
        "china",
        required_end,
        coverage.get("market_last_date") or coverage.get("last_date"),
    )
    suspension_covered_end = bool(
        end_status.get("calendarComplete")
        and trade_dates
        and not unresolved_dates
    )
    if not end_status["passed"] and not suspension_covered_end and not allow_truncated:
        raise LeanWebError(
            f"A-share daily bars are truncated for {symbol}: requested end {required_end}, "
            f"actual last date {end_status.get('actualLastDate')}, calendar latest "
            f"{end_status.get('calendarLatestDate')}. Set allowTruncatedData=true only for explicitly untrusted research."
        )
    batch = latest_batch_for_symbol(symbol, source=source)
    if not batch:
        raise LeanWebError(f"A-share import batch is missing for {symbol}.")
    qa_report = batch.get("qa_report") or {}
    if batch.get("status") != "success" or not qa_report.get("passed", False):
        raise LeanWebError(f"Latest A-share data QA failed for {symbol}: {qa_report or batch.get('error')}")


def assert_benchmark_ready(
    symbol: str,
    start: str,
    end: str,
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str = "china",
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str | None = None,
    allow_truncated: bool = False,
) -> None:
    benchmark = str(symbol or "").strip().upper()
    if not benchmark:
        raise LeanPlatformError("benchmark_missing: A-share benchmarkSymbol is required.")
    with db() as connection:
        row = connection.execute(
            f"""
            select count(distinct trade_date) as row_count,
                   min(trade_date) as first_date,
                   max(trade_date) as last_date
            from market_daily_bars
            where symbol = ? and asset_class in (?, 'index') and market = ? and venue = ?
              and resolution = ? and data_type = ? and adjust = ?
              and trade_date between ? and ?
              {"and source = ?" if source else ""}
            """,
            (
                benchmark,
                asset_class.lower(),
                market.lower(),
                venue.lower(),
                resolution.lower(),
                data_type.lower(),
                adjust or "raw",
                start,
                end,
                *([source] if source else []),
            ),
        ).fetchone()
    benchmark_row = dict(row) if row else {}
    row_count = int(benchmark_row.get("row_count") or 0)
    if row_count <= 0:
        raise LeanPlatformError(f"benchmark_missing:{benchmark} has no daily bars in {start} -> {end}.")
    trade_dates = trade_dates_between(market.lower(), start, end)
    expected_dates = len(trade_dates)
    if expected_dates and row_count < expected_dates:
        raise LeanPlatformError(
            f"benchmark_missing:{benchmark} has {row_count}/{expected_dates} daily bars in {start} -> {end}."
        )
    end_status = end_coverage_status(market.lower(), end, benchmark_row.get("last_date"))
    if not end_status["passed"] and not allow_truncated:
        raise LeanPlatformError(
            f"benchmark_truncated:{benchmark} requested end {end}, actual last date "
            f"{end_status.get('actualLastDate')}, calendar latest {end_status.get('calendarLatestDate')}."
        )
