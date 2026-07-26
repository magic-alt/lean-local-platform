from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.errors import LeanWebError
from ..domain.assets import (
    AssetRequest,
    asset_class_key,
    asset_request,
    data_type_key,
    parse_lean_zip_ohlcv_series,
    parse_lean_zip_price_series,
    resolution_key,
)
from .symbols import market_key, normalize_symbol, parse_date

def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def extract_statistics(result_json: Path, summary_json: Path | None = None) -> dict[str, Any]:
    source = summary_json if summary_json and summary_json.exists() else result_json
    if not source.exists():
        return {}
    data = load_json(source)
    return data.get("statistics") or data.get("Statistics") or {}


def point_series(chart: dict[str, Any], name: str) -> list[dict[str, Any]]:
    series = (chart.get("series") or {}).get(name) or {}
    points = []
    for row in series.get("values", []):
        if len(row) < 2:
            continue
        timestamp = float(row[0])
        value = float(row[-1])
        if math.isfinite(timestamp) and math.isfinite(value):
            points.append(
                {
                    "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                    "value": value,
                }
            )
    return points


def read_lean_daily_price_series(
    symbol: str,
    market: str | None = None,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> list[dict[str, Any]]:
    start_date = parse_date(start) if start else None
    end_date = parse_date(end) if end else None
    try:
        if asset_class_key(asset_class or "equity") == "equity":
            market_value = market_key(market or venue)
            request = AssetRequest("equity", normalize_symbol(symbol, market_value).upper(), market_value, resolution_key(resolution), data_type_key(data_type))
        else:
            request = asset_request(symbol, asset_class, venue=venue or market, resolution=resolution, data_type=data_type)
    except LeanWebError:
        return []
    return parse_lean_zip_price_series(request, start_date, end_date)


def read_lean_daily_candle_series(
    symbol: str,
    market: str | None = None,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> list[dict[str, Any]]:
    start_date = parse_date(start) if start else None
    end_date = parse_date(end) if end else None
    try:
        if asset_class_key(asset_class or "equity") == "equity":
            market_value = market_key(market or venue)
            request = AssetRequest("equity", normalize_symbol(symbol, market_value).upper(), market_value, resolution_key(resolution), data_type_key(data_type))
        else:
            request = asset_request(symbol, asset_class, venue=venue or market, resolution=resolution, data_type=data_type)
    except LeanWebError:
        return []
    return parse_lean_zip_ohlcv_series(request, start_date, end_date)


def _has_moving_values(points: list[dict[str, Any]]) -> bool:
    values = {round(float(point["value"]), 8) for point in points if point.get("value") not in (None, 0)}
    return len(values) > 1


def _cumulative_return_series(
    points: list[dict[str, Any]],
    *,
    ignore_zero_values: bool = False,
) -> list[dict[str, Any]]:
    """Rebase a value curve to decimal cumulative returns starting at zero."""
    base_item = next(
        (
            (index, float(point["value"]))
            for index, point in enumerate(points)
            if point.get("value") is not None
            and math.isfinite(float(point["value"]))
            and float(point["value"]) != 0
        ),
        None,
    )
    if base_item is None:
        return []
    base_index, base = base_item
    return [
        {
            "time": point["time"],
            "value": (float(point["value"]) / base) - 1.0,
        }
        for point in points[base_index:]
        if point.get("time")
        and point.get("value") is not None
        and math.isfinite(float(point["value"]))
        and (not ignore_zero_values or float(point["value"]) != 0)
    ]


FILLED_ORDER_STATUSES = {2, 3}
FILLED_ORDER_STATUS_LABELS = {"filled", "partiallyfilled", "partialfilled", "partially"}
NON_FILLED_ORDER_STATUS_LABELS = {"submitted", "invalid", "canceled", "cancelled", "rejected"}


def _normalize_order_status(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(float(value)):
            return None
        int_value = int(value)
        if int_value == value:
            return int_value
    text = str(value).strip()
    try:
        numeric = float(text)
    except (TypeError, ValueError):
        numeric = None
    if numeric is not None and numeric.is_integer():
        return int(numeric)
    text = str(value).strip().lower().replace("-", "").replace("_", "")
    return text


def _is_filled_order(order: dict[str, Any]) -> bool:
    status = _normalize_order_status(order.get("status"))
    if status is None:
        return True
    if isinstance(status, int):
        return status in FILLED_ORDER_STATUSES
    if isinstance(status, str):
        if status in NON_FILLED_ORDER_STATUS_LABELS:
            return False
        if status in FILLED_ORDER_STATUS_LABELS:
            return True
    return True


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _nearest_value(points: list[dict[str, Any]], time_value: str | None) -> float | None:
    target = _parse_time(time_value)
    if target is None or not points:
        return None
    nearest = min(
        points,
        key=lambda point: abs((_parse_time(point.get("time")) or target) - target),
    )
    return float(nearest["value"])


def infer_holdings_from_orders(
    orders: list[dict[str, Any]],
    price_series: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def _order_time(order: dict[str, Any]) -> datetime:
        return _parse_time(order.get("time")) or datetime.min.replace(tzinfo=timezone.utc)

    sorted_orders = sorted(orders, key=_order_time)
    lots_by_symbol: dict[str, list[dict[str, float]]] = {}
    last_times: dict[str, datetime] = {}
    for order in sorted_orders:
        symbol = order.get("symbol") or ""
        quantity = float(order.get("quantity") or 0)
        price = float(order.get("price") or 0)
        time_value = _order_time(order)
        if not symbol or quantity == 0:
            continue
        lots_by_symbol.setdefault(symbol, [])
        last_times[symbol] = time_value
        lots = lots_by_symbol[symbol]
        if quantity > 0:
            remaining = quantity
            while remaining > 0 and lots and lots[0]["quantity"] < 0:
                lot = lots[0]
                used = min(remaining, -lot["quantity"])
                lot["quantity"] += used
                remaining -= used
                if lot["quantity"] >= 0:
                    lots.pop(0)
            if remaining > 0:
                lots.append({"quantity": remaining, "price": price})
            continue
        remaining = -quantity
        while remaining > 0 and lots and lots[0]["quantity"] > 0:
            lot = lots[0]
            used = min(remaining, lot["quantity"])
            lot["quantity"] -= used
            remaining -= used
            if lot["quantity"] <= 0:
                lots.pop(0)
        if remaining > 0 and not lots:
            lots.append({"quantity": -remaining, "price": price})

    holdings: list[dict[str, Any]] = []
    for symbol, lots in lots_by_symbol.items():
        quantity = sum(lot["quantity"] for lot in lots)
        if abs(quantity) <= 1e-12:
            continue
        long_value = sum(lot["quantity"] * lot["price"] for lot in lots if lot["quantity"] > 0)
        short_value = sum(lot["quantity"] * lot["price"] for lot in lots if lot["quantity"] < 0)
        net_cost = long_value + short_value
        long_quantity = sum(lot["quantity"] for lot in lots if lot["quantity"] > 0)
        short_quantity = sum(lot["quantity"] for lot in lots if lot["quantity"] < 0)
        if quantity > 0 and long_quantity > 0:
            average_price = long_value / long_quantity
        elif quantity < 0 and short_quantity < 0:
            average_price = short_value / short_quantity
        else:
            average_price = 0
        latest_time = last_times.get(symbol)
        time_key = latest_time.isoformat() if latest_time else None
        market_price = _nearest_value(price_series, time_key) or 0
        market_value = quantity * market_price if market_price else 0
        holdings.append(
            {
                "time": time_key,
                "symbol": symbol,
                "quantity": quantity,
                "averagePrice": average_price,
                "marketPrice": market_price,
                "marketValue": market_value,
                "netCost": net_cost,
            }
        )
    return holdings


def extract_chart_data(
    result_json: Path,
    symbol: str | None = None,
    benchmark_symbol: str | None = None,
    market: str | None = None,
    benchmark_market: str | None = None,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> dict[str, Any]:
    data = load_json(result_json)
    charts = data.get("charts") or {}
    equity = charts.get("Strategy Equity") or {}
    drawdown = charts.get("Drawdown") or {}
    ema = charts.get("EMA") or {}
    benchmark = charts.get("Benchmark") or {}

    raw_orders = []
    orders_payload = data.get("orders") or data.get("Orders") or {}
    order_rows = list(orders_payload.values()) if isinstance(orders_payload, dict) else list(orders_payload) if isinstance(orders_payload, list) else []
    for order in order_rows:
        if not isinstance(order, dict):
            continue
        symbol_payload = order.get("symbol") or order.get("Symbol") or order.get("symbolValue") or order.get("symbolPermtick")
        symbol = ""
        if isinstance(symbol_payload, dict):
            symbol = (
                symbol_payload.get("value")
                or symbol_payload.get("Value")
                or symbol_payload.get("Symbol")
                or symbol_payload.get("symbol")
                or ""
            )
        elif symbol_payload is not None:
            symbol = str(symbol_payload)
        quantity = float(order.get("quantity", order.get("Quantity", 0)))
        time_value = (
            order.get("lastFillTime")
            or order.get("LastFillTime")
            or order.get("time")
            or order.get("Time")
            or order.get("orderTime")
        )
        price = float(
            order.get("fillPrice", order.get("FillPrice", order.get("price", order.get("Price", 0))))
        )
        raw_orders.append(
            {
                "time": time_value,
                "side": "BUY" if quantity > 0 else "SELL",
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "tag": order.get("tag") or "",
                "status": _normalize_order_status(order.get("status")),
            }
        )
    orders = [order for order in raw_orders if _is_filled_order(order)]

    inferred_symbol = symbol or next((order["symbol"] for order in orders if order["symbol"]), None)
    candles = (
        read_lean_daily_candle_series(
            inferred_symbol,
            market,
            start,
            end,
            asset_class=asset_class,
            venue=venue,
            resolution=resolution,
            data_type=data_type,
        )
        if inferred_symbol
        else []
    )
    price = [{"time": row["time"], "value": row["close"]} for row in candles]
    benchmark_series = point_series(benchmark, "Benchmark")
    benchmark_source = "lean_result"
    if benchmark_symbol and not _has_moving_values(benchmark_series):
        cache_series = read_lean_daily_price_series(
            benchmark_symbol,
            benchmark_market or market,
            start,
            end,
            asset_class=asset_class,
            venue=benchmark_market or venue or market,
            resolution=resolution,
            data_type=data_type,
        )
        if _has_moving_values(cache_series):
            benchmark_series = cache_series
            benchmark_source = "lean_data_cache"
    equity_series = point_series(equity, "Equity")
    cumulative_return_series = _cumulative_return_series(equity_series)
    benchmark_return_series = (
        _cumulative_return_series(benchmark_series, ignore_zero_values=True)
        if _has_moving_values(benchmark_series)
        else []
    )
    excluded_indicator_charts = {
        "Strategy Equity",
        "Drawdown",
        "Benchmark",
        "Portfolio Turnover",
        "Exposure",
        "Capacity",
        "Assets Sales Volume",
        "Portfolio Margin",
    }
    indicators = []
    for chart_name, chart in charts.items():
        if chart_name in excluded_indicator_charts or not isinstance(chart, dict):
            continue
        for series_name in (chart.get("series") or {}):
            points = point_series(chart, series_name)
            if points:
                indicators.append({"chart": chart_name, "name": series_name, "points": points})

    order_markers = [
        {
            **order,
            "fillPrice": order["price"],
            "priceValue": order["price"] or _nearest_value(price, order["time"]),
            "equityValue": _nearest_value(equity_series, order["time"]),
        }
        for order in orders
    ]

    return {
        "statistics": data.get("statistics") or {},
        "candles": candles,
        "indicators": indicators,
        "series": {
            "equity": equity_series,
            "return": point_series(equity, "Return"),
            "cumulativeReturn": cumulative_return_series,
            "drawdown": point_series(drawdown, "Equity Drawdown"),
            "emaFast": point_series(ema, "Fast"),
            "emaSlow": point_series(ema, "Slow"),
            "benchmark": benchmark_series,
            "benchmarkReturn": benchmark_return_series,
            "price": price,
        },
        "seriesSources": {
            "benchmark": benchmark_source,
            "benchmarkStatus": "available" if benchmark_return_series else "unavailable",
        },
        "metadata": {
            "benchmarkSymbol": benchmark_symbol,
            "comparisonBasis": "cumulative_return",
        },
        "orders": orders,
        "orderMarkers": order_markers,
        "holdings": infer_holdings_from_orders(orders, price_series=price),
    }
