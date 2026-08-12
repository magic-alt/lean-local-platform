from __future__ import annotations

import hashlib
import html
import json
import math
import shutil
import statistics
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .. import db as db_module
from ..db import db, rows_to_dicts, utc_now
from .ashare_repository import trade_status_as_of, universe_as_of


TEMPLATE_KEY = "ashare-swing-candidates"
RULES_VERSION = "orderly-pullback-v1"
REQUIRED_DATASETS = [
    "stock_basic",
    "namechange",
    "trade_cal",
    "daily",
    "adj_factor",
    "daily_basic",
    "suspend_d",
    "stk_limit",
    "income",
    "fina_indicator",
]
DEFAULT_CASE_SYMBOLS = [
    "600036",
    "601166",
    "000651",
    "600690",
    "600030",
    "601088",
    "300059",
    "601766",
    "601985",
    "601899",
    "600938",
    "601600",
    "603993",
    "600111",
]


@dataclass(frozen=True)
class ScreenRules:
    max_price: float = 50.0
    min_total_mv_cny: float = 20_000_000_000.0
    min_spot_amount_cny: float = 100_000_000.0
    min_amount_20_cny: float = 300_000_000.0
    min_history_bars: int = 500
    worst_3d_min: float = -0.09
    worst_5d_min: float = -0.12
    worst_10d_min: float = -0.18
    worst_streak_min: float = -0.12
    max_drawdown_60_min: float = -0.15
    current_drawdown_60_min: float = -0.15
    pullback_threshold: float = -0.03
    pullback_max_age: int = 60
    pullback_p80_max: float = 60.0
    atr20_min: float = 0.012
    atr20_max: float = 0.045
    amplitude_60_min: float = 0.08
    amplitude_60_max: float = 0.35
    ma120_tolerance: float = 0.02
    ma60_slope_20_min: float = -0.02
    entry_drawdown_min: float = -0.10
    entry_drawdown_max: float = -0.04
    entry_age_min: int = 3
    entry_age_max: int = 30
    rsi14_min: float = 40.0
    rsi14_max: float = 58.0
    volume_contraction_max: float = 0.95
    entry_ma60_tolerance: float = 0.02


def default_parameters() -> dict[str, Any]:
    return {
        "universeCode": "ALL_A",
        "rulesVersion": RULES_VERSION,
        "minHistoryBars": 500,
        "topN": 30,
        "caseSymbols": DEFAULT_CASE_SYMBOLS,
    }


def normalize_parameters(parameters: dict[str, Any] | None) -> tuple[dict[str, Any], ScreenRules]:
    raw = {**default_parameters(), **(parameters or {})}
    if str(raw.get("rulesVersion") or RULES_VERSION) != RULES_VERSION:
        raise ValueError(f"unsupported_swing_rules_version:{raw.get('rulesVersion')}")
    history = int(raw.get("minHistoryBars") or 500)
    if history < 250 or history > 750:
        raise ValueError("minHistoryBars must be between 250 and 750")
    top_n = int(raw.get("topN") or 30)
    if top_n < 1 or top_n > 200:
        raise ValueError("topN must be between 1 and 200")
    symbols = sorted(
        {
            str(value).strip().upper().split(".", 1)[0]
            for value in raw.get("caseSymbols") or DEFAULT_CASE_SYMBOLS
            if str(value).strip()
        }
    )
    rules = ScreenRules(min_history_bars=history)
    normalized = {
        "universeCode": str(raw.get("universeCode") or "ALL_A").strip().upper(),
        "rulesVersion": RULES_VERSION,
        "minHistoryBars": history,
        "topN": top_n,
        "caseSymbols": symbols,
    }
    return normalized, rules


def _chunks(values: list[str], size: int = 300) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _open_dates(as_of_date: str, limit: int = 12) -> list[str]:
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date from trade_calendar
            where market='china' and is_open=1 and trade_date<=?
            order by trade_date desc limit ?
            """,
            (as_of_date, limit),
        ).fetchall()
    return [str(row["trade_date"]) for row in rows]


def _daily_counts(trade_date: str) -> dict[str, int]:
    with db() as connection:
        bars = connection.execute(
            """
            select count(distinct symbol) n from market_daily_bars
            where asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade'
              and trade_date=? and adjust='raw' and source='tushare'
            """,
            (trade_date,),
        ).fetchone()
        basics = connection.execute(
            """
            select count(distinct symbol) n from daily_basic_factor_values
            where trade_date=? and factor_name='pe_ttm'
            """,
            (trade_date,),
        ).fetchone()
        adjustments = connection.execute(
            """
            select count(distinct symbol) n from adjustment_factors
            where trade_date=? and source='tushare'
            """,
            (trade_date,),
        ).fetchone()
        statuses = connection.execute(
            """select count(distinct symbol) n from market_trade_status
               where asset_class='equity' and market='china' and venue='china' and trade_date=?""",
            (trade_date,),
        ).fetchone()
    return {
        "bars": int(bars["n"] or 0),
        "dailyBasic": int(basics["n"] or 0),
        "adjustmentFactors": int(adjustments["n"] or 0),
        "tradeStatus": int(statuses["n"] or 0),
    }


def resolve_complete_trade_date(as_of_date: str, *, min_coverage: float = 0.95) -> dict[str, Any]:
    dates = _open_dates(as_of_date)
    attempts: list[dict[str, Any]] = []
    counts_by_date = {item: _daily_counts(item) for item in dates}
    for index, trade_date in enumerate(dates[:5]):
        counts = counts_by_date[trade_date]
        previous = [counts_by_date[item]["bars"] for item in dates[index + 1 : index + 6] if counts_by_date[item]["bars"]]
        expected = float(statistics.median(previous)) if previous else float(counts["bars"])
        base = max(1.0, expected)
        ratios = {
            "bars": counts["bars"] / base,
            "dailyBasic": counts["dailyBasic"] / max(1, counts["bars"]),
            "adjustmentFactors": counts["adjustmentFactors"] / max(1, counts["bars"]),
            "tradeStatus": counts["tradeStatus"] / max(1, counts["bars"]),
        }
        complete = bool(counts["bars"] and all(value >= min_coverage for value in ratios.values()))
        attempts.append({"tradeDate": trade_date, "counts": counts, "ratios": ratios, "complete": complete})
        if complete:
            return {
                "requestedAsOfDate": as_of_date,
                "tradeDate": trade_date,
                "fellBack": trade_date != as_of_date,
                "counts": counts,
                "ratios": ratios,
                "attempts": attempts,
            }
    return {
        "requestedAsOfDate": as_of_date,
        "tradeDate": None,
        "fellBack": False,
        "counts": attempts[0]["counts"] if attempts else {},
        "ratios": attempts[0]["ratios"] if attempts else {},
        "attempts": attempts,
    }


def preview(scope: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    normalized, rules = normalize_parameters(parameters)
    as_of = scope["time"].get("asOfDate") or scope["time"].get("endDate")
    if not as_of:
        raise ValueError("asOfDate is required for A-share swing screening")
    blocking: list[str] = []
    if scope["price"].get("adjust") != "raw":
        blocking.append("raw_scope_required")
    resolved = resolve_complete_trade_date(str(as_of))
    trade_date = resolved.get("tradeDate")
    members = universe_as_of(normalized["universeCode"], trade_date or str(as_of))
    coverage: dict[str, Any] = {
        **(resolved.get("counts") or {}),
        "rows": int((resolved.get("counts") or {}).get("bars") or 0),
        "symbols": len(members),
        "first_date": None,
        "last_date": trade_date,
        "historyEligible": 0,
        "positiveProfit": 0,
        "nameHistory": 0,
        "nameHistoryRatio": 0.0,
    }
    if not trade_date:
        blocking.append("complete_trade_date_unavailable")
    if not members:
        blocking.append("pit_universe_unavailable")
    if trade_date and members:
        symbols = [str(item["symbol"]) for item in members]
        eligible = 0
        positive_profit: set[str] = set()
        name_symbols: set[str] = set()
        first_dates: list[str] = []
        for chunk in _chunks(symbols):
            placeholders = ",".join("?" for _ in chunk)
            with db() as connection:
                history_rows = connection.execute(
                    f"""
                    select symbol,count(*) n,min(trade_date) first_date
                    from market_daily_bars
                    where asset_class='equity' and market='china' and venue='china'
                      and resolution='daily' and data_type='trade'
                      and symbol in ({placeholders}) and trade_date<=?
                      and adjust='raw' and source='tushare'
                    group by symbol having count(*)>=?
                    """,
                    [*chunk, trade_date, rules.min_history_bars],
                ).fetchall()
                profit_rows = connection.execute(
                    f"""
                    select distinct symbol from financial_facts
                    where symbol in ({placeholders}) and field_name='n_income_attr_p'
                      and value>0 and announce_date<=? and effective_date<=?
                      and source like 'tushare:%'
                    """,
                    [*chunk, trade_date, trade_date],
                ).fetchall()
                name_rows = connection.execute(
                    f"""
                    select distinct symbol from security_name_history
                    where symbol in ({placeholders}) and start_date<=?
                      and (end_date is null or end_date>=?)
                    """,
                    [*chunk, trade_date, trade_date],
                ).fetchall()
            eligible += len(history_rows)
            first_dates.extend(str(row["first_date"]) for row in history_rows if row["first_date"])
            positive_profit.update(str(row["symbol"]) for row in profit_rows)
            name_symbols.update(str(row["symbol"]) for row in name_rows)
        coverage.update(
            {
                "historyEligible": eligible,
                "positiveProfit": len(positive_profit),
                "nameHistory": len(name_symbols),
                "nameHistoryRatio": len(name_symbols) / max(1, len(members)),
                "first_date": min(first_dates) if first_dates else None,
            }
        )
        if not eligible:
            blocking.append("screen_history_unavailable")
        if not positive_profit:
            blocking.append("financial_pit_unavailable")
        if coverage["nameHistoryRatio"] < 0.95:
            blocking.append("name_history_pit_incomplete")
    ready = not blocking
    warnings = []
    if resolved.get("fellBack"):
        warnings.append(f"请求日数据未完整，使用 {trade_date}。")
    return {
        "template": TEMPLATE_KEY,
        "ready": ready,
        "blocking": blocking,
        "warnings": warnings,
        "coverage": coverage,
        "resolvedTradeDate": trade_date,
        "requestedAsOfDate": as_of,
        "dateResolution": resolved,
        "parameters": normalized,
        "requiredDatasets": REQUIRED_DATASETS,
        "preparationRequest": None
        if ready
        else {
            "mode": "screen_backfill",
            "datasets": REQUIRED_DATASETS,
            "scope": {
                "type": "ashare_swing_screen",
                "universeCode": normalized["universeCode"],
                "asOfDate": as_of,
                "minHistoryBars": rules.min_history_bars,
            },
        },
    }


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def worst_negative_streak_return(returns: pd.Series) -> float:
    cumulative = 1.0
    worst = 0.0
    for value in returns.dropna():
        if value < 0:
            cumulative *= 1 + float(value)
            worst = min(worst, cumulative - 1)
        else:
            cumulative = 1.0
    return float(worst)


def pullback_run_statistics(mask: pd.Series) -> tuple[int, float, int]:
    values = mask.fillna(False).to_numpy(dtype=bool)
    runs: list[int] = []
    index = 0
    while index < len(values):
        if not values[index]:
            index += 1
            continue
        end = index
        while end < len(values) and values[end]:
            end += 1
        runs.append(end - index)
        index = end
    if not runs:
        return 0, 0.0, 0
    current_age = runs[-1] if values[-1] else 0
    completed = runs[:-1] if values[-1] else runs
    return current_age, float(np.percentile(completed, 80)) if completed else 0.0, len(completed)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def calculate_stock_features(history: pd.DataFrame, rules: ScreenRules) -> dict[str, Any] | None:
    if history.empty or len(history) < rules.min_history_bars:
        return None
    frame = history.tail(max(rules.min_history_bars, 500)).copy()
    close = frame["close_qfq"].astype(float)
    high = frame["high_qfq"].astype(float)
    low = frame["low_qfq"].astype(float)
    volume = frame["volume"].astype(float)
    amount = frame["amount"].astype(float)
    returns = close.pct_change()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma120 = close.rolling(120).mean()
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    atr20_pct = float(true_range.rolling(20).mean().iloc[-1] / close.iloc[-1])
    recent_120 = close.tail(120)
    recent_returns = returns.tail(120)
    worst_3d = float(recent_120.pct_change(3).min())
    worst_5d = float(recent_120.pct_change(5).min())
    worst_10d = float(recent_120.pct_change(10).min())
    worst_streak = worst_negative_streak_return(recent_returns)
    recent_60 = close.tail(60)
    high_60 = float(recent_60.max())
    low_60 = float(recent_60.min())
    current_drawdown_60 = float(close.iloc[-1] / high_60 - 1)
    max_drawdown_60 = float((recent_60 / recent_60.cummax() - 1).min())
    amplitude_60 = float(high_60 / low_60 - 1)
    rolling_high_60 = close.rolling(60, min_periods=20).max()
    pullback_mask = close / rolling_high_60 - 1 <= rules.pullback_threshold
    pullback_age, pullback_p80, pullback_episodes = pullback_run_statistics(pullback_mask)
    amount_20 = float(amount.tail(20).mean())
    mean_volume_20 = float(volume.tail(20).mean())
    volume_contraction = float(volume.tail(5).mean() / mean_volume_20) if mean_volume_20 > 0 else math.nan
    rsi14 = float(calculate_rsi(close).iloc[-1])
    ma60_slope_20 = float(ma60.iloc[-1] / ma60.iloc[-21] - 1)
    reclaim_ma10 = bool(close.iloc[-1] > ma10.iloc[-1] and close.iloc[-2] <= ma10.iloc[-2])
    break_3d_high = bool(close.iloc[-1] > high.iloc[-4:-1].max())

    checks = [
        ("worst_3d", worst_3d > rules.worst_3d_min),
        ("worst_5d", worst_5d > rules.worst_5d_min),
        ("worst_10d", worst_10d > rules.worst_10d_min),
        ("worst_down_streak", worst_streak > rules.worst_streak_min),
        ("max_drawdown_60", max_drawdown_60 > rules.max_drawdown_60_min),
        ("current_drawdown_60", current_drawdown_60 > rules.current_drawdown_60_min),
        ("pullback_age", pullback_age <= rules.pullback_max_age),
        ("pullback_p80", pullback_p80 <= rules.pullback_p80_max),
        ("atr20", rules.atr20_min <= atr20_pct <= rules.atr20_max),
        ("amplitude_60", rules.amplitude_60_min <= amplitude_60 <= rules.amplitude_60_max),
        ("amount_20", amount_20 >= rules.min_amount_20_cny),
        ("ma120_support", close.iloc[-1] >= ma120.iloc[-1] * (1 - rules.ma120_tolerance)),
        ("ma60_slope", ma60_slope_20 >= rules.ma60_slope_20_min),
    ]
    first_rejection = next((name for name, passed in checks if not passed), None)
    technical_pass = first_rejection is None
    entry_ready = bool(
        technical_pass
        and rules.entry_drawdown_min <= current_drawdown_60 <= rules.entry_drawdown_max
        and rules.entry_age_min <= pullback_age <= rules.entry_age_max
        and rules.rsi14_min <= rsi14 <= rules.rsi14_max
        and close.iloc[-1] >= ma60.iloc[-1] * (1 - rules.entry_ma60_tolerance)
        and volume_contraction <= rules.volume_contraction_max
    )
    triggered = bool(entry_ready and (reclaim_ma10 or break_3d_high))
    technical_score = (
        25 * np.clip((worst_5d - rules.worst_5d_min) / abs(rules.worst_5d_min), 0, 1)
        + 20 * np.clip((worst_10d - rules.worst_10d_min) / abs(rules.worst_10d_min), 0, 1)
        + 15 * np.clip((rules.pullback_p80_max - pullback_p80) / rules.pullback_p80_max, 0, 1)
        + 15 * np.clip((amplitude_60 - rules.amplitude_60_min) / 0.15, 0, 1)
        + 10 * np.clip((atr20_pct - rules.atr20_min) / 0.025, 0, 1)
        + 10 * float(close.iloc[-1] >= ma60.iloc[-1])
        + 5 * float(entry_ready)
    )
    return {
        "technical_pass": technical_pass,
        "entry_ready": entry_ready,
        "triggered": triggered,
        "first_rejection": first_rejection,
        "technical_score": round(float(technical_score), 2),
        "close_qfq": float(close.iloc[-1]),
        "ma10": float(ma10.iloc[-1]),
        "ma20": float(ma20.iloc[-1]),
        "ma60": float(ma60.iloc[-1]),
        "ma120": float(ma120.iloc[-1]),
        "rsi14": rsi14,
        "atr20_pct": atr20_pct,
        "amplitude_60": amplitude_60,
        "current_drawdown_60": current_drawdown_60,
        "max_drawdown_60": max_drawdown_60,
        "worst_3d": worst_3d,
        "worst_5d": worst_5d,
        "worst_10d": worst_10d,
        "worst_down_streak": worst_streak,
        "pullback_age": pullback_age,
        "pullback_p80": pullback_p80,
        "pullback_episode_count": pullback_episodes,
        "amount_20": amount_20,
        "volume_contraction": volume_contraction,
        "ma60_slope_20": ma60_slope_20,
        "reclaim_ma10": reclaim_ma10,
        "break_3d_high": break_3d_high,
        "history_bars": len(history),
        "history_digest": str(history.attrs.get("input_digest") or ""),
    }


def _latest_factors(symbols: list[str], trade_date: str) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {symbol: {} for symbol in symbols}
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,factor_name,value from daily_basic_factor_values
                where symbol in ({placeholders}) and trade_date=?
                  and factor_name in ('pe_ttm','total_mv_cny','circ_mv_cny')
                """,
                [*chunk, trade_date],
            ).fetchall()
        for row in rows_to_dicts(rows):
            result[str(row["symbol"])][str(row["factor_name"])] = float(row["value"])
    return result


def _latest_financials(symbols: list[str], trade_date: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {symbol: {} for symbol in symbols}
    seen: set[tuple[str, str]] = set()
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,field_name,report_date,announce_date,effective_date,value,source
                from financial_facts
                where symbol in ({placeholders})
                  and field_name in ('n_income_attr_p','profit_dedt')
                  and announce_date<=? and effective_date<=? and source like 'tushare:%'
                order by symbol,field_name,report_date desc,effective_date desc,announce_date desc
                """,
                [*chunk, trade_date, trade_date],
            ).fetchall()
        for row in rows_to_dicts(rows):
            key = (str(row["symbol"]), str(row["field_name"]))
            if key in seen:
                continue
            seen.add(key)
            result[key[0]][key[1]] = row.get("value")
            result[key[0]][f"{key[1]}_report_date"] = row.get("report_date")
            result[key[0]][f"{key[1]}_effective_date"] = row.get("effective_date")
    return result


def _pit_names(symbols: list[str], trade_date: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,name,is_st,start_date from security_name_history
                where symbol in ({placeholders}) and start_date<=?
                  and (end_date is null or end_date>=?)
                order by symbol,start_date desc
                """,
                [*chunk, trade_date, trade_date],
            ).fetchall()
        for row in rows_to_dicts(rows):
            result.setdefault(str(row["symbol"]), row)
    return result


def _spot_bars(symbols: list[str], trade_date: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,trade_date,open,high,low,close,volume,amount
                from market_daily_bars where asset_class='equity' and market='china' and venue='china'
                  and resolution='daily' and data_type='trade'
                  and symbol in ({placeholders}) and trade_date=?
                  and adjust='raw' and source='tushare'
                """,
                [*chunk, trade_date],
            ).fetchall()
        result.update({str(row["symbol"]): row for row in rows_to_dicts(rows)})
    return result


def _history(symbols: list[str], trade_date: str, rules: ScreenRules) -> dict[str, pd.DataFrame]:
    start = (date.fromisoformat(trade_date) - timedelta(days=max(1200, rules.min_history_bars * 2))).isoformat()
    result: dict[str, pd.DataFrame] = {}
    for chunk in _chunks(symbols, 120):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select b.symbol,b.trade_date,b.open,b.high,b.low,b.close,b.volume,
                       coalesce(b.amount,0) amount,a.adj_factor verified_adj_factor
                from market_daily_bars b
                left join adjustment_factors a
                  on a.symbol=b.symbol and a.trade_date=b.trade_date and a.source='tushare'
                where b.asset_class='equity' and b.market='china' and b.venue='china'
                  and b.resolution='daily' and b.data_type='trade'
                  and b.symbol in ({placeholders}) and b.trade_date between ? and ?
                  and b.adjust='raw' and b.source='tushare'
                order by b.symbol,b.trade_date
                """,
                [*chunk, start, trade_date],
            ).fetchall()
        frame = pd.DataFrame(rows_to_dicts(rows))
        if frame.empty:
            continue
        for symbol, group in frame.groupby("symbol", sort=False):
            group = group.dropna(subset=["verified_adj_factor"]).copy()
            if group.empty:
                continue
            if str(group["trade_date"].iloc[-1]) != trade_date:
                continue
            latest_factor = float(group["verified_adj_factor"].iloc[-1])
            multiplier = group["verified_adj_factor"].astype(float) / latest_factor
            for field in ("open", "high", "low", "close"):
                group[f"{field}_qfq"] = group[field].astype(float) * multiplier
            normalized = group.reset_index(drop=True)
            digest_columns = [
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "verified_adj_factor",
            ]
            normalized.attrs["input_digest"] = hashlib.sha256(
                normalized[digest_columns].to_json(orient="records", double_precision=12).encode("utf-8")
            ).hexdigest()
            result[str(symbol)] = normalized
    return result


def _first_gate_rejection(
    member: dict[str, Any],
    pit_name: dict[str, Any] | None,
    status: dict[str, Any] | None,
    spot: dict[str, Any] | None,
    factors: dict[str, Any],
    financials: dict[str, Any],
    rules: ScreenRules,
) -> str | None:
    if not spot:
        return "spot_bar_missing"
    if not status:
        return "trade_status_missing"
    is_st = bool((pit_name or {}).get("is_st", member.get("is_st")))
    if is_st:
        return "st_or_special_treatment"
    if status.get("is_suspended"):
        return "suspended"
    if status.get("is_one_word_limit_up") or status.get("is_one_word_limit_down"):
        return "one_word_limit"
    if _safe_float(spot.get("close")) is None or float(spot["close"]) > rules.max_price:
        return "price_above_limit"
    total_mv = _safe_float(factors.get("total_mv_cny"))
    if total_mv is None:
        return "total_mv_missing"
    if total_mv < rules.min_total_mv_cny:
        return "total_mv_below_limit"
    pe_ttm = _safe_float(factors.get("pe_ttm"))
    if pe_ttm is None:
        return "pe_ttm_missing"
    if pe_ttm <= 0:
        return "pe_ttm_non_positive"
    profit = _safe_float(financials.get("n_income_attr_p"))
    if profit is None:
        return "profit_missing"
    if profit <= 0:
        return "profit_non_positive"
    if float(spot.get("amount") or 0) < rules.min_spot_amount_cny:
        return "spot_liquidity_below_limit"
    return None


def _audit_fingerprint(rows: list[dict[str, Any]], trade_date: str, parameters: dict[str, Any]) -> str:
    payload = {
        "tradeDate": trade_date,
        "parameters": parameters,
        "rows": [
            {
                key: row.get(key)
                for key in (
                    "ts_code",
                    "bucket",
                    "first_rejection",
                    "spot_close",
                    "total_mv_cny",
                    "pe_ttm",
                    "n_income_attr_p",
                    "profit_dedt",
                    "score",
                    "technical_pass",
                    "entry_ready",
                    "triggered",
                    "history_digest",
                )
            }
            for row in rows
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _html_report(
    *,
    summary: dict[str, Any],
    candidates: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    rejection_counts: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    colors = {"A": "#0f766e", "B": "#2563eb", "C": "#7c3aed", "Reject": "#6b7280"}

    def pct(value: Any) -> str:
        return "—" if value is None else f"{float(value) * 100:.2f}%"

    def candidate_rows(items: list[dict[str, Any]]) -> str:
        output = []
        for item in items:
            bucket = str(item.get("bucket") or "Reject")
            output.append(
                "<tr>"
                f"<td><span class='pill' style='--pill:{colors.get(bucket, '#6b7280')}'>{html.escape(bucket)}</span></td>"
                f"<td><strong>{html.escape(str(item.get('name') or item.get('ts_code')))}</strong><br><small>{html.escape(str(item.get('ts_code')))}</small></td>"
                f"<td>{float(item.get('spot_close') or 0):.2f}</td>"
                f"<td>{float(item.get('score') or 0):.1f}</td>"
                f"<td>{pct(item.get('current_drawdown_60'))}</td>"
                f"<td>{pct(item.get('worst_5d'))}</td>"
                f"<td>{pct(item.get('atr20_pct'))}</td>"
                f"<td>{html.escape(str(item.get('first_rejection') or '—'))}</td>"
                "</tr>"
            )
        return "".join(output) or "<tr><td colspan='8'>当前规则下没有候选。</td></tr>"

    top_cards = []
    for item in candidates[:5]:
        action = "进入基本面与回测深挖" if item["bucket"] == "A" else "观察触发条件" if item["bucket"] == "B" else "保留屏幕标记"
        why = "MA10重新上穿" if item.get("reclaim_ma10") else "突破此前3日高点" if item.get("break_3d_high") else "尚未出现确认触发"
        top_cards.append(
            f"""
            <article class="idea-card">
              <div><span class="pill" style="--pill:{colors[item['bucket']]}">{item['bucket']}</span><h3>{html.escape(str(item['name']))} <small>{item['ts_code']}</small></h3></div>
              <dl>
                <dt>Actionability</dt><dd>{action}</dd>
                <dt>Variant Wedge</dt><dd>盈利和流动性硬门槛通过，60日回撤为 {pct(item.get('current_drawdown_60'))}；这只是形态筛选证据，不代表市场错误定价。</dd>
                <dt>Why Now</dt><dd>{why}。</dd>
                <dt>First Rejection</dt><dd>{html.escape(str(item.get('first_rejection') or '当前无硬拒绝项'))}</dd>
                <dt>What Would Make It Investable</dt><dd>补齐盈利质量、估值和行业催化尽调，并通过含费用的样本外回测。</dd>
                <dt>What Would Kill It</dt><dd>跌破下跌速度、15%回撤、MA120支撑或流动性门槛。</dd>
                <dt>Next Workflow</dt><dd>公司基本面尽调 → 参数敏感度回测 → 风险预算。</dd>
              </dl>
            </article>
            """
        )
    warning_html = "".join(f"<li>{html.escape(item)}</li>" for item in warnings) or "<li>无额外警告。</li>"
    rejection_html = "".join(
        f"<tr><td>{html.escape(str(item['reason']))}</td><td>{item['count']}</td></tr>" for item in rejection_counts
    )
    generated = html.escape(str(summary.get("generatedAt") or ""))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>全A有序回调候选研究</title><style>
:root{{--ink:#172033;--muted:#667085;--line:#e4e7ec;--paper:#fff;--wash:#f5f7fb;--accent:#0f766e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font:14px/1.55 Inter,"PingFang SC","Microsoft YaHei",sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:36px 24px 64px}}header{{background:linear-gradient(135deg,#102a43,#0f766e);color:white;border-radius:20px;padding:32px}}
h1{{margin:0 0 8px;font-size:32px}}h2{{margin:36px 0 14px;font-size:22px}}h3{{display:inline;margin-left:10px}}small{{color:var(--muted)}}header small{{color:#d1fae5}}
.lede{{max-width:900px;font-size:16px}}.tiles{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:22px}}.tile{{background:#ffffff18;border:1px solid #ffffff35;border-radius:12px;padding:12px}}.tile strong{{display:block;font-size:24px}}
.panel,.idea-card{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 4px 16px #102a4310}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;border-bottom:1px solid var(--line);padding:10px;white-space:nowrap}}th{{color:var(--muted);font-size:12px;text-transform:uppercase}}.table-wrap{{overflow:auto}}
.pill{{display:inline-block;background:var(--pill);color:white;border-radius:999px;padding:3px 9px;font-weight:700}}.ideas{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.idea-card dl{{display:grid;grid-template-columns:180px 1fr;gap:6px 12px}}dt{{font-weight:700;color:var(--muted)}}dd{{margin:0}}.note{{border-left:4px solid #f59e0b;padding-left:14px;color:#7c2d12}}
@media(max-width:850px){{.tiles{{grid-template-columns:repeat(2,1fr)}}.ideas{{grid-template-columns:1fr}}.idea-card dl{{grid-template-columns:1fr}}main{{padding:16px}}}}
</style></head><body><main>
<header><small>IDEA TRIAGE · {RULES_VERSION} · {generated}</small><h1>全A“有序回调”候选研究</h1><p class="lede">研究优先级筛选，不是买入评级。先排除盈利、流动性、下跌速度和趋势结构不合格的股票，再区分已触发、等待触发与普通观察项。</p>
<div class="tiles"><div class="tile"><span>股票池</span><strong>{summary['universeCount']}</strong></div><div class="tile"><span>A</span><strong>{summary['bucketA']}</strong></div><div class="tile"><span>B</span><strong>{summary['bucketB']}</strong></div><div class="tile"><span>C</span><strong>{summary['bucketC']}</strong></div><div class="tile"><span>Reject</span><strong>{summary['rejected']}</strong></div></div></header>
<h2>研究结论与候选漏斗</h2><section class="panel"><p><strong>实际数据日：</strong>{summary['tradeDate']}；<strong>请求日：</strong>{summary['requestedAsOfDate']}；<strong>数据指纹：</strong><code>{summary['dataFingerprint'][:16]}</code></p><p class="note">“Advance to deeper work”仅表示研究优先级更高。名单与公开网页候选不一致时，应以首个拒绝原因和本报告的冻结数据日解释差异。</p><ul>{warning_html}</ul></section>
<h2>排名候选</h2><section class="panel table-wrap"><table><thead><tr><th>Bucket</th><th>证券</th><th>收盘</th><th>分数</th><th>60日回撤</th><th>最差5日</th><th>ATR20</th><th>首个拒绝</th></tr></thead><tbody>{candidate_rows(candidates)}</tbody></table></section>
<h2>最高优先级研究卡</h2><section class="ideas">{''.join(top_cards) or '<div class="panel">没有A/B/C候选。</div>'}</section>
<h2>给定案例逐项审计</h2><section class="panel table-wrap"><table><thead><tr><th>Bucket</th><th>证券</th><th>收盘</th><th>分数</th><th>60日回撤</th><th>最差5日</th><th>ATR20</th><th>首个拒绝</th></tr></thead><tbody>{candidate_rows(cases)}</tbody></table></section>
<h2>排除原因</h2><section class="panel"><table><thead><tr><th>首个拒绝原因</th><th>数量</th></tr></thead><tbody>{rejection_html}</tbody></table></section>
<h2>方法和来源</h2><section class="panel"><p>来源：平台治理后的 Tushare 原始日线、adj_factor、daily_basic、交易状态、income 与 fina_indicator。技术指标使用截至实际数据日的前复权序列；归母净利润和扣非净利润只使用公告日及生效日不晚于该日的记录。</p><p>扣非利润只影响5分质量加分；缺失或为负不会单独剔除。历史没有已完成回调区间时，P80记为0并标记证据有限。所有阈值和结果都写入运行清单供复核。</p></section>
</main></body></html>"""


def _write_artifacts(
    run_id: str,
    *,
    audit_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    summary: dict[str, Any],
    warnings: list[str],
    rejection_counts: list[dict[str, Any]],
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    root = Path(db_module.RESEARCH_DIR) / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    audit = pd.DataFrame(audit_rows)
    candidate_frame = pd.DataFrame(candidates)
    audit_csv = root / "screen-audit.csv"
    candidate_csv = root / "screen-candidates.csv"
    audit_parquet = root / "screen-audit.parquet"
    report_path = root / "report.html"
    manifest_path = root / "run-manifest.json"
    audit.to_csv(audit_csv, index=False, encoding="utf-8-sig")
    candidate_frame.to_csv(candidate_csv, index=False, encoding="utf-8-sig")
    try:
        audit.to_parquet(audit_parquet, index=False)
    except Exception:
        import duckdb

        connection = duckdb.connect()
        connection.execute("copy (select * from read_csv_auto(?)) to ? (format parquet, compression zstd)", [str(audit_csv), str(audit_parquet)])
        connection.close()
    report_path.write_text(
        _html_report(
            summary=summary,
            candidates=candidates,
            cases=cases,
            rejection_counts=rejection_counts,
            warnings=warnings,
        ),
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": "1.0",
        "template": TEMPLATE_KEY,
        "rulesVersion": RULES_VERSION,
        "parameters": parameters,
        "summary": summary,
        "files": [],
    }
    artifacts = []
    for key, path, mime in (
        ("report", report_path, "text/html; charset=utf-8"),
        ("candidatesCsv", candidate_csv, "text/csv; charset=utf-8"),
        ("auditCsv", audit_csv, "text/csv; charset=utf-8"),
        ("auditParquet", audit_parquet, "application/vnd.apache.parquet"),
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        item = {"key": key, "name": path.name, "mimeType": mime, "sha256": digest, "size": path.stat().st_size}
        artifacts.append(item)
        manifest["files"].append(item)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    artifacts.append(
        {
            "key": "manifest",
            "name": manifest_path.name,
            "mimeType": "application/json",
            "sha256": digest,
            "size": manifest_path.stat().st_size,
        }
    )
    return artifacts


def analyze(
    scope: dict[str, Any],
    parameters: dict[str, Any],
    *,
    run_id: str,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    normalized, rules = normalize_parameters(parameters)
    check = preview(scope, normalized)
    if check["blocking"]:
        raise ValueError("swing_screen_preflight_failed:" + ",".join(check["blocking"]))
    trade_date = str(check["resolvedTradeDate"])
    requested_as_of = str(check["requestedAsOfDate"])
    emit = progress or (lambda _message: None)
    is_cancelled = cancelled or (lambda: False)
    members = universe_as_of(normalized["universeCode"], trade_date)
    member_by_symbol = {str(item["symbol"]): item for item in members}
    symbols = sorted(member_by_symbol)
    emit(f"Resolved {len(symbols)} PIT members on {trade_date}.")
    factors = _latest_factors(symbols, trade_date)
    financials = _latest_financials(symbols, trade_date)
    names = _pit_names(symbols, trade_date)
    statuses = trade_status_as_of(symbols, trade_date)
    spots = _spot_bars(symbols, trade_date)
    audit_by_symbol: dict[str, dict[str, Any]] = {}
    technical_symbols: list[str] = []
    for symbol in symbols:
        member = member_by_symbol[symbol]
        pit_name = names.get(symbol)
        rejection = _first_gate_rejection(
            member, pit_name, statuses.get(symbol), spots.get(symbol), factors.get(symbol, {}), financials.get(symbol, {}), rules
        )
        spot = spots.get(symbol) or {}
        fact = factors.get(symbol, {})
        fin = financials.get(symbol, {})
        row = {
            "ts_code": symbol,
            "name": str((pit_name or {}).get("name") or member.get("name") or symbol),
            "industry": member.get("industry"),
            "spot_close": _safe_float(spot.get("close")),
            "spot_amount": _safe_float(spot.get("amount")),
            "total_mv_cny": _safe_float(fact.get("total_mv_cny")),
            "total_mv_yi": (_safe_float(fact.get("total_mv_cny")) or 0) / 100_000_000,
            "pe_ttm": _safe_float(fact.get("pe_ttm")),
            "n_income_attr_p": _safe_float(fin.get("n_income_attr_p")),
            "profit_dedt": _safe_float(fin.get("profit_dedt")),
            "profit_report_date": fin.get("n_income_attr_p_report_date"),
            "profit_effective_date": fin.get("n_income_attr_p_effective_date"),
            "technical_pass": False,
            "entry_ready": False,
            "triggered": False,
            "technical_score": 0.0,
            "score": 0.0,
            "bucket": "Reject",
            "first_rejection": rejection,
            "is_case_symbol": symbol in normalized["caseSymbols"],
            "name_history_available": pit_name is not None,
        }
        audit_by_symbol[symbol] = row
        if rejection is None:
            technical_symbols.append(symbol)
    emit(f"{len(technical_symbols)} securities passed the fast PIT gates; calculating technical features.")
    for chunk_index, chunk in enumerate(_chunks(technical_symbols, 120), start=1):
        if is_cancelled():
            raise RuntimeError("research_run_cancelled")
        histories = _history(chunk, trade_date, rules)
        for symbol in chunk:
            row = audit_by_symbol[symbol]
            frame = histories.get(symbol)
            features = calculate_stock_features(frame, rules) if frame is not None else None
            if features is None:
                row["first_rejection"] = "history_or_adjustment_factor_missing"
                continue
            row.update(features)
            if not features["technical_pass"]:
                row["bucket"] = "Reject"
            elif features["triggered"]:
                row["bucket"] = "A"
            elif features["entry_ready"]:
                row["bucket"] = "B"
            else:
                row["bucket"] = "C"
            quality_bonus = 5.0 if (row.get("profit_dedt") or 0) > 0 else 0.0
            row["score"] = round(min(100.0, float(features["technical_score"]) * 0.95 + quality_bonus), 2)
            if features["technical_pass"]:
                row["first_rejection"] = None
        emit(f"Technical chunk {chunk_index} complete ({min(chunk_index * 120, len(technical_symbols))}/{len(technical_symbols)}).")
    audit_rows = [audit_by_symbol[symbol] for symbol in symbols]
    bucket_rank = {"A": 0, "B": 1, "C": 2, "Reject": 3}
    audit_rows.sort(key=lambda row: (bucket_rank[str(row["bucket"])], -float(row.get("score") or 0), str(row["ts_code"])))
    candidates = [row for row in audit_rows if row["bucket"] != "Reject"][: normalized["topN"]]
    cases = [audit_by_symbol[symbol] for symbol in normalized["caseSymbols"] if symbol in audit_by_symbol]
    rejection_series = pd.Series([row["first_rejection"] for row in audit_rows if row["bucket"] == "Reject"]).value_counts()
    rejection_counts = [{"reason": str(reason), "count": int(count)} for reason, count in rejection_series.items()]
    warnings = list(check.get("warnings") or [])
    missing_cases = sorted(set(normalized["caseSymbols"]) - set(audit_by_symbol))
    if missing_cases:
        warnings.append("案例代码不在当日PIT股票池：" + ", ".join(missing_cases))
    limited_pullbacks = sum(1 for row in candidates if int(row.get("pullback_episode_count") or 0) == 0)
    if limited_pullbacks:
        warnings.append(f"{limited_pullbacks} 个候选没有已完成的历史回调区间，修复时长证据有限。")
    negative_deducted = sum(1 for row in candidates if (row.get("profit_dedt") is None or float(row["profit_dedt"]) <= 0))
    if negative_deducted:
        warnings.append(f"{negative_deducted} 个候选的扣非利润缺失或非正，未获质量加分。")
    fingerprint = _audit_fingerprint(audit_rows, trade_date, normalized)
    summary = {
        "universeCount": len(audit_rows),
        "bucketA": sum(row["bucket"] == "A" for row in audit_rows),
        "bucketB": sum(row["bucket"] == "B" for row in audit_rows),
        "bucketC": sum(row["bucket"] == "C" for row in audit_rows),
        "rejected": sum(row["bucket"] == "Reject" for row in audit_rows),
        "tradeDate": trade_date,
        "requestedAsOfDate": requested_as_of,
        "fellBack": bool(check["dateResolution"].get("fellBack")),
        "rulesVersion": RULES_VERSION,
        "dataFingerprint": fingerprint,
        "generatedAt": utc_now(),
    }
    artifacts = _write_artifacts(
        run_id,
        audit_rows=audit_rows,
        candidates=candidates,
        cases=cases,
        summary=summary,
        warnings=warnings,
        rejection_counts=rejection_counts,
        parameters={**normalized, "resolvedRules": asdict(rules)},
    )
    tables = [
        {
            "name": "候选优先级",
            "columns": ["bucket", "ts_code", "name", "spot_close", "score", "entry_ready", "triggered", "current_drawdown_60", "worst_5d", "atr20_pct", "first_rejection"],
            "rows": candidates,
            "truncated": False,
        },
        {
            "name": "给定案例审计",
            "columns": ["bucket", "ts_code", "name", "spot_close", "score", "technical_pass", "entry_ready", "triggered", "first_rejection"],
            "rows": cases,
            "truncated": False,
        },
        {
            "name": "排除漏斗",
            "columns": ["reason", "count"],
            "rows": rejection_counts,
            "truncated": False,
        },
    ]
    return {
        "summary": summary,
        "charts": [],
        "tables": tables,
        "warnings": warnings,
        "artifacts": artifacts,
        "coverage": check["coverage"],
        "dataFingerprint": fingerprint,
        "resolvedParameters": {**normalized, "resolvedRules": asdict(rules)},
    }


def artifact_path(run_id: str, artifact_name: str) -> Path:
    root = (Path(db_module.RESEARCH_DIR) / "runs" / run_id).resolve()
    target = (root / artifact_name).resolve()
    if root not in target.parents or not target.is_file():
        raise ValueError("Research artifact path is invalid.")
    return target


def remove_artifacts(run_id: str) -> None:
    root = Path(db_module.RESEARCH_DIR) / "runs" / run_id
    if root.exists():
        shutil.rmtree(root)
