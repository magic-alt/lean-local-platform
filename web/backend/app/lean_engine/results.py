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


def _has_moving_values(points: list[dict[str, Any]]) -> bool:
    values = {round(float(point["value"]), 8) for point in points if point.get("value") not in (None, 0)}
    return len(values) > 1


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

    orders = []
    for order in (data.get("orders") or {}).values():
        quantity = float(order.get("quantity", 0))
        time_value = order.get("lastFillTime") or order.get("time")
        orders.append(
            {
                "time": time_value,
                "side": "BUY" if quantity > 0 else "SELL",
                "symbol": ((order.get("symbol") or {}).get("value") or ""),
                "quantity": quantity,
                "price": float(order.get("price") or 0),
                "tag": order.get("tag") or "",
            }
        )

    inferred_symbol = symbol or next((order["symbol"] for order in orders if order["symbol"]), None)
    price = (
        read_lean_daily_price_series(
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
    order_markers = [
        {
            **order,
            "fillPrice": order["price"],
            "priceValue": _nearest_value(price, order["time"]) or order["price"],
            "equityValue": _nearest_value(equity_series, order["time"]),
        }
        for order in orders
    ]

    return {
        "statistics": data.get("statistics") or {},
        "series": {
            "equity": equity_series,
            "return": point_series(equity, "Return"),
            "drawdown": point_series(drawdown, "Equity Drawdown"),
            "emaFast": point_series(ema, "Fast"),
            "emaSlow": point_series(ema, "Slow"),
            "benchmark": benchmark_series,
            "price": price,
        },
        "seriesSources": {"benchmark": benchmark_source},
        "orders": orders,
        "orderMarkers": order_markers,
    }
