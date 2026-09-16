from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..db import utc_now
from ..repositories.backtest_repository import get_backtest, get_result, save_result


SCHEMA_VERSION = "etf-rotation-execution-attribution.v1"


def _number(value: Any, *, percent: bool = False) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1]
    text = re.sub(r"[^0-9eE+\-.]", "", text)
    if not text:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result / 100.0 if is_percent or percent else result


def _find(source: Mapping[str, Any], *aliases: str, percent: bool = False) -> float | None:
    lowered = {str(key).casefold(): value for key, value in source.items()}
    for alias in aliases:
        if alias.casefold() in lowered:
            value = _number(lowered[alias.casefold()], percent=percent)
            if value is not None:
                return value
    return None


def _raw_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    path = result.get("raw_result_path")
    if not path:
        return {}
    candidate = Path(str(path))
    if not candidate.is_file():
        return {}
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _filled_orders(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in result.get("orders") or []:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status and "fill" not in status:
            continue
        quantity = abs(_number(item.get("fillQuantity") or item.get("quantity") or item.get("Quantity")) or 0.0)
        price = _number(item.get("fillPrice") or item.get("price") or item.get("Price")) or 0.0
        if quantity > 0 and price > 0:
            rows.append(dict(item))
    return rows


def _total_filled_notional(result: Mapping[str, Any]) -> float:
    return sum(
        abs(_number(item.get("fillQuantity") or item.get("quantity") or item.get("Quantity")) or 0.0)
        * (_number(item.get("fillPrice") or item.get("price") or item.get("Price")) or 0.0)
        for item in _filled_orders(result)
    )


def _chart_series(raw: Mapping[str, Any], series_name: str) -> list[float]:
    charts = raw.get("Charts") or raw.get("charts") or {}
    if not isinstance(charts, Mapping):
        return []
    values: list[float] = []
    for chart in charts.values():
        if not isinstance(chart, Mapping):
            continue
        series = chart.get("Series") or chart.get("series") or {}
        if not isinstance(series, Mapping):
            continue
        target = next(
            (value for key, value in series.items() if str(key).casefold() == series_name.casefold()),
            None,
        )
        if not isinstance(target, Mapping):
            continue
        points = target.get("Values") or target.get("values") or target.get("Data") or target.get("data") or []
        for point in points:
            raw_value = point.get("y") if isinstance(point, Mapping) else point[1] if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2 else None
            number = _number(raw_value)
            if number is not None:
                values.append(number)
    return values


def _max_drawdown(result: Mapping[str, Any]) -> float | None:
    performance = result.get("performance") if isinstance(result.get("performance"), Mapping) else {}
    summary = result.get("summary_metrics") if isinstance(result.get("summary_metrics"), Mapping) else {}
    statistics = result.get("statistics") if isinstance(result.get("statistics"), Mapping) else {}
    for source in (performance, summary, statistics):
        value = _find(source, "maxDrawdown", "maximum drawdown", "drawdown", "max_drawdown")
        if value is not None:
            return abs(value / 100.0 if value > 1.0 else value)
    curve = result.get("drawdown_curve") or []
    values = []
    for point in curve:
        raw = point.get("value") if isinstance(point, Mapping) else point[1] if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) >= 2 else None
        value = _number(raw)
        if value is not None:
            values.append(abs(value / 100.0 if abs(value) > 1.0 else value))
    return max(values) if values else None


def _normalized_metrics(result: Mapping[str, Any]) -> dict[str, Any]:
    performance = result.get("performance") if isinstance(result.get("performance"), Mapping) else {}
    summary = result.get("summary_metrics") if isinstance(result.get("summary_metrics"), Mapping) else {}
    statistics = result.get("statistics") if isinstance(result.get("statistics"), Mapping) else {}
    sharpe = None
    turnover = None
    trade_count = None
    for source in (performance, summary, statistics):
        if sharpe is None:
            sharpe = _find(source, "sharpe", "sharpe ratio", "sharperatio", "sharpe_recomputed_from_equity")
        if turnover is None:
            turnover = _find(source, "turnover", "portfolio turnover", "portfolioTurnover", "totalTurnover")
        if trade_count is None:
            trade_count = _find(source, "tradeCount", "total trades", "totalTrades", "trades", "total orders")
    if turnover is not None and turnover > 1.0:
        turnover /= 100.0
    if trade_count is None:
        trade_count = float(len(result.get("trades") or _filled_orders(result)))
    return {
        "sharpe": sharpe,
        "maxDrawdown": _max_drawdown(result),
        "turnover": turnover,
        "tradeCount": int(trade_count) if trade_count is not None and trade_count >= 0 and float(trade_count).is_integer() else None,
    }


def _fee_cost(result: Mapping[str, Any], raw: Mapping[str, Any]) -> tuple[float | None, str | None]:
    statistics = result.get("statistics") if isinstance(result.get("statistics"), Mapping) else {}
    summary = result.get("summary_metrics") if isinstance(result.get("summary_metrics"), Mapping) else {}
    for source in (statistics, summary):
        value = _find(source, "Total Fees", "total fees", "fees", "totalFees")
        if value is not None:
            return abs(value), "lean_statistics_total_fees"
    events = raw.get("OrderEvents") or raw.get("orderEvents") or []
    total = 0.0
    seen = False
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, Mapping):
                continue
            fee = event.get("OrderFee") or event.get("orderFee") or event.get("Fee") or event.get("fee")
            if isinstance(fee, Mapping):
                fee = fee.get("Value") or fee.get("value") or (fee.get("Amount") or {}).get("Amount") if isinstance(fee.get("Amount"), Mapping) else fee.get("Amount")
            value = _number(fee)
            if value is not None:
                total += abs(value)
                seen = True
    return (total, "lean_order_events") if seen else (None, None)


def _cash_drag(raw: Mapping[str, Any]) -> tuple[float | None, str | None]:
    exposure = _chart_series(raw, "GrossExposure")
    if not exposure:
        return None, None
    fractions = [max(0.0, 1.0 - min(max(value, 0.0), 1.0)) for value in exposure]
    return sum(fractions) / len(fractions), "lean_strategy_gross_exposure_chart_average_cash_fraction"


def _capacity_impact(run: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[float | None, str | None]:
    statistics = result.get("statistics") if isinstance(result.get("statistics"), Mapping) else {}
    summary = result.get("summary_metrics") if isinstance(result.get("summary_metrics"), Mapping) else {}
    capacity = None
    for source in (statistics, summary):
        capacity = _find(source, "Estimated Strategy Capacity", "estimatedStrategyCapacity", "strategy capacity")
        if capacity is not None:
            break
    if capacity is None or capacity <= 0:
        return None, None
    parameters = run.get("parameters") if isinstance(run.get("parameters"), Mapping) else {}
    initial_cash = _number(parameters.get("initialCash") or parameters.get("initial_cash") or parameters.get("cash"))
    if initial_cash is None or initial_cash <= 0:
        return None, None
    return initial_cash / capacity, "initial_capital_over_lean_estimated_strategy_capacity"


def build_execution_attribution(run: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    raw = _raw_payload(result)
    parameters = run.get("parameters") if isinstance(run.get("parameters"), Mapping) else {}
    fees, fee_source = _fee_cost(result, raw)
    filled_notional = _total_filled_notional(result)
    slippage_bps = _number(parameters.get("slippageBps"))
    slippage = filled_notional * slippage_bps / 10000.0 if slippage_bps is not None else None
    cash_drag, cash_drag_source = _cash_drag(raw)
    capacity_impact, capacity_source = _capacity_impact(run, result)
    metrics = _normalized_metrics(result)
    attribution = {
        "schemaVersion": SCHEMA_VERSION,
        "fees": fees,
        "slippage": slippage,
        "cashDrag": cash_drag,
        "capacityImpact": capacity_impact,
        "complete": all(value is not None for value in (fees, slippage, cash_drag, capacity_impact)),
        "sources": {
            "fees": fee_source,
            "slippage": "configured_constant_bps_on_actual_filled_notional" if slippage is not None else None,
            "cashDrag": cash_drag_source,
            "capacityImpact": capacity_source,
        },
        "inputs": {
            "filledNotional": filled_notional,
            "slippageBps": slippage_bps,
            "estimatedCapacityUtilizationUnits": "initial_capital/estimated_capacity",
        },
    }
    return {"metrics": metrics, "executionAttribution": attribution, "complete": attribution["complete"] and all(value is not None for value in metrics.values())}


def materialize_execution_attribution(run_id: str) -> dict[str, Any]:
    run = get_backtest(run_id)
    result = get_result(run_id)
    if not run or not result:
        return {"runId": run_id, "complete": False, "reason": "backtest_result_missing"}
    built = build_execution_attribution(run, result)
    performance = dict(result.get("performance") or {})
    performance.update({key: value for key, value in built["metrics"].items() if value is not None})
    performance["executionAttribution"] = built["executionAttribution"]
    save_result(
        run_id,
        {
            "id": result.get("id"),
            "summary_metrics": result.get("summary_metrics") or {},
            "equity_curve": result.get("equity_curve") or [],
            "drawdown_curve": result.get("drawdown_curve") or [],
            "orders": result.get("orders") or [],
            "trades": result.get("trades") or [],
            "holdings": result.get("holdings") or [],
            "statistics": result.get("statistics") or {},
            "performance": performance,
            "raw_result_path": result.get("raw_result_path"),
            "raw_result_object_id": result.get("raw_result_object_id"),
            "summary_object_id": result.get("summary_object_id"),
        },
        result.get("created_at") or utc_now(),
    )
    return {
        "runId": run_id,
        **built,
    }
