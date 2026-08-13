from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ..services.source_gate import resolve_source_context
from ..services import market_lake


class MarketDataUnavailable(RuntimeError):
    """Raised when a certified point-in-time valuation input is unavailable."""


def _date(value: str, field: str) -> str:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date.") from exc


def close_price(
    symbol: str,
    as_of: str,
    *,
    source: str | None,
    allow_research_source: bool = False,
    asset_class: str = "equity",
    market: str = "china",
) -> dict[str, Any]:
    as_of_date = _date(as_of, "as_of")
    normalized_asset_class = str(asset_class).strip().lower()
    if normalized_asset_class not in {"equity", "index"}:
        raise ValueError(f"Unsupported daily close asset class: {asset_class}")
    try:
        context = resolve_source_context(
            {},
            source=source,
            allow_research_source=allow_research_source,
            asset_class=normalized_asset_class,
            market=market,
            venue=market,
        )
    except ValueError as exc:
        raise MarketDataUnavailable(str(exc)) from exc
    rows = market_lake.query_rows(
        kind="bars", asset_class=normalized_asset_class, market=market, venue=market,
        resolution="daily", data_type="trade", adjust="raw", source=str(context["source"]),
        columns="symbol,trade_date,close,source,asset_class",
        predicates=("symbol=?", "trade_date<=?", "close is not null"),
        parameters=(str(symbol).upper(), as_of_date), order_by="trade_date desc", limit=1,
    )
    if not rows:
        raise MarketDataUnavailable(
            f"market_data_unavailable:{str(symbol).upper()}:{as_of_date}:{context['source']}"
        )
    row = rows[0]
    price = Decimal(str(row["close"]))
    if not price.is_finite() or price <= 0:
        raise MarketDataUnavailable(
            f"market_price_invalid:{str(symbol).upper()}:{row['trade_date']}:{context['source']}"
        )
    return {
        "symbol": str(row["symbol"]),
        "tradeDate": str(row["trade_date"]),
        "close": price,
        "source": str(row["source"]),
        "assetClass": str(row["asset_class"]),
        "datasetVersion": context.get("datasetVersion"),
    }


def benchmark_return(
    symbol: str,
    start: str,
    end: str,
    *,
    source: str | None,
    allow_research_source: bool = False,
    market: str = "china",
) -> dict[str, Any]:
    start_date = _date(start, "start")
    end_date = _date(end, "end")
    if start_date > end_date:
        raise ValueError("Benchmark start must not be after end.")
    opening = close_price(
        symbol,
        start_date,
        source=source,
        allow_research_source=allow_research_source,
        asset_class="index",
        market=market,
    )
    closing = close_price(
        symbol,
        end_date,
        source=source,
        allow_research_source=allow_research_source,
        asset_class="index",
        market=market,
    )
    if opening["tradeDate"] != start_date:
        raise MarketDataUnavailable(
            f"benchmark_data_unavailable:{str(symbol).upper()}:{start_date}:{opening['source']}"
        )
    if closing["tradeDate"] != end_date:
        raise MarketDataUnavailable(
            f"benchmark_data_unavailable:{str(symbol).upper()}:{end_date}:{closing['source']}"
        )
    value = closing["close"] / opening["close"] - Decimal("1")
    return {
        "symbol": str(symbol).upper(),
        "startDate": start_date,
        "endDate": end_date,
        "openingDate": opening["tradeDate"],
        "closingDate": closing["tradeDate"],
        "openingClose": opening["close"],
        "closingClose": closing["close"],
        "return": value,
        "source": opening["source"],
        "datasetVersion": opening.get("datasetVersion"),
    }
