from __future__ import annotations

import json
import logging
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts
from ..lean_engine.symbols import market_key, normalize_symbol
from .security_search import MARKET_LABELS
from . import market_lake


logger = logging.getLogger(__name__)


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
    try:
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
                    ("corporate_actions", "公司行动", "corporate_actions", "ex_date", ""),
                    ("factor_values", "每日指标/因子", "factor_values", "trade_date", ""),
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
            memberships = rows_to_dicts(connection.execute(
            """
            select universe_code, start_date, end_date, weight, source
            from universe_membership where symbol = ?
            order by coalesce(end_date, '9999-12-31') desc, start_date desc limit 50
            """,
            (normalized,),
            ).fetchall()) if selected_market == "china" else []
    except Exception as exc:
        # Quote reads must remain usable when only the local market lake is
        # configured. SQL master data is optional enrichment for this view, so
        # an old partially migrated metadata table must not break Preview.
        logger.warning("security metadata enrichment unavailable for %s: %s", normalized, exc)
        security, instrument, identifiers, coverage, memberships = {}, {}, [], [], []
    bars = market_lake.query_matching(
        kind="bars", asset_class="equity", market=selected_market,
        resolution="daily", data_type="trade", adjust="raw",
        predicates=("symbol=?",), parameters=(normalized,), order_by="trade_date desc,source asc", limit=1,
        recent_partitions=5,
    )
    status_rows = market_lake.query_matching(
        kind="trade_status", asset_class="equity", market=selected_market,
        predicates=("symbol=?",), parameters=(normalized,), order_by="trade_date desc,updated_at desc", limit=200,
        recent_partitions=512,
    ) if selected_market == "china" else []
    adjustments = market_lake.query_matching(
        kind="adjustment_factor", predicates=("symbol=?",), parameters=(normalized,),
        order_by="trade_date desc,source desc", limit=200,
        recent_partitions=512,
    ) if selected_market == "china" else []
    for key, label, items in (
        ("daily", "日线行情", bars),
        ("trade_status", "交易状态/涨跌停", status_rows),
        ("adjustment_factors", "复权因子", adjustments),
    ):
        if items:
            dates = sorted(str(item["trade_date"])[:10] for item in items)
            coverage.append({"key": key, "label": label, "rows": len(items),
                             "firstDate": dates[0], "lastDate": dates[-1],
                             "sources": sorted({str(item["source"]) for item in items if item.get("source")})})
    latest_status = status_rows[0] if status_rows else None
    tushare_bars = [item for item in bars if item.get("source") == "tushare"]
    quote_row = (tushare_bars or bars)[0] if bars else None
    adjustment_history = adjustments
    suspension_history = [item for item in status_rows if item.get("source") == "tushare:suspend_d"][:200]
    limit_history = [item for item in status_rows if item.get("source") == "tushare:stk_limit"][:200]

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
