from __future__ import annotations

from pathlib import Path
from typing import Any

from ..db import utc_now
from ..lean import extract_chart_data, extract_statistics, load_json
from ..repositories.backtest_repository import get_result, save_result


SUMMARY_KEYS = [
    "Net Profit",
    "Compounding Annual Return",
    "Drawdown",
    "Sharpe Ratio",
    "Sortino Ratio",
    "Probabilistic Sharpe Ratio",
    "Loss Rate",
    "Win Rate",
    "Total Orders",
    "Average Win",
    "Average Loss",
    "Alpha",
    "Beta",
    "Annual Standard Deviation",
    "Annual Variance",
    "Information Ratio",
    "Tracking Error",
    "Treynor Ratio",
    "Total Fees",
]


def _values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def summary_metrics(statistics: dict[str, Any]) -> dict[str, Any]:
    return {key: statistics[key] for key in SUMMARY_KEYS if key in statistics}


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
    return {
        "summary_metrics": summary_metrics(statistics),
        "statistics": statistics,
        "equity_curve": chart_data["series"].get("equity") or [],
        "drawdown_curve": chart_data["series"].get("drawdown") or [],
        "orders": chart_data.get("orders") or [],
        "trades": trades,
        "holdings": holdings,
        "charts": chart_data["series"],
        "order_markers": chart_data.get("orderMarkers") or [],
        "raw_result_path": str(result_json),
    }


def persist_result(job_id: str, result_json: Path, summary_json: Path | None, run: dict[str, Any]) -> dict[str, Any]:
    payload = parse_result_payload(result_json, summary_json, run)
    return save_result(job_id, payload, utc_now())


def result_for_job(job_id: str) -> dict[str, Any] | None:
    return get_result(job_id)
