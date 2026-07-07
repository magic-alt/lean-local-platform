from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ..services.ashare_repository import get_security

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
    "Calmar Ratio",
    "Portfolio Turnover",
]

SHARPE_ANNUALIZATION_FACTOR = 252
SHORT_WINDOW_SHARPE_MIN_RETURNS = 60


def _values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def summary_metrics(statistics: dict[str, Any]) -> dict[str, Any]:
    return {key: statistics[key] for key in SUMMARY_KEYS if key in statistics}


def _dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        clean = value.replace("%", "").replace(",", "").replace("¥", "").strip()
        try:
            number = float(clean)
        except ValueError:
            return None
        return number / 100.0 if "%" in value else number
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _period_returns(equity_curve: list[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    if not equity_curve:
        return []
    grouped: dict[str, dict[str, Any]] = {}
    for point in equity_curve:
        time_value = _dt(point.get("time"))
        value = _float(point.get("value"))
        if time_value is None or value is None:
            continue
        key = time_value.strftime("%Y-%m") if period == "month" else time_value.strftime("%Y")
        item = grouped.setdefault(key, {"period": key, "start": value, "end": value})
        item["end"] = value
    rows = []
    for key in sorted(grouped):
        item = grouped[key]
        start = item["start"]
        end = item["end"]
        rows.append({"period": key, "return": (end / start - 1.0) if start else 0.0, "start": start, "end": end})
    return rows


def _filled_events(order_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filled = []
    for event in order_events:
        status = str(event.get("status") or "").lower()
        quantity = _float(event.get("fillQuantity") if "fillQuantity" in event else event.get("quantity")) or 0
        price = _float(event.get("fillPrice") if "fillPrice" in event else event.get("price")) or 0
        if status and status != "filled":
            continue
        if quantity == 0 or price <= 0:
            continue
        filled.append(
            {
                **event,
                "time": event.get("time"),
                "symbol": event.get("symbolValue") or event.get("symbolPermtick") or event.get("symbol") or "",
                "quantity": quantity,
                "price": price,
                "fee": _float(event.get("orderFeeAmount")) or 0.0,
            }
        )
    return sorted(filled, key=lambda item: _dt(item.get("time")) or datetime.min.replace(tzinfo=timezone.utc))


def _trade_pairs(filled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lots: dict[str, list[dict[str, Any]]] = {}
    trades: list[dict[str, Any]] = []
    for event in filled:
        symbol = str(event["symbol"])
        quantity = float(event["quantity"])
        time_value = _dt(event.get("time"))
        if quantity > 0:
            lots.setdefault(symbol, []).append({**event, "remaining": quantity})
            continue
        remaining_sell = abs(quantity)
        while remaining_sell > 0 and lots.get(symbol):
            lot = lots[symbol][0]
            matched = min(remaining_sell, lot["remaining"])
            gross = (event["price"] - lot["price"]) * matched
            fees = event["fee"] * (matched / abs(quantity)) + lot["fee"] * (matched / lot["quantity"])
            entry_time = _dt(lot.get("time"))
            hold_days = (time_value - entry_time).days if time_value and entry_time else None
            cost = lot["price"] * matched
            trades.append(
                {
                    "symbol": symbol,
                    "entry_time": lot.get("time"),
                    "exit_time": event.get("time"),
                    "quantity": matched,
                    "entry_price": lot["price"],
                    "exit_price": event["price"],
                    "gross_pnl": gross,
                    "fees": fees,
                    "net_pnl": gross - fees,
                    "return": (gross - fees) / cost if cost else None,
                    "holding_days": hold_days,
                }
            )
            lot["remaining"] -= matched
            remaining_sell -= matched
            if lot["remaining"] <= 0:
                lots[symbol].pop(0)
    return trades


def _latest_benchmark_return(series: list[dict[str, Any]]) -> float | None:
    values = [_float(point.get("value")) for point in series]
    values = [value for value in values if value is not None and value != 0]
    if len(values) < 2 or len({round(value, 12) for value in values}) < 2:
        return None
    return values[-1] / values[0] - 1.0


def _return_by_time(series: list[dict[str, Any]]) -> dict[str, float]:
    points: list[tuple[datetime, float]] = []
    for point in series:
        time_value = _dt(point.get("time"))
        value = _float(point.get("value"))
        if time_value is not None and value is not None and value != 0:
            points.append((time_value, value))
    points.sort(key=lambda item: item[0])
    returns: dict[str, float] = {}
    for previous, current in zip(points, points[1:]):
        if previous[1]:
            returns[current[0].isoformat()] = current[1] / previous[1] - 1.0
    return returns


def _last_value_by_date(series: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, tuple[datetime, float]] = {}
    for point in series:
        time_value = _dt(point.get("time"))
        value = _float(point.get("value"))
        if time_value is None or value is None or value <= 0:
            continue
        key = time_value.date().isoformat()
        current = values.get(key)
        if current is None or time_value >= current[0]:
            values[key] = (time_value, value)
    return {key: item[1] for key, item in values.items()}


def _calendar_dates(series: list[dict[str, Any]]) -> set[str]:
    dates: set[str] = set()
    for point in series:
        time_value = _dt(point.get("time"))
        value = _float(point.get("value"))
        if time_value is not None and value is not None and value > 0:
            dates.add(time_value.date().isoformat())
    return dates


def _daily_equity_returns(
    equity_curve: list[dict[str, Any]],
    chart_data: dict[str, Any],
) -> tuple[list[float], str, int]:
    equity_by_date = _last_value_by_date(equity_curve)
    if not equity_by_date:
        return [], "equity_curve_missing", 0
    series = chart_data.get("series") or {}
    calendar_source = "equity_curve"
    calendar_dates = _calendar_dates(series.get("price") or [])
    if calendar_dates:
        calendar_source = "price_series"
    else:
        calendar_dates = _calendar_dates(series.get("benchmark") or [])
        if calendar_dates:
            calendar_source = "benchmark_series"
    dates = sorted(equity_by_date)
    if calendar_dates:
        filtered_dates = [date for date in dates if date in calendar_dates]
        if len(filtered_dates) >= 2:
            dates = filtered_dates
        else:
            calendar_source = "equity_curve"
    returns: list[float] = []
    for previous_date, current_date in zip(dates, dates[1:]):
        previous = equity_by_date[previous_date]
        current = equity_by_date[current_date]
        if previous > 0:
            returns.append(current / previous - 1.0)
    return returns, calendar_source, len(dates)


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _sharpe_quality(
    statistics: dict[str, Any],
    chart_data: dict[str, Any],
    equity_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    returns, calendar_source, date_points = _daily_equity_returns(equity_curve, chart_data)
    lean_sharpe = _float(statistics.get("Sharpe Ratio"))
    warnings: list[str] = []
    result: dict[str, Any] = {
        "lean_sharpe_ratio": lean_sharpe,
        "sharpe_recomputed_from_equity": None,
        "sharpe_recomputed_sample_count": len(returns),
        "sharpe_recomputed_date_points": date_points,
        "sharpe_recomputed_calendar_source": calendar_source,
        "sharpe_recomputed_annualization_factor": SHARPE_ANNUALIZATION_FACTOR,
        "sharpe_recomputed_mean_daily_return": None,
        "sharpe_recomputed_daily_volatility": None,
        "short_window_unstable": len(returns) < SHORT_WINDOW_SHARPE_MIN_RETURNS,
        "sharpe_recompute_status": "insufficient_return_points",
        "sharpe_metric_warnings": warnings,
    }
    if result["short_window_unstable"]:
        warnings.append("short_window_unstable")
    if len(returns) < 2:
        return result
    mean = sum(returns) / len(returns)
    volatility = _sample_std(returns)
    result["sharpe_recomputed_mean_daily_return"] = mean
    result["sharpe_recomputed_daily_volatility"] = volatility
    if volatility is None or volatility <= 1e-18:
        result["sharpe_recompute_status"] = "zero_return_volatility"
        return result
    recomputed = mean / volatility * math.sqrt(SHARPE_ANNUALIZATION_FACTOR)
    result["sharpe_recomputed_from_equity"] = recomputed
    result["sharpe_recompute_status"] = "computed_from_equity_curve"
    if lean_sharpe is not None and abs(lean_sharpe - recomputed) > max(1.0, abs(recomputed) * 0.5):
        warnings.append("lean_sharpe_diverges_from_equity_recompute")
    if warnings:
        result["sharpe_recompute_status"] = "computed_with_warnings"
    return result


def _aligned_alpha_beta(
    equity_curve: list[dict[str, Any]],
    benchmark_series: list[dict[str, Any]],
) -> dict[str, Any]:
    strategy_returns = _return_by_time(equity_curve)
    benchmark_returns = _return_by_time(benchmark_series)
    common = sorted(set(strategy_returns) & set(benchmark_returns))
    if len(common) < 2:
        return {"alpha": None, "beta": None, "status": "insufficient_aligned_points_for_alpha_beta", "points": len(common)}
    strategy_values = [strategy_returns[key] for key in common]
    benchmark_values = [benchmark_returns[key] for key in common]
    mean_strategy = sum(strategy_values) / len(strategy_values)
    mean_benchmark = sum(benchmark_values) / len(benchmark_values)
    variance = sum((value - mean_benchmark) ** 2 for value in benchmark_values)
    if abs(variance) < 1e-18:
        return {"alpha": None, "beta": None, "status": "zero_benchmark_variance", "points": len(common)}
    covariance = sum((s - mean_strategy) * (b - mean_benchmark) for s, b in zip(strategy_values, benchmark_values))
    beta = covariance / variance
    alpha = mean_strategy - beta * mean_benchmark
    return {"alpha": alpha, "beta": beta, "status": "computed_from_aligned_chart_returns", "points": len(common)}


def summary_with_benchmark_metrics(statistics: dict[str, Any], performance: dict[str, Any]) -> dict[str, Any]:
    summary = summary_metrics(statistics)
    metric_status = performance.get("benchmarkMetricStatus")
    summary["Strategy Return"] = performance.get("strategy_return")
    summary["Benchmark Return"] = performance.get("benchmark_return")
    summary["Excess Return"] = performance.get("excess_return")
    summary["Benchmark Metric Status"] = metric_status
    if performance.get("sharpe_recomputed_from_equity") is not None:
        summary["Recomputed Sharpe"] = performance.get("sharpe_recomputed_from_equity")
    summary["Sharpe Sample Count"] = performance.get("sharpe_recomputed_sample_count")
    summary["Sharpe Metric Status"] = performance.get("sharpe_recompute_status")
    summary["Short Window Unstable"] = performance.get("short_window_unstable")
    if performance.get("sharpe_metric_warnings"):
        summary["Sharpe Metric Warnings"] = ", ".join(performance.get("sharpe_metric_warnings") or [])
    if performance.get("computed_alpha") is not None:
        summary["Computed Alpha"] = performance.get("computed_alpha")
    if performance.get("computed_beta") is not None:
        summary["Computed Beta"] = performance.get("computed_beta")
    return summary


def _industry_exposure(filled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positions: dict[str, dict[str, float]] = {}
    for event in filled:
        symbol = str(event["symbol"])
        quantity = float(event["quantity"])
        price = float(event["price"])
        item = positions.setdefault(symbol, {"quantity": 0.0, "price": price})
        item["quantity"] += quantity
        item["price"] = price
    exposure: dict[str, float] = {}
    for symbol, item in positions.items():
        market_value = item["quantity"] * item["price"]
        if abs(market_value) < 1e-9:
            continue
        security = get_security(symbol)
        industry = (security or {}).get("industry") or "UNKNOWN"
        exposure[industry] = exposure.get(industry, 0.0) + market_value
    total = sum(abs(value) for value in exposure.values()) or 1.0
    return [
        {"industry": industry, "market_value": value, "weight": value / total}
        for industry, value in sorted(exposure.items(), key=lambda item: abs(item[1]), reverse=True)
    ]


def performance_analytics(
    statistics: dict[str, Any],
    chart_data: dict[str, Any],
    order_events: list[dict[str, Any]],
    data: dict[str, Any],
) -> dict[str, Any]:
    equity_curve = chart_data["series"].get("equity") or []
    filled = _filled_events(order_events)
    trade_pairs = _trade_pairs(filled)
    pnl_values = [_float(value) for value in (data.get("profitLoss") or {}).values()]
    pnl_values = [value for value in pnl_values if value is not None]
    annual_return = _float(statistics.get("Compounding Annual Return"))
    drawdown = abs(_float(statistics.get("Drawdown")) or 0)
    calmar = annual_return / drawdown if annual_return is not None and drawdown > 0 else None
    strategy_return = None
    if equity_curve:
        start = _float(equity_curve[0].get("value"))
        end = _float(equity_curve[-1].get("value"))
        strategy_return = end / start - 1.0 if start else None
    benchmark_return = _latest_benchmark_return(chart_data["series"].get("benchmark") or [])
    alpha_beta = _aligned_alpha_beta(equity_curve, chart_data["series"].get("benchmark") or [])
    metric_status = "benchmark_return_available"
    benchmark_source = (chart_data.get("seriesSources") or {}).get("benchmark")
    if benchmark_return is None:
        metric_status = "benchmark_curve_missing_or_insufficient_points"
    elif alpha_beta["status"] != "computed_from_aligned_chart_returns":
        metric_status = alpha_beta["status"]
    elif benchmark_source == "lean_data_cache":
        metric_status = "benchmark_return_available_from_lean_data_cache"
    sharpe_quality = _sharpe_quality(statistics, chart_data, equity_curve)
    return {
        "monthly_returns": _period_returns(equity_curve, "month"),
        "yearly_returns": _period_returns(equity_curve, "year"),
        "calmar": calmar,
        "trade_pnl": trade_pairs,
        "trade_pnl_summary": {
            "count": len(trade_pairs),
            "average_pnl": sum(item["net_pnl"] for item in trade_pairs) / len(trade_pairs) if trade_pairs else 0,
            "best_pnl": max((item["net_pnl"] for item in trade_pairs), default=0),
            "worst_pnl": min((item["net_pnl"] for item in trade_pairs), default=0),
            "average_holding_days": sum(item["holding_days"] or 0 for item in trade_pairs) / len(trade_pairs) if trade_pairs else 0,
        },
        "single_trade_returns": [
            {"symbol": item["symbol"], "exit_time": item["exit_time"], "return": item["return"], "net_pnl": item["net_pnl"]}
            for item in trade_pairs
        ],
        "profit_loss_distribution": pnl_values,
        "excess_return": (strategy_return - benchmark_return) if strategy_return is not None and benchmark_return is not None else None,
        "strategy_return": strategy_return,
        "benchmark_return": benchmark_return,
        "computed_alpha": alpha_beta["alpha"],
        "computed_beta": alpha_beta["beta"],
        "benchmarkMetricStatus": metric_status,
        "benchmarkMetricPoints": alpha_beta["points"],
        "benchmarkSeriesSource": benchmark_source,
        **sharpe_quality,
        "industry_exposure": _industry_exposure(filled),
    }
