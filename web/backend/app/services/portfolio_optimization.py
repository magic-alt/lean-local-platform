from __future__ import annotations

import itertools
import math
from datetime import datetime
from typing import Any

from ..db import db, row_to_dict
from .strategy_admission import parameters_sha256


def _date_key(value: Any) -> str:
    return str(value or "")[:10]


def _load_nav(run_id: str) -> tuple[dict[str, Any], dict[str, float]]:
    with db() as connection:
        row = connection.execute(
            """
            select br.id, br.project_id, br.status, br.parameters_json, result.equity_curve_json
            from backtest_runs br
            left join backtest_results result on result.job_id = br.id
            where br.id = ?
            """,
            (run_id,),
        ).fetchone()
    item = row_to_dict(row)
    if not item:
        raise KeyError(f"Backtest run not found: {run_id}")
    if item.get("status") not in {"success", "succeeded"}:
        raise ValueError(f"Backtest run {run_id} is not successful.")
    parameter_hash = parameters_sha256(item.get("parameters") or {})
    with db() as connection:
        admission = connection.execute(
            """
            select id from strategy_admissions
            where strategy_id = ? and parameters_sha256 = ? and current_stage in ('admission_passed', 'paper_validated')
            order by updated_at desc limit 1
            """,
            (item.get("project_id"), parameter_hash),
        ).fetchone()
    if not admission:
        raise ValueError(f"Backtest run {run_id} has not passed strategy admission.")
    curve: dict[str, float] = {}
    for point in item.get("equity_curve") or []:
        date = _date_key(point.get("time") or point.get("date"))
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if date and math.isfinite(value) and value > 0:
            curve[date] = value
    if len(curve) < 3:
        raise ValueError(f"Backtest run {run_id} has insufficient NAV history.")
    return item, curve


def _returns(curve: dict[str, float], dates: list[str]) -> list[float]:
    values = [curve[date] for date in dates]
    return [current / previous - 1.0 for previous, current in zip(values, values[1:]) if previous > 0]


def _metrics(returns: list[float]) -> dict[str, float]:
    if not returns:
        raise ValueError("Portfolio has no aligned return points.")
    average = sum(returns) / len(returns)
    variance = sum((value - average) ** 2 for value in returns) / max(1, len(returns) - 1)
    volatility = math.sqrt(variance)
    nav = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in returns:
        nav *= 1.0 + value
        peak = max(peak, nav)
        max_drawdown = max(max_drawdown, 1.0 - nav / peak)
    annual_return = nav ** (252.0 / len(returns)) - 1.0 if nav > 0 else -1.0
    return {
        "totalReturn": nav - 1.0,
        "annualReturn": annual_return,
        "annualVolatility": volatility * math.sqrt(252.0),
        "sharpe": average / volatility * math.sqrt(252.0) if volatility > 1e-18 else 0.0,
        "maxDrawdown": max_drawdown,
    }


def _weight_grid(count: int, step: float, max_weight: float) -> list[tuple[float, ...]]:
    units = round(1.0 / step)
    if abs(units * step - 1.0) > 1e-9:
        raise ValueError("step must divide 1.0 exactly.")
    max_units = math.floor(max_weight / step + 1e-9)
    candidates = [
        tuple(value * step for value in weights)
        for weights in itertools.product(range(max_units + 1), repeat=count)
        if sum(weights) == units
    ]
    if not candidates:
        raise ValueError("No feasible weight combination satisfies step and maxWeight.")
    if len(candidates) > 100000:
        raise ValueError("Weight grid exceeds 100000 candidates; increase step or reduce runIds.")
    return candidates


def optimize_portfolio(
    run_ids: list[str],
    *,
    objective: str = "sharpe",
    step: float = 0.1,
    max_weight: float = 1.0,
    allow_short: bool = False,
) -> dict[str, Any]:
    if allow_short:
        raise ValueError("Short portfolio weights are not enabled in the trusted research profile.")
    if not 2 <= len(run_ids) <= 5:
        raise ValueError("Portfolio optimization requires between 2 and 5 runIds.")
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("runIds must be unique.")
    if objective not in {"sharpe", "return", "drawdown"}:
        raise ValueError("objective must be sharpe, return, or drawdown.")
    if not 0 < step <= 0.5:
        raise ValueError("step must be greater than 0 and no more than 0.5.")
    if not 0 < max_weight <= 1:
        raise ValueError("maxWeight must be in (0, 1].")
    loaded = [_load_nav(run_id) for run_id in run_ids]
    common_dates = sorted(set.intersection(*(set(curve) for _, curve in loaded)))
    if len(common_dates) < 3:
        raise ValueError("runIds have fewer than three aligned NAV dates.")
    return_series = [_returns(curve, common_dates) for _, curve in loaded]
    candidates = []
    for weights in _weight_grid(len(run_ids), step, max_weight):
        combined = [
            sum(weights[index] * series[offset] for index, series in enumerate(return_series))
            for offset in range(len(common_dates) - 1)
        ]
        metrics = _metrics(combined)
        score = metrics["sharpe"] if objective == "sharpe" else metrics["annualReturn"] if objective == "return" else -metrics["maxDrawdown"]
        candidates.append((score, weights, metrics, combined))
    _, best_weights, best_metrics, best_returns = max(candidates, key=lambda item: item[0])
    nav = 1.0
    curve = [{"time": common_dates[0], "value": nav}]
    for date, value in zip(common_dates[1:], best_returns):
        nav *= 1.0 + value
        curve.append({"time": date, "value": nav})
    return {
        "schemaVersion": 1,
        "objective": objective,
        "runIds": run_ids,
        "weights": {run_id: best_weights[index] for index, run_id in enumerate(run_ids)},
        "metrics": best_metrics,
        "alignedStart": common_dates[0],
        "alignedEnd": common_dates[-1],
        "alignedPoints": len(common_dates),
        "candidateCount": len(candidates),
        "equityCurve": curve,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

