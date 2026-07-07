from __future__ import annotations

from pathlib import Path
from typing import Any

from ..analyzers.performance_analyzer import performance_analytics, summary_with_benchmark_metrics
from ..lean_engine.results import extract_chart_data, extract_statistics, load_json


def _values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def parse_result_payload(
    result_json: Path,
    summary_json: Path | None = None,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = run or {}
    data = load_json(result_json)
    parameters = run.get("parameters") or {}
    chart_data = extract_chart_data(
        result_json,
        symbol=run.get("symbol"),
        market=parameters.get("market"),
        start=parameters.get("start"),
        end=parameters.get("end"),
        asset_class=parameters.get("assetClass"),
        venue=parameters.get("venue"),
        resolution=parameters.get("resolution"),
        data_type=parameters.get("dataType"),
    )
    statistics = extract_statistics(result_json, summary_json)
    if not statistics:
        statistics = chart_data.get("statistics") or {}
    order_events = _values(data.get("orderEvents") or data.get("order-events") or data.get("OrderEvents"))
    holdings = _values(data.get("holdings") or data.get("Holdings"))
    trades = order_events or chart_data.get("orders") or []
    performance = performance_analytics(statistics, chart_data, order_events, data)
    if run.get("validation"):
        performance["validation"] = run.get("validation")
    if run.get("experiment"):
        performance["experiment"] = run.get("experiment")
    if performance.get("calmar") is not None:
        statistics.setdefault("Calmar Ratio", f"{performance['calmar']:.3f}")
    return {
        "summary_metrics": summary_with_benchmark_metrics(statistics, performance),
        "statistics": statistics,
        "performance": performance,
        "equity_curve": chart_data["series"].get("equity") or [],
        "drawdown_curve": chart_data["series"].get("drawdown") or [],
        "orders": chart_data.get("orders") or [],
        "trades": trades,
        "holdings": holdings,
        "charts": chart_data["series"],
        "order_markers": chart_data.get("orderMarkers") or [],
        "raw_result_path": str(result_json),
    }
