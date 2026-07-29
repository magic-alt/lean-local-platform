from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import db, row_to_dict

router = APIRouter(prefix="/api/compare", tags=["compare"])


class BacktestCompareRequest(BaseModel):
    runIds: list[str] = Field(min_length=2, max_length=20)
    includeCurves: bool = True


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        text = value.replace("%", "").replace(",", "").replace("¥", "").replace("$", "").strip()
        try:
            number = float(text)
        except ValueError:
            return None
        return number / 100.0 if "%" in value else number
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _first_metric(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _metrics(run: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary_metrics") or {}
    statistics = result.get("statistics") or run.get("statistics") or {}
    performance = result.get("performance") or {}
    source = {**statistics, **summary}
    strategy_return = performance.get("strategy_return")
    benchmark_return = performance.get("benchmark_return")
    lean_sharpe = _float(_first_metric(source, "Sharpe Ratio"))
    recomputed_sharpe = _float(performance.get("sharpe_recomputed_from_equity"))
    if recomputed_sharpe is None:
        recomputed_sharpe = _float(_first_metric(source, "Recomputed Sharpe"))
    short_window = performance.get("short_window_unstable")
    if short_window is None:
        short_window = _first_metric(source, "Short Window Unstable")
    return {
        "totalReturn": _float(strategy_return) if strategy_return is not None else _float(_first_metric(source, "Net Profit", "Total Return")),
        "annualReturn": _float(_first_metric(source, "Compounding Annual Return", "Annual Return")),
        "maxDrawdown": abs(_float(_first_metric(source, "Drawdown", "Maximum Drawdown")) or 0),
        "sharpeRatio": recomputed_sharpe if recomputed_sharpe is not None else lean_sharpe,
        "leanSharpeRatio": lean_sharpe,
        "recomputedSharpeRatio": recomputed_sharpe,
        "sharpeMetricStatus": performance.get("sharpe_recompute_status") or _first_metric(source, "Sharpe Metric Status"),
        "shortWindowUnstable": _bool(short_window),
        "sharpeSampleCount": _float(performance.get("sharpe_recomputed_sample_count") or _first_metric(source, "Sharpe Sample Count")),
        "sortinoRatio": _float(_first_metric(source, "Sortino Ratio")),
        "calmarRatio": _float(_first_metric(source, "Calmar Ratio")) or _float(performance.get("calmar")),
        "winRate": _float(_first_metric(source, "Win Rate")),
        "lossRate": _float(_first_metric(source, "Loss Rate")),
        "totalOrders": _float(_first_metric(source, "Total Orders")),
        "totalFees": _float(_first_metric(source, "Total Fees")),
        "benchmarkReturn": _float(benchmark_return),
        "excessReturn": _float(performance.get("excess_return")),
        "alpha": _float(_first_metric(source, "Alpha")) or _float(performance.get("computed_alpha")),
        "beta": _float(_first_metric(source, "Beta")) or _float(performance.get("computed_beta")),
        "informationRatio": _float(_first_metric(source, "Information Ratio")),
    }


def _run_item(run_id: str, include_curves: bool) -> dict[str, Any]:
    with db() as connection:
        run_row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
        result_row = connection.execute("select * from backtest_results where job_id = ?", (run_id,)).fetchone()
    run = row_to_dict(run_row)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Backtest run not found: {run_id}")
    result = row_to_dict(result_row) if result_row is not None else {}
    if run.get("status") != "success":
        raise HTTPException(status_code=409, detail=f"Backtest run is not successful: {run_id}")
    if not result:
        raise HTTPException(status_code=409, detail=f"Parsed backtest result is missing: {run_id}")
    parameters = run.get("parameters") or {}
    market = str(parameters.get("market") or run.get("venue") or "usa").lower()
    currency = str(parameters.get("accountCurrency") or "").upper() or (
        "CNY" if market == "china" else "HKD" if market == "hongkong" else "USD"
    )
    item = {
        "runId": run["id"],
        "name": run.get("name"),
        "symbol": run.get("symbol"),
        "assetClass": run.get("asset_class"),
        "venue": run.get("venue"),
        "status": run.get("status"),
        "projectId": run.get("project_id"),
        "createdAt": run.get("created_at"),
        "finishedAt": run.get("finished_at"),
        "parameters": parameters,
        "currency": currency,
        "resolution": str(parameters.get("resolution") or run.get("resolution") or "daily").lower(),
        "validation": run.get("validation"),
        "experiment": run.get("experiment"),
        "metrics": _metrics(run, result),
        "error": None,
    }
    if include_curves:
        equity_curve = result.get("equity_curve") or []
        item["equityCurve"] = equity_curve
        first_value = next(
            (
                _float(point.get("value"))
                for point in equity_curve
                if isinstance(point, dict) and (_float(point.get("value")) or 0) > 0
            ),
            None,
        )
        item["normalizedEquityCurve"] = [
            {**point, "value": (_float(point.get("value")) or 0) / first_value}
            for point in equity_curve
            if isinstance(point, dict) and first_value
        ]
        item["drawdownCurve"] = result.get("drawdown_curve") or []
    return item


def _rank(items: list[dict[str, Any]], key: str, reverse: bool = True) -> list[str]:
    def metric(item: dict[str, Any]) -> float:
        value = item.get("metrics", {}).get(key)
        return float(value) if value is not None else float("-inf")

    return [item["runId"] for item in sorted(items, key=metric, reverse=reverse)]


@router.post("/backtests")
def compare_backtests(request: BacktestCompareRequest):
    run_ids = list(dict.fromkeys(request.runIds))
    if len(run_ids) != len(request.runIds):
        raise HTTPException(status_code=400, detail="runIds must be unique.")
    items = [_run_item(run_id, request.includeCurves) for run_id in run_ids]
    currencies = sorted({str(item["currency"]) for item in items})
    resolutions = sorted({str(item["resolution"]) for item in items})
    warnings = []
    if len(currencies) > 1:
        warnings.append("Raw NAV values use different currencies; compare normalized curves and percentage metrics only.")
    if len(resolutions) > 1:
        warnings.append("Runs use different resolutions; risk metrics may not be directly comparable.")
    return {
        "items": items,
        "compatibility": {
            "currencies": currencies,
            "resolutions": resolutions,
            "rawNavComparable": len(currencies) == 1,
            "riskMetricComparable": len(resolutions) == 1,
            "warnings": warnings,
        },
        "rankings": {
            "byTotalReturn": _rank(items, "totalReturn"),
            "bySharpe": _rank(items, "sharpeRatio"),
            "byCalmar": _rank(items, "calmarRatio"),
            "byDrawdown": _rank(items, "maxDrawdown", reverse=False),
        },
    }
