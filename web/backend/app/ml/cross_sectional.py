from __future__ import annotations

import calendar
import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Sequence

import polars as pl


FEATURE_VERSION = "csi300-lgbm-ranker-v1"
FEATURE_COLUMNS = (
    "ret_1", "ret_5", "ret_10", "ret_20", "ret_60",
    "close_to_ma_5", "close_to_ma_20", "close_to_ma_60",
    "ma5_to_ma20", "ma20_to_ma60", "vol_5", "vol_20", "vol_60",
    "atr_14", "max_drawdown_20", "downside_vol_20", "log_amount_mean_20",
    "amount_ratio_20", "turnover_mean_5", "amihud_20", "turnover_rate",
    "volume_ratio", "earnings_yield_ttm", "book_to_price",
    "sales_to_price_ttm", "log_total_mv", "roe", "grossprofit_margin",
    "netprofit_yoy", "or_yoy", "debt_to_assets",
    "operating_cashflow_to_profit",
)
QUALITY_THRESHOLDS = {"meanRankIc": 0.02, "annualizedIcir": 0.5, "q5MinusQ1": 0.0}


@dataclass(frozen=True)
class WalkForwardFold:
    index: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "trainStart": self.train_start,
            "trainEnd": self.train_end,
            "validationStart": self.validation_start,
            "validationEnd": self.validation_end,
            "testStart": self.test_start,
            "testEnd": self.test_end,
        }


def _safe_div(numerator: pl.Expr, denominator: pl.Expr) -> pl.Expr:
    return pl.when(denominator.abs() > 1e-12).then(numerator / denominator).otherwise(None)


def build_price_features(frame: pl.DataFrame) -> pl.DataFrame:
    """Build causal price/volume features from raw prices and adjustment factors."""
    required = {"symbol", "trade_date", "open", "high", "low", "close", "amount", "adj_factor"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Missing price columns: {', '.join(missing)}")
    data = frame.sort(["symbol", "trade_date"]).with_columns(
        (pl.col("close") * pl.col("adj_factor")).alias("adj_close"),
        pl.col("close").shift(1).over("symbol").alias("previous_close"),
    )
    data = data.with_columns(
        (pl.col("adj_close") / pl.col("adj_close").shift(1).over("symbol") - 1).alias("daily_return"),
        pl.max_horizontal(
            pl.col("high") - pl.col("low"),
            (pl.col("high") - pl.col("previous_close")).abs(),
            (pl.col("low") - pl.col("previous_close")).abs(),
        ).alias("true_range"),
    )
    expressions: list[pl.Expr] = []
    for window in (1, 5, 10, 20, 60):
        expressions.append(
            (pl.col("adj_close") / pl.col("adj_close").shift(window).over("symbol") - 1).alias(f"ret_{window}")
        )
    for window in (5, 20, 60):
        expressions.extend(
            [
                pl.col("adj_close").rolling_mean(window).over("symbol").alias(f"ma_{window}"),
                pl.col("daily_return").rolling_std(window).over("symbol").alias(f"vol_{window}"),
            ]
        )
    data = data.with_columns(expressions)
    rolling_peak = pl.col("adj_close").rolling_max(20).over("symbol")
    data = data.with_columns(
        (_safe_div(pl.col("adj_close"), pl.col("ma_5")) - 1).alias("close_to_ma_5"),
        (_safe_div(pl.col("adj_close"), pl.col("ma_20")) - 1).alias("close_to_ma_20"),
        (_safe_div(pl.col("adj_close"), pl.col("ma_60")) - 1).alias("close_to_ma_60"),
        (_safe_div(pl.col("ma_5"), pl.col("ma_20")) - 1).alias("ma5_to_ma20"),
        (_safe_div(pl.col("ma_20"), pl.col("ma_60")) - 1).alias("ma20_to_ma60"),
        pl.col("true_range").rolling_mean(14).over("symbol").alias("atr_14"),
        (pl.col("adj_close") / rolling_peak - 1).rolling_min(20).over("symbol").alias("max_drawdown_20"),
        pl.when(pl.col("daily_return") < 0).then(pl.col("daily_return")).otherwise(0.0)
        .rolling_std(20).over("symbol").alias("downside_vol_20"),
        pl.col("amount").rolling_mean(20).over("symbol").log().alias("log_amount_mean_20"),
        _safe_div(pl.col("amount"), pl.col("amount").rolling_mean(20).over("symbol")).alias("amount_ratio_20"),
        pl.col("turnover_rate").rolling_mean(5).over("symbol").alias("turnover_mean_5"),
        _safe_div(pl.col("daily_return").abs(), pl.col("amount"))
        .rolling_mean(20).over("symbol").alias("amihud_20"),
    )
    return data.drop(["previous_close", "daily_return", "true_range", "ma_5", "ma_20", "ma_60"])


def add_valuation_features(frame: pl.DataFrame) -> pl.DataFrame:
    expressions = []
    for source, target in (("pe_ttm", "earnings_yield_ttm"), ("pb", "book_to_price"), ("ps_ttm", "sales_to_price_ttm")):
        expressions.append(_safe_div(pl.lit(1.0), pl.col(source)).alias(target))
    expressions.append(pl.when(pl.col("total_mv") > 0).then(pl.col("total_mv").log()).otherwise(None).alias("log_total_mv"))
    return frame.with_columns(expressions)


def add_forward_labels(
    frame: pl.DataFrame, benchmark: pl.DataFrame, horizon: int = 5, eligibility_column: str | None = None,
) -> pl.DataFrame:
    """Label t signals using t+1 raw open through t+h raw close and adjusted returns."""
    if horizon != 5:
        raise ValueError("The first research template fixes the horizon at five trading days.")
    ordered = frame.sort(["symbol", "trade_date"]).with_columns(
        (pl.col("open").shift(-1).over("symbol") * pl.col("adj_factor").shift(-1).over("symbol")).alias("entry_price"),
        (pl.col("close").shift(-horizon).over("symbol") * pl.col("adj_factor").shift(-horizon).over("symbol")).alias("exit_price"),
    )
    benchmark_returns = benchmark.sort("trade_date").with_columns(
        (pl.col("open").shift(-1) * pl.col("adj_factor").shift(-1)).alias("benchmark_entry"),
        (pl.col("close").shift(-horizon) * pl.col("adj_factor").shift(-horizon)).alias("benchmark_exit"),
    ).select(
        "trade_date",
        (pl.col("benchmark_exit") / pl.col("benchmark_entry")).log().alias("benchmark_forward_return"),
    )
    labelled = ordered.join(benchmark_returns, on="trade_date", how="left").with_columns(
        ((pl.col("exit_price") / pl.col("entry_price")).log() - pl.col("benchmark_forward_return")).alias("label_return")
    )
    eligible_label = (
        pl.when(pl.col(eligibility_column).cast(pl.Boolean)).then(pl.col("label_return")).otherwise(None)
        if eligibility_column else pl.col("label_return")
    )
    valid_count = eligible_label.count().over("trade_date")
    percentile = eligible_label.rank(method="average").over("trade_date") / valid_count
    return labelled.with_columns(
        pl.when(eligible_label.is_not_null() & (valid_count >= 150))
        .then((percentile * 5).ceil().clip(1, 5).cast(pl.Int8) - 1)
        .otherwise(None)
        .alias("relevance")
    ).drop(["entry_price", "exit_price", "benchmark_forward_return"])


def preprocess_cross_section(frame: pl.DataFrame, features: Sequence[str] = FEATURE_COLUMNS) -> pl.DataFrame:
    """Winsorize, SW-L1 demean, size-residualize and z-score per trade date."""
    result = frame
    available = [feature for feature in features if feature in result.columns]
    for feature in available:
        clipped = f"__{feature}_clip"
        result = result.with_columns(
            pl.col(feature).clip(
                pl.col(feature).quantile(0.01).over("trade_date"),
                pl.col(feature).quantile(0.99).over("trade_date"),
            ).alias(clipped)
        )
        if feature != "log_total_mv":
            grouped = f"__{feature}_grouped"
            industry_count = pl.col(clipped).count().over(["trade_date", "industry_code"])
            result = result.with_columns(
                pl.when(pl.col("industry_code").is_not_null() & (industry_count >= 5))
                .then(pl.col(clipped) - pl.col(clipped).mean().over(["trade_date", "industry_code"]))
                .otherwise(pl.col(clipped))
                .alias(grouped)
            )
            x = pl.col("log_total_mv") - pl.col("log_total_mv").mean().over("trade_date")
            y = pl.col(grouped) - pl.col(grouped).mean().over("trade_date")
            beta = _safe_div((x * y).mean().over("trade_date"), (x * x).mean().over("trade_date"))
            result = result.with_columns((pl.col(grouped) - beta * x).alias(clipped)).drop(grouped)
        mean = pl.col(clipped).mean().over("trade_date")
        std = pl.col(clipped).std().over("trade_date")
        result = result.with_columns(
            pl.when(std > 1e-12).then((pl.col(clipped) - mean) / std).otherwise(0.0).alias(feature)
        ).drop(clipped)
    return result


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _at_or_after(dates: Sequence[date], target: date) -> int | None:
    return next((index for index, value in enumerate(dates) if value >= target), None)


def build_walk_forward_plan(
    trading_dates: Iterable[str], *, purge_days: int = 5, embargo_days: int = 5,
) -> dict[str, Any]:
    dates = sorted({date.fromisoformat(str(value)[:10]) for value in trading_dates})
    if len(dates) < 252 * 7:
        raise ValueError("At least seven years of trading dates are required for 5y/6m/3m walk-forward validation.")
    holdout_start_target = _add_months(dates[-1], -12)
    holdout_start_index = _at_or_after(dates, holdout_start_target)
    if holdout_start_index is None:
        raise ValueError("Unable to locate final holdout boundary.")
    folds: list[WalkForwardFold] = []
    test_start_target = _add_months(dates[0], 66)
    while True:
        validation_start_index = _at_or_after(dates, _add_months(test_start_target, -6))
        test_start_index = _at_or_after(dates, test_start_target)
        test_end_index = _at_or_after(dates, _add_months(test_start_target, 3))
        if validation_start_index is None or test_start_index is None or test_end_index is None:
            break
        if test_end_index >= holdout_start_index:
            break
        train_end_index = validation_start_index - purge_days - 1
        validation_end_index = test_start_index - embargo_days - 1
        train_start_index = _at_or_after(dates, _add_months(dates[validation_start_index], -60))
        if train_start_index is not None and train_end_index > train_start_index and validation_end_index >= validation_start_index:
            folds.append(WalkForwardFold(
                len(folds), dates[train_start_index].isoformat(), dates[train_end_index].isoformat(),
                dates[validation_start_index].isoformat(), dates[validation_end_index].isoformat(),
                dates[test_start_index].isoformat(), dates[test_end_index - 1].isoformat(),
            ))
        test_start_target = _add_months(test_start_target, 3)
    if not folds:
        raise ValueError("No complete pre-holdout walk-forward fold could be constructed.")
    return {
        "purgeTradingDays": purge_days,
        "embargoTradingDays": embargo_days,
        "folds": [fold.as_dict() for fold in folds],
        "holdout": {"start": dates[holdout_start_index].isoformat(), "end": dates[-1].isoformat()},
    }


def spearman_rank_correlation(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    if len(actual) != len(predicted) or len(actual) < 2:
        return None

    def ranks(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda index: values[index])
        output = [0.0] * len(values)
        cursor = 0
        while cursor < len(order):
            end = cursor
            while end + 1 < len(order) and values[order[end + 1]] == values[order[cursor]]:
                end += 1
            rank = (cursor + end) / 2.0
            for offset in range(cursor, end + 1):
                output[order[offset]] = rank
            cursor = end + 1
        return output

    left, right = ranks(actual), ranks(predicted)
    left_mean, right_mean = statistics.fmean(left), statistics.fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)
    )
    return None if denominator <= 1e-15 else numerator / denominator


def prediction_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("label_return") is None or row.get("score") is None:
            continue
        by_date.setdefault(str(row["trade_date"]), []).append(row)
    daily_ic: list[float] = []
    daily_spreads: list[float] = []
    quantile_returns: list[list[float]] = [[] for _ in range(5)]
    for items in by_date.values():
        if len(items) < 5:
            continue
        ic = spearman_rank_correlation(
            [float(item["label_return"]) for item in items], [float(item["score"]) for item in items]
        )
        if ic is not None:
            daily_ic.append(ic)
        ordered = sorted(items, key=lambda item: float(item["score"]))
        for index, item in enumerate(ordered):
            bucket = min(4, index * 5 // len(ordered))
            quantile_returns[bucket].append(float(item["label_return"]))
        bottom = ordered[: max(1, len(ordered) // 5)]
        top = ordered[-max(1, len(ordered) // 5):]
        daily_spreads.append(
            statistics.fmean(float(item["label_return"]) for item in top)
            - statistics.fmean(float(item["label_return"]) for item in bottom)
        )
    mean_ic = statistics.fmean(daily_ic) if daily_ic else None
    ic_std = statistics.stdev(daily_ic) if len(daily_ic) > 1 else None
    icir = None if mean_ic is None or not ic_std else mean_ic / ic_std * math.sqrt(252)
    q_returns = [statistics.fmean(values) if values else None for values in quantile_returns]
    spread = statistics.fmean(daily_spreads) if daily_spreads else None
    monotonic = all(
        q_returns[index] is not None and q_returns[index + 1] is not None
        and q_returns[index] <= q_returns[index + 1]
        for index in range(4)
    )
    return {
        "dateCount": len(by_date), "meanRankIc": mean_ic, "annualizedIcir": icir,
        "q1": q_returns[0], "q2": q_returns[1], "q3": q_returns[2],
        "q4": q_returns[3], "q5": q_returns[4], "q5MinusQ1": spread,
        "groupMonotonic": monotonic,
    }


def assess_quality(rolling: dict[str, Any], holdout: dict[str, Any]) -> dict[str, Any]:
    checks = []
    for split, metrics in (("rollingOos", rolling), ("finalHoldout", holdout)):
        for metric, threshold in QUALITY_THRESHOLDS.items():
            value = metrics.get(metric)
            passed = value is not None and (
                float(value) > threshold if metric == "q5MinusQ1" else float(value) >= threshold
            )
            checks.append({
                "split": split, "metric": metric, "value": value, "threshold": threshold,
                "passed": passed,
            })
    return {"qualified": all(check["passed"] for check in checks), "advisory": True, "checks": checks}


def candidate_grid() -> list[dict[str, Any]]:
    return [
        {"num_leaves": leaves, "min_child_samples": minimum, "learning_rate": rate}
        for leaves in (15, 31) for minimum in (50, 100) for rate in (0.03, 0.05)
    ]
