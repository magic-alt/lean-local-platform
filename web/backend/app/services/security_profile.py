from __future__ import annotations

import json
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts
from ..lean_engine.symbols import market_key, normalize_symbol
from .security_search import MARKET_LABELS


def _json_list(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _coverage_row(
    connection: Any,
    *,
    key: str,
    label: str,
    table: str,
    symbol: str,
    date_column: str,
    predicate: str = "",
) -> dict[str, Any] | None:
    extra = f" and {predicate}" if predicate else ""
    aggregate = connection.execute(
        f"select count(*) as rows, min({date_column}) as first_date, max({date_column}) as last_date "
        f"from {table} where symbol = ?{extra}",
        (symbol,),
    ).fetchone()
    count = int(aggregate["rows"] or 0) if aggregate else 0
    if count <= 0:
        return None
    sources = connection.execute(
        f"select distinct source from {table} where symbol = ?{extra} order by source",
        (symbol,),
    ).fetchall()
    return {
        "key": key,
        "label": label,
        "rows": count,
        "firstDate": aggregate["first_date"],
        "lastDate": aggregate["last_date"],
        "sources": [str(row["source"]) for row in sources if row["source"]],
    }


def security_profile(symbol: str, *, market: str = "china") -> dict[str, Any]:
    selected_market = market_key(market)
    normalized = normalize_symbol(symbol, selected_market).upper()
    with db() as connection:
        security = row_to_dict(connection.execute(
            "select * from securities where symbol = ? and market = ? limit 1",
            (normalized, selected_market),
        ).fetchone()) or {}
        instrument = row_to_dict(connection.execute(
            """
            select * from instruments
            where symbol = ? and market = ? and asset_class = 'equity'
            order by updated_at desc limit 1
            """,
            (normalized, selected_market),
        ).fetchone()) or {}

        instrument_id = instrument.get("instrument_id")
        identifiers = rows_to_dicts(connection.execute(
            """
            select provider, identifier_type, identifier_value, exchange, market,
                   valid_from, valid_to, is_primary, source
            from instrument_identifiers
            where instrument_id = ?
            order by is_primary desc, provider, identifier_type
            """,
            (instrument_id or "",),
        ).fetchall())

        coverage: list[dict[str, Any]] = []
        if selected_market == "china":
            specs = (
                ("daily", "日线行情", "market_daily_bars", "trade_date", "asset_class='equity' and market='china' and venue='china' and resolution='daily' and data_type='trade'"),
                ("trade_status", "交易状态/涨跌停", "market_trade_status", "trade_date", "asset_class='equity' and market='china' and venue='china'"),
                ("adjustment_factors", "复权因子", "adjustment_factors", "trade_date", ""),
                ("corporate_actions", "公司行动", "corporate_actions", "ex_date", ""),
                ("factor_values", "每日指标/因子", "all_factor_values", "trade_date", ""),
                ("financial_statements", "财务报表", "financial_statements", "report_date", ""),
            )
            for key, label, table, date_column, predicate in specs:
                item = _coverage_row(
                    connection,
                    key=key,
                    label=label,
                    table=table,
                    symbol=normalized,
                    date_column=date_column,
                    predicate=predicate,
                )
                if item:
                    coverage.append(item)
        else:
            aggregate = connection.execute(
                """
                select count(*) as rows, min(trade_date) as first_date, max(trade_date) as last_date
                from market_daily_bars
                where symbol = ? and market = ? and asset_class = 'equity'
                """,
                (normalized, selected_market),
            ).fetchone()
            if aggregate and int(aggregate["rows"] or 0) > 0:
                sources = connection.execute(
                    """
                    select distinct source from market_daily_bars
                    where symbol = ? and market = ? and asset_class = 'equity' order by source
                    """,
                    (normalized, selected_market),
                ).fetchall()
                coverage.append({
                    "key": "daily",
                    "label": "日线行情",
                    "rows": int(aggregate["rows"] or 0),
                    "firstDate": aggregate["first_date"],
                    "lastDate": aggregate["last_date"],
                    "sources": [str(row["source"]) for row in sources if row["source"]],
                })

        latest_status = row_to_dict(connection.execute(
            """
            select * from market_trade_status where symbol=? and asset_class='equity'
              and market='china' and venue='china' order by trade_date desc,updated_at desc limit 1
            """,
            (normalized,),
        ).fetchone()) if selected_market == "china" else None
        memberships = rows_to_dicts(connection.execute(
            """
            select universe_code, start_date, end_date, weight, source
            from universe_membership where symbol = ?
            order by coalesce(end_date, '9999-12-31') desc, start_date desc limit 50
            """,
            (normalized,),
        ).fetchall()) if selected_market == "china" else []
        quote_row = row_to_dict(connection.execute(
            """
            select symbol,trade_date,open,high,low,close,prev_close,pct_change,
                   volume,amount,turnover_rate,adj_factor,source
            from market_daily_bars
            where symbol=? and asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade' and adjust='raw'
            order by case when source='tushare' then 0 else 1 end, trade_date desc
            limit 1
            """,
            (normalized,),
        ).fetchone()) if selected_market == "china" else None
        adjustment_history = rows_to_dicts(connection.execute(
            """
            select trade_date,adj_factor,source from adjustment_factors
            where symbol=? order by trade_date desc, source desc limit 200
            """,
            (normalized,),
        ).fetchall()) if selected_market == "china" else []
        suspension_history = rows_to_dicts(connection.execute(
            """
            select trade_date,is_suspended,can_buy,can_sell,source from market_trade_status
            where symbol=? and asset_class='equity' and market='china' and venue='china'
              and source='tushare:suspend_d'
            order by trade_date desc limit 200
            """,
            (normalized,),
        ).fetchall()) if selected_market == "china" else []
        limit_history = rows_to_dicts(connection.execute(
            """
            select trade_date,limit_up,limit_down,can_buy,can_sell,is_st,source
            from market_trade_status
            where symbol=? and asset_class='equity' and market='china' and venue='china'
              and source='tushare:stk_limit'
            order by trade_date desc limit 200
            """,
            (normalized,),
        ).fetchall()) if selected_market == "china" else []

    listed_dates = [value for value in (security.get("listed_date"), instrument.get("listed_date")) if value]
    name = security.get("name") or instrument.get("name") or normalized
    master_source = str(instrument.get("source") or "") or None
    quote = None
    if quote_row:
        close = float(quote_row.get("close") or 0)
        previous = float(quote_row.get("prev_close") or 0)
        quote = {
            "tradeDate": quote_row.get("trade_date"),
            "open": quote_row.get("open"),
            "high": quote_row.get("high"),
            "low": quote_row.get("low"),
            "close": quote_row.get("close"),
            "previousClose": quote_row.get("prev_close"),
            "change": close - previous if previous else None,
            "pctChange": quote_row.get("pct_change"),
            "volume": quote_row.get("volume"),
            "amount": quote_row.get("amount"),
            "turnoverRate": quote_row.get("turnover_rate"),
            "adjustmentFactor": quote_row.get("adj_factor"),
            "source": quote_row.get("source"),
        }
    return {
        "symbol": normalized,
        "name": name,
        "market": selected_market,
        "marketLabel": MARKET_LABELS.get(selected_market, selected_market),
        "exchange": security.get("exchange") or instrument.get("exchange"),
        "listedDate": min(listed_dates) if listed_dates else None,
        "delistedDate": security.get("delisted_date") or instrument.get("delisted_date"),
        "status": security.get("status") or instrument.get("status"),
        "isSt": bool(security.get("is_st")),
        "industry": security.get("industry"),
        "concepts": _json_list(security.get("concepts")),
        "currency": instrument.get("currency"),
        "lotSize": instrument.get("lot_size"),
        "tickSize": instrument.get("tick_size"),
        "masterSource": master_source,
        "masterUpdatedAt": security.get("updated_at") or instrument.get("updated_at"),
        "hasLocalData": bool(coverage),
        "identifiers": identifiers,
        "coverage": coverage,
        "latestTradeStatus": latest_status,
        "memberships": memberships,
        "quote": quote,
        "adjustmentHistory": adjustment_history,
        "suspensionHistory": suspension_history,
        "limitHistory": limit_history,
    }
