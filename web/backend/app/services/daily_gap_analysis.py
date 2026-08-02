from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any

from ..db import db, rows_to_dicts
from . import data_gateway


TEMPLATE_KEY = "daily-gap-events"

SEVERITY_ORDER = {"全部≥1σ": 0, "1.0-1.5σ": 1, "1.5-2.0σ": 2, "≥2.0σ": 3}


def default_parameters() -> dict[str, Any]:
    return {
        "gapSigmaWindow": 60,
        "gapSigmaMinPeriods": 30,
        "volumeWindow": 20,
        "volumeMinPeriods": 10,
        "corporateActionTolerance": 0.001,
    }


def _parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    merged = {**default_parameters(), **(parameters or {})}
    sigma_window = int(merged["gapSigmaWindow"])
    sigma_min_periods = int(merged["gapSigmaMinPeriods"])
    volume_window = int(merged["volumeWindow"])
    volume_min_periods = int(merged["volumeMinPeriods"])
    corporate_action_tolerance = float(merged["corporateActionTolerance"])
    if not 20 <= sigma_window <= 252:
        raise ValueError("gapSigmaWindow must be between 20 and 252")
    if not 10 <= sigma_min_periods <= sigma_window:
        raise ValueError("gapSigmaMinPeriods must be between 10 and gapSigmaWindow")
    if not 5 <= volume_window <= 252:
        raise ValueError("volumeWindow must be between 5 and 252")
    if not 3 <= volume_min_periods <= volume_window:
        raise ValueError("volumeMinPeriods must be between 3 and volumeWindow")
    if not 0 <= corporate_action_tolerance <= 0.2:
        raise ValueError("corporateActionTolerance must be between 0 and 0.2")
    return {
        "gapSigmaWindow": sigma_window,
        "gapSigmaMinPeriods": sigma_min_periods,
        "volumeWindow": volume_window,
        "volumeMinPeriods": volume_min_periods,
        "corporateActionTolerance": corporate_action_tolerance,
    }


def _scope_blocking(scope: dict[str, Any]) -> list[str]:
    blocking: list[str] = []
    if str(scope["asset"].get("resolution") or "").lower() != "daily":
        blocking.append("daily_resolution_required")
    if str(scope["asset"].get("dataType") or "").lower() != "trade":
        blocking.append("trade_bars_required")
    if str(scope["price"].get("adjust") or "").lower() != "raw":
        blocking.append("raw_price_with_exchange_prev_close_required")
    selection = scope["selection"]
    if selection.get("type") != "symbols" or not selection.get("values"):
        blocking.append("explicit_symbol_proxies_required")
    if len(selection.get("values") or []) > 50:
        blocking.append("maximum_50_symbol_proxies")
    if not scope["time"].get("startDate") or not scope["time"].get("endDate"):
        blocking.append("bounded_date_window_required")
    return blocking


def preview(
    scope: dict[str, Any],
    parameters: dict[str, Any],
    *,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = data_gateway.normalize_scope(scope)
    normalized_parameters = _parameters(parameters)
    resolution = resolved or data_gateway.resolve(normalized)
    blocking = _scope_blocking(normalized)
    if not resolution.get("ready"):
        blocking.append("data_unavailable")
    return {
        "template": TEMPLATE_KEY,
        "resolvedParameters": normalized_parameters,
        "blocking": list(dict.fromkeys(blocking)),
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = min(1.0, max(0.0, probability)) * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _prior_ratio(values: list[float | None], index: int, window: int, min_periods: int) -> float | None:
    current = values[index]
    prior = [value for value in values[max(0, index - window):index] if value is not None and value >= 0]
    average = _mean(prior) if len(prior) >= min_periods else None
    return current / average if current is not None and average and average > 0 else None


def _severity(gap_z: float) -> str:
    magnitude = abs(gap_z)
    if magnitude < 1.5:
        return "1.0-1.5σ"
    if magnitude < 2.0:
        return "1.5-2.0σ"
    return "≥2.0σ"


def add_daily_gap_features(
    rows: list[dict[str, Any]],
    *,
    gap_sigma_window: int = 60,
    gap_sigma_min_periods: int = 30,
    volume_window: int = 20,
    volume_min_periods: int = 10,
    corporate_action_tolerance: float = 0.001,
) -> list[dict[str, Any]]:
    """Create daily-only gap features independently for every symbol."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "")].append(dict(row))

    output: list[dict[str, Any]] = []
    for symbol, symbol_rows in sorted(grouped.items()):
        ordered = sorted(symbol_rows, key=lambda item: str(item.get("trade_date") or ""))
        closes = [_finite(item.get("close")) for item in ordered]
        volumes = [
            _finite(item.get("volume") if item.get("volume") is not None else item.get("vol"))
            for item in ordered
        ]
        amounts = [_finite(item.get("amount")) for item in ordered]
        prior_gaps: list[float] = []

        for index, item in enumerate(ordered):
            open_price = _finite(item.get("open"))
            high = _finite(item.get("high"))
            low = _finite(item.get("low"))
            close = closes[index]
            prev_close = _finite(
                item.get("prev_close") if item.get("prev_close") is not None else item.get("pre_close")
            )
            previous_actual_close = closes[index - 1] if index else None
            corporate_action_flag = bool(
                previous_actual_close
                and previous_actual_close > 0
                and prev_close
                and prev_close > 0
                and abs(prev_close / previous_actual_close - 1) > corporate_action_tolerance
            )
            valid_ohlc = bool(
                open_price
                and prev_close
                and open_price > 0
                and prev_close > 0
                and high is not None
                and low is not None
                and close is not None
                and high >= max(open_price, close)
                and low <= min(open_price, close)
            )
            gap = open_price / prev_close - 1 if valid_ohlc else None
            history = prior_gaps[-gap_sigma_window:]
            sigma = statistics.stdev(history) if len(history) >= gap_sigma_min_periods else None
            gap_z = gap / sigma if gap is not None and sigma and sigma > 0 else None

            ret_open_close = close / open_price - 1 if valid_ohlc else None
            mfe = high / open_price - 1 if valid_ohlc else None
            mae = low / open_price - 1 if valid_ohlc else None
            volume_ratio = _prior_ratio(volumes, index, volume_window, volume_min_periods)
            amount_ratio = _prior_ratio(amounts, index, volume_window, volume_min_periods)
            ret_5d_before = (
                previous_actual_close / closes[index - 6] - 1
                if index >= 6 and previous_actual_close and closes[index - 6] and closes[index - 6] > 0
                else None
            )
            ret_20d_before = (
                previous_actual_close / closes[index - 21] - 1
                if index >= 21 and previous_actual_close and closes[index - 21] and closes[index - 21] > 0
                else None
            )

            feature = {
                "symbol": symbol,
                "tradeDate": str(item.get("trade_date") or ""),
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "preClose": prev_close,
                "previousActualClose": previous_actual_close,
                "corporateActionFlag": corporate_action_flag,
                "gap": gap,
                "gapSigma": sigma,
                "gapZ": gap_z,
                "retOpenClose": ret_open_close,
                "mfeFromOpen": mfe,
                "maeFromOpen": mae,
                "volumeRatio": volume_ratio,
                "amountRatio": amount_ratio,
                "ret5dBefore": ret_5d_before,
                "ret20dBefore": ret_20d_before,
                "side": None,
                "severity": None,
                "fillRatioClose": None,
                "closeRebound": None,
                "halfFill": None,
                "fullFill": None,
                "givebackRatioClose": None,
                "closeFade": None,
                "fullReversalIntraday": None,
            }

            if gap_z is not None and abs(gap_z) >= 1 and not corporate_action_flag:
                feature["severity"] = _severity(gap_z)
                if gap is not None and gap < 0:
                    gap_size = prev_close - open_price
                    feature.update(
                        {
                            "side": "down",
                            "fillRatioClose": (close - open_price) / gap_size,
                            "closeRebound": close > open_price,
                            "halfFill": high >= open_price + 0.5 * gap_size,
                            "fullFill": high >= prev_close,
                        }
                    )
                elif gap is not None and gap > 0:
                    gap_size = open_price - prev_close
                    feature.update(
                        {
                            "side": "up",
                            "givebackRatioClose": (open_price - close) / gap_size,
                            "closeFade": close < open_price,
                            "fullReversalIntraday": low <= prev_close,
                        }
                    )
            output.append(feature)
            if gap is not None:
                prior_gaps.append(gap)
    return output


def _probability(events: list[dict[str, Any]], key: str) -> float | None:
    values = [bool(item[key]) for item in events if item.get(key) is not None]
    return sum(values) / len(values) if values else None


def summarize_daily_gap_events(features: list[dict[str, Any]], side: str) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in features:
        if item.get("side") == side and item.get("severity"):
            grouped[(str(item["symbol"]), "全部≥1σ")].append(item)
            grouped[(str(item["symbol"]), str(item["severity"]))].append(item)

    summaries: list[dict[str, Any]] = []
    for (symbol, severity), events in sorted(
        grouped.items(), key=lambda entry: (entry[0][0], SEVERITY_ORDER[entry[0][1]])
    ):
        common = {
            "symbol": symbol,
            "severity": severity,
            "eventCount": len(events),
            "medianGap": _median([item["gap"] for item in events if item.get("gap") is not None]),
            "medianGapZ": _median([item["gapZ"] for item in events if item.get("gapZ") is not None]),
            "medianOpenClose": _median(
                [item["retOpenClose"] for item in events if item.get("retOpenClose") is not None]
            ),
            "medianMfe": _median([item["mfeFromOpen"] for item in events if item.get("mfeFromOpen") is not None]),
            "medianMae": _median([item["maeFromOpen"] for item in events if item.get("maeFromOpen") is not None]),
            "maeP05": _quantile([item["maeFromOpen"] for item in events if item.get("maeFromOpen") is not None], 0.05),
            "medianVolumeRatio": _median(
                [item["volumeRatio"] for item in events if item.get("volumeRatio") is not None]
            ),
            "medianAmountRatio": _median(
                [item["amountRatio"] for item in events if item.get("amountRatio") is not None]
            ),
        }
        if side == "down":
            common.update(
                {
                    "pCloseRebound": _probability(events, "closeRebound"),
                    "pHalfFill": _probability(events, "halfFill"),
                    "pFullFill": _probability(events, "fullFill"),
                    "medianFillRatio": _median(
                        [item["fillRatioClose"] for item in events if item.get("fillRatioClose") is not None]
                    ),
                }
            )
        else:
            common.update(
                {
                    "pCloseFade": _probability(events, "closeFade"),
                    "pFullReversal": _probability(events, "fullReversalIntraday"),
                    "medianGiveback": _median(
                        [item["givebackRatioClose"] for item in events if item.get("givebackRatioClose") is not None]
                    ),
                }
            )
        summaries.append(common)
    return summaries


def _load_rows(scope: dict[str, Any], source: str) -> list[dict[str, Any]]:
    asset = scope["asset"]
    selection = scope["selection"]
    time = scope["time"]
    clauses = [
        "asset_class=?",
        "market=?",
        "coalesce(venue,market)=?",
        "resolution=?",
        "data_type=?",
        "adjust=?",
        "source=?",
        f"symbol in ({','.join('?' for _ in selection['values'])})",
        "trade_date>=?",
        "trade_date<=?",
    ]
    params = [
        asset["assetClass"],
        asset["market"],
        asset["venue"],
        asset["resolution"],
        asset["dataType"],
        scope["price"]["adjust"],
        source,
        *selection["values"],
        time["startDate"],
        time["endDate"],
    ]
    with db() as connection:
        rows = connection.execute(
            f"""
            select symbol,trade_date,open,high,low,close,prev_close,volume,amount,source
            from market_daily_bars
            where {' and '.join(clauses)}
            order by symbol,trade_date
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def analyze(scope: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict, list, list, list]:
    normalized = data_gateway.normalize_scope(scope)
    resolved = data_gateway.resolve(normalized)
    checked = preview(normalized, parameters, resolved=resolved)
    if checked["blocking"]:
        raise ValueError(f"daily_gap_analysis_blocked:{','.join(checked['blocking'])}")
    params = checked["resolvedParameters"]
    rows = _load_rows(normalized, str(resolved["source"]))
    features = add_daily_gap_features(
        rows,
        gap_sigma_window=params["gapSigmaWindow"],
        gap_sigma_min_periods=params["gapSigmaMinPeriods"],
        volume_window=params["volumeWindow"],
        volume_min_periods=params["volumeMinPeriods"],
        corporate_action_tolerance=params["corporateActionTolerance"],
    )
    down = summarize_daily_gap_events(features, "down")
    up = summarize_daily_gap_events(features, "up")
    events = [item for item in features if item.get("side")]
    missing_prev_close = sum(item.get("preClose") is None for item in features)
    corporate_actions = sum(bool(item.get("corporateActionFlag")) for item in features)
    warnings = [
        "结果按证券代码和缺口强度分别统计，不跨银行、白酒、有色、保险代理合并平均。",
        "日K只能判断当日最高/最低是否触及目标，不能识别先涨后跌或先跌后涨，也不能计算VWAP、前15分钟确认和回补用时。",
        "量比/额比使用当日总成交量和成交额，仅用于事后分层；开盘时尚不可知，不能作为同日开盘决策的前视特征。",
        "prev_close必须来自交易所前收盘参考价；若上游用上一行close回填，除权除息过滤将不可靠。",
    ]
    if missing_prev_close:
        warnings.append(f"{missing_prev_close}条日K缺少交易所口径prev_close，已排除在缺口事件之外。")
    if not events:
        warnings.append("当前范围没有达到|ZGap|≥1的有效事件；请扩大日期窗口或检查prev_close覆盖。")
    detail_columns = [
        "symbol", "tradeDate", "side", "severity", "gap", "gapZ", "retOpenClose",
        "mfeFromOpen", "maeFromOpen", "fillRatioClose", "givebackRatioClose",
        "closeRebound", "halfFill", "fullFill", "closeFade", "fullReversalIntraday",
        "volumeRatio", "amountRatio", "ret5dBefore", "ret20dBefore",
    ]
    return (
        {
            "symbols": len({item["symbol"] for item in features}),
            "dailyBars": len(features),
            "gapDownEvents": sum(item.get("side") == "down" for item in features),
            "gapUpEvents": sum(item.get("side") == "up" for item in features),
            "corporateActionFlags": corporate_actions,
            "missingPrevClose": missing_prev_close,
            "dailyOnly": True,
            "pooledAcrossSymbols": False,
            "resolvedParameters": params,
        },
        [],
        [
            {
                "name": "低开事件（按代码分别统计）",
                "columns": list(down[0]) if down else [],
                "rows": down,
                "truncated": False,
            },
            {
                "name": "高开事件（按代码分别统计）",
                "columns": list(up[0]) if up else [],
                "rows": up,
                "truncated": False,
            },
            {
                "name": "日线缺口事件明细",
                "columns": detail_columns,
                "rows": [{key: item.get(key) for key in detail_columns} for item in events[:1000]],
                "truncated": len(events) > 1000,
            },
        ],
        warnings,
    )
