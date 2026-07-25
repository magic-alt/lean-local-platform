from __future__ import annotations

import math
import statistics
from typing import Any

from ..core.errors import LeanWebError


NORMALIZATION_TEMPLATES = {
    "zscore": {"description": "Cross-sectional mean/std standardization.", "parameters": {}},
    "winsor_zscore": {
        "description": "Quantile winsorization followed by z-score standardization.",
        "parameters": {"winsorLower": 0.01, "winsorUpper": 0.99},
    },
    "robust_zscore": {
        "description": "Median/MAD standardization with outlier resistance.",
        "parameters": {},
    },
    "rank": {"description": "Cross-sectional percentile rank scaled to [-1, 1].", "parameters": {}},
    "minmax": {"description": "Cross-sectional min/max scaling to [-1, 1].", "parameters": {}},
    "demean": {"description": "Cross-sectional mean centering.", "parameters": {}},
    "raw": {"description": "Preserve the supplied factor values.", "parameters": {}},
}

NEUTRALIZATION_TEMPLATES = {
    "none": {"description": "No neutralization.", "parameters": {}},
    "group_demean": {
        "description": "Demean within one or more categorical groups such as industry.",
        "parameters": {"neutralizeGroups": ["industry"]},
    },
    "exposure_residual": {
        "description": "OLS residualization against numeric exposures such as log market cap and beta.",
        "parameters": {"neutralizeExposures": ["logMarketCap", "beta"]},
    },
    "group_and_exposure": {
        "description": "Group demeaning followed by numeric exposure residualization.",
        "parameters": {
            "neutralizeGroups": ["industry"],
            "neutralizeExposures": ["logMarketCap", "beta"],
        },
    },
}

PORTFOLIO_TEMPLATES = {
    "equal_top": {
        "description": "Equal-weight the highest scores.",
        "parameters": {"topN": 20, "grossExposure": 1.0, "netExposure": 1.0, "maxWeight": 0.1},
    },
    "score_weighted": {
        "description": "Long-only positive-score weights with a per-name cap.",
        "parameters": {"topN": 50, "grossExposure": 1.0, "netExposure": 1.0, "maxWeight": 0.1},
    },
    "rank_weighted": {
        "description": "Long-only descending-rank weights with a per-name cap.",
        "parameters": {"topN": 50, "grossExposure": 1.0, "netExposure": 1.0, "maxWeight": 0.1},
    },
    "long_short": {
        "description": "Dollar-neutral or target-net long/short tails with independent side normalization.",
        "parameters": {"topN": 20, "bottomN": 20, "grossExposure": 1.0, "netExposure": 0.0, "maxWeight": 0.05},
    },
}

ROBUSTNESS_TEMPLATES = {
    "normalization_grid": {
        "dimension": "normalization",
        "values": ["zscore", "winsor_zscore", "robust_zscore", "rank"],
    },
    "neutralization_grid": {
        "dimension": "neutralization",
        "values": ["none", "group_demean", "exposure_residual", "group_and_exposure"],
    },
    "construction_grid": {
        "dimension": "portfolioConstruction",
        "values": ["equal_top", "score_weighted", "rank_weighted", "long_short"],
    },
    "subperiod_grid": {
        "dimension": "subperiod",
        "values": ["expansion", "contraction", "high_volatility", "low_volatility"],
    },
    "cost_stress_grid": {
        "dimension": "costMultiplier",
        "values": [0.5, 1.0, 1.5, 2.0],
    },
}


def factor_templates() -> dict[str, Any]:
    return {
        "normalization": NORMALIZATION_TEMPLATES,
        "neutralization": NEUTRALIZATION_TEMPLATES,
        "portfolioConstruction": PORTFOLIO_TEMPLATES,
        "robustness": ROBUSTNESS_TEMPLATES,
    }


def _finite(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LeanWebError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise LeanWebError(f"{field} must be finite.")
    return number


def _quantile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _normalize(values: list[float], method: str, lower: float, upper: float) -> list[float]:
    if not values:
        return []
    if method not in NORMALIZATION_TEMPLATES:
        raise LeanWebError(f"Unknown normalization method: {method}.")
    working = list(values)
    if method == "raw":
        return working
    if method == "winsor_zscore":
        low_value = _quantile(working, lower)
        high_value = _quantile(working, upper)
        working = [min(high_value, max(low_value, value)) for value in working]
        method = "zscore"
    if method == "rank":
        ordered = sorted(range(len(working)), key=lambda index: working[index])
        ranks = [0.0] * len(working)
        cursor = 0
        while cursor < len(ordered):
            end = cursor
            while end + 1 < len(ordered) and working[ordered[end + 1]] == working[ordered[cursor]]:
                end += 1
            rank = (cursor + end) / 2.0
            for offset in range(cursor, end + 1):
                ranks[ordered[offset]] = rank
            cursor = end + 1
        return [0.0] * len(working) if len(working) == 1 else [2.0 * rank / (len(working) - 1) - 1.0 for rank in ranks]
    if method == "minmax":
        minimum, maximum = min(working), max(working)
        span = maximum - minimum
        return [0.0] * len(working) if span == 0 else [2.0 * (value - minimum) / span - 1.0 for value in working]
    if method == "robust_zscore":
        center = statistics.median(working)
        mad = statistics.median(abs(value - center) for value in working)
        scale = mad * 1.4826
        return [0.0] * len(working) if scale <= 1e-15 else [(value - center) / scale for value in working]
    mean = statistics.fmean(working)
    if method == "demean":
        return [value - mean for value in working]
    variance = sum((value - mean) ** 2 for value in working) / len(working)
    scale = math.sqrt(variance)
    return [0.0] * len(working) if scale <= 1e-15 else [(value - mean) / scale for value in working]


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(matrix[row]) + [vector[row]] for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            augmented[column][column] += 1e-8
            pivot = column
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            augmented[row] = [
                augmented[row][offset] - multiplier * augmented[column][offset]
                for offset in range(size + 1)
            ]
    return [augmented[row][-1] for row in range(size)]


def _residualize(values: list[float], rows: list[dict[str, Any]], exposures: list[str]) -> list[float]:
    if not exposures:
        return values
    design = [[1.0, *[_finite(row.get(field), field) for field in exposures]] for row in rows]
    columns = len(exposures) + 1
    xtx = [
        [sum(design[row][left] * design[row][right] for row in range(len(rows))) for right in range(columns)]
        for left in range(columns)
    ]
    xty = [sum(design[row][column] * values[row] for row in range(len(rows))) for column in range(columns)]
    coefficients = _solve(xtx, xty)
    return [
        values[index] - sum(design[index][column] * coefficients[column] for column in range(columns))
        for index in range(len(rows))
    ]


def process_factor_rows(
    records: list[dict[str, Any]],
    *,
    normalization: str = "winsor_zscore",
    winsor_lower: float = 0.01,
    winsor_upper: float = 0.99,
    neutralize_groups: list[str] | None = None,
    neutralize_exposures: list[str] | None = None,
    partition_by: list[str] | None = None,
) -> dict[str, Any]:
    if not records:
        raise LeanWebError("At least one factor record is required.")
    if not 0 <= winsor_lower < winsor_upper <= 1:
        raise LeanWebError("winsorLower and winsorUpper must satisfy 0 <= lower < upper <= 1.")
    rows = [dict(record) for record in records]
    raw_values = [_finite(row.get("value"), "value") for row in rows]
    groups = list(dict.fromkeys(neutralize_groups or []))
    exposures = list(dict.fromkeys(neutralize_exposures or []))
    partitions = list(dict.fromkeys(partition_by or []))
    partitioned: dict[tuple[str, ...], list[int]] = {}
    for index, row in enumerate(rows):
        partitioned.setdefault(tuple(str(row.get(field) or "") for field in partitions), []).append(index)
    normalized = [0.0] * len(rows)
    neutralized = [0.0] * len(rows)
    for indexes in partitioned.values():
        partition_values = _normalize(
            [raw_values[index] for index in indexes],
            normalization,
            winsor_lower,
            winsor_upper,
        )
        exposure_rows = [dict(rows[index]) for index in indexes]
        if groups:
            grouped: dict[tuple[str, ...], list[int]] = {}
            for local_index, row in enumerate(exposure_rows):
                grouped.setdefault(tuple(str(row.get(field) or "") for field in groups), []).append(local_index)
            for group_indexes in grouped.values():
                value_mean = statistics.fmean(partition_values[index] for index in group_indexes)
                for index in group_indexes:
                    partition_values[index] -= value_mean
                for exposure in exposures:
                    exposure_mean = statistics.fmean(
                        _finite(exposure_rows[index].get(exposure), exposure)
                        for index in group_indexes
                    )
                    for index in group_indexes:
                        exposure_rows[index][exposure] = (
                            _finite(exposure_rows[index].get(exposure), exposure) - exposure_mean
                        )
        partition_scores = _residualize(partition_values, exposure_rows, exposures)
        for local_index, global_index in enumerate(indexes):
            normalized[global_index] = partition_values[local_index]
            neutralized[global_index] = partition_scores[local_index]
    items = []
    for row, raw_value, normalized_value, score in zip(rows, raw_values, normalized, neutralized, strict=True):
        items.append(
            {
                **row,
                "rawValue": raw_value,
                "normalizedValue": normalized_value,
                "neutralizedValue": score,
                "score": score,
            }
        )
    return {
        "normalization": normalization,
        "neutralizeGroups": groups,
        "neutralizeExposures": exposures,
        "partitionBy": partitions,
        "count": len(items),
        "items": items,
    }


def _capped_weights(raw: dict[str, float], target: float, maximum: float) -> dict[str, float]:
    if target <= 1e-15:
        return {key: 0.0 for key in raw}
    if len(raw) * maximum + 1e-12 < target:
        raise LeanWebError("maxWeight is too small for the selected holdings and target exposure.")
    remaining = set(raw)
    weights = {key: 0.0 for key in raw}
    remaining_target = target
    while remaining and remaining_target > 1e-12:
        scale_base = sum(max(0.0, raw[key]) for key in remaining)
        proposals = {
            key: remaining_target / len(remaining)
            if scale_base <= 1e-15
            else remaining_target * max(0.0, raw[key]) / scale_base
            for key in remaining
        }
        capped = {key for key, value in proposals.items() if value > maximum + 1e-12}
        if not capped:
            for key, value in proposals.items():
                weights[key] = value
            break
        for key in capped:
            weights[key] = maximum
            remaining_target -= maximum
            remaining.remove(key)
    return weights


def construct_factor_portfolio(
    records: list[dict[str, Any]],
    *,
    method: str = "equal_top",
    top_n: int = 20,
    bottom_n: int = 20,
    gross_exposure: float = 1.0,
    net_exposure: float = 1.0,
    max_weight: float = 0.1,
) -> dict[str, Any]:
    if method not in PORTFOLIO_TEMPLATES:
        raise LeanWebError(f"Unknown portfolio construction method: {method}.")
    if not records:
        raise LeanWebError("At least one scored factor record is required.")
    if gross_exposure <= 0 or abs(net_exposure) > gross_exposure:
        raise LeanWebError("grossExposure must be positive and abs(netExposure) cannot exceed it.")
    if not 0 < max_weight <= gross_exposure:
        raise LeanWebError("maxWeight must be positive and no greater than grossExposure.")
    scored = [
        (str(row.get("symbol") or "").strip().upper(), _finite(row.get("score", row.get("value")), "score"))
        for row in records
    ]
    if any(not symbol for symbol, _ in scored) or len({symbol for symbol, _ in scored}) != len(scored):
        raise LeanWebError("Portfolio records require unique, non-empty symbols.")
    scored.sort(key=lambda item: item[1], reverse=True)
    long_target = (gross_exposure + net_exposure) / 2.0
    short_target = (gross_exposure - net_exposure) / 2.0
    if method == "long_short" and len(scored) < 2:
        raise LeanWebError("long_short construction requires at least two symbols.")
    long_count = min(top_n, len(scored) // 2) if method == "long_short" else min(top_n, len(scored))
    selected_longs = scored[: max(1, long_count)]
    if method == "equal_top":
        long_raw = {symbol: 1.0 for symbol, _ in selected_longs}
    elif method == "rank_weighted":
        long_raw = {symbol: float(len(selected_longs) - index) for index, (symbol, _) in enumerate(selected_longs)}
    else:
        floor = min(score for _, score in selected_longs)
        long_raw = {symbol: max(score - floor, 0.0) for symbol, score in selected_longs}
    weights = _capped_weights(long_raw, long_target, max_weight)
    if method == "long_short" and short_target > 0:
        short_count = max(1, min(bottom_n, len(scored) - len(selected_longs)))
        selected_shorts = list(reversed(scored[-short_count:]))
        short_floor = min(-score for _, score in selected_shorts)
        short_raw = {symbol: max(-score - short_floor, 0.0) for symbol, score in selected_shorts}
        for symbol, weight in _capped_weights(short_raw, short_target, max_weight).items():
            weights[symbol] = -weight
    ordered = sorted(weights.items(), key=lambda item: item[1], reverse=True)
    return {
        "method": method,
        "grossExposure": sum(abs(weight) for _, weight in ordered),
        "netExposure": sum(weight for _, weight in ordered),
        "maxWeight": max_weight,
        "count": len([weight for _, weight in ordered if abs(weight) > 1e-15]),
        "weights": {symbol: weight for symbol, weight in ordered if abs(weight) > 1e-15},
        "items": [{"symbol": symbol, "weight": weight} for symbol, weight in ordered if abs(weight) > 1e-15],
    }
