from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "etf-rotation-certification.v1"
ANNUALIZATION_SESSIONS = 252.0
EPSILON = 1e-12
REQUIRED_METRICS = ("sharpe", "maxDrawdown", "turnover", "tradeCount")
REQUIRED_LINEAGE = ("codeVersion", "dataReleaseId", "costModelId")


def _finite_number(value: Any, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


def _bounded_number(
    parameters: Mapping[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
    *,
    integer: bool = False,
) -> int | float:
    number = _finite_number(parameters.get(key, default), field=key)
    if integer:
        if int(number) != number:
            raise ValueError(f"{key} must be an integer.")
        value: int | float = int(number)
    else:
        value = number
    if value < minimum or value > maximum:
        raise ValueError(f"{key} must be in [{minimum}, {maximum}].")
    return value


def validate_parameters(
    parameters: Mapping[str, Any],
    *,
    symbol_count: int | None = None,
) -> dict[str, int | float]:
    clean: dict[str, int | float] = {
        "lookback": _bounded_number(parameters, "lookback", 63, 2, 504, integer=True),
        "rebalanceDays": _bounded_number(
            parameters,
            "rebalanceDays",
            21,
            1,
            126,
            integer=True,
        ),
        "selectionCount": _bounded_number(
            parameters,
            "selectionCount",
            2,
            1,
            20,
            integer=True,
        ),
        "volatilityLookback": _bounded_number(
            parameters,
            "volatilityLookback",
            60,
            2,
            252,
            integer=True,
        ),
        "targetVolatility": _bounded_number(
            parameters,
            "targetVolatility",
            0.10,
            0.01,
            1.0,
        ),
        "maxWeight": _bounded_number(parameters, "maxWeight", 0.60, 0.01, 1.0),
        "maxTurnover": _bounded_number(parameters, "maxTurnover", 0.25, 0.01, 1.0),
        "commissionPerOrder": _bounded_number(
            parameters,
            "commissionPerOrder",
            1.0,
            0.0,
            100.0,
        ),
        "slippageBps": _bounded_number(
            parameters,
            "slippageBps",
            2.0,
            0.0,
            100.0,
        ),
    }
    if symbol_count is not None and int(clean["selectionCount"]) > symbol_count:
        raise ValueError(
            f"selectionCount={clean['selectionCount']} exceeds symbol count={symbol_count}."
        )
    return clean


def _validated_prices(values: Sequence[Any], *, field: str) -> list[float]:
    prices = [_finite_number(value, field=field) for value in values]
    if any(price <= 0 for price in prices):
        raise ValueError(f"{field} prices must be positive.")
    return prices


def momentum_score(prices: Sequence[Any], lookback: int) -> float | None:
    if len(prices) < lookback + 1:
        return None
    window = _validated_prices(prices[-(lookback + 1) :], field="momentum")
    score = window[-1] / window[0] - 1.0
    return score if math.isfinite(score) else None


def annualized_volatility(prices: Sequence[Any], lookback: int) -> float | None:
    if len(prices) < lookback + 1:
        return None
    window = _validated_prices(prices[-(lookback + 1) :], field="volatility")
    returns = [
        window[index] / window[index - 1] - 1.0
        for index in range(1, len(window))
    ]
    if len(returns) < 2:
        return None
    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / (
        len(returns) - 1
    )
    if not math.isfinite(variance) or variance <= 1e-16:
        return None
    volatility = math.sqrt(variance) * math.sqrt(ANNUALIZATION_SESSIONS)
    if not math.isfinite(volatility) or volatility <= 1e-8:
        return None
    return volatility


def stable_rank(
    momentum: Mapping[str, Any],
    *,
    selection_count: int,
    positive_only: bool = True,
) -> list[str]:
    rows: list[tuple[float, str]] = []
    for symbol, value in momentum.items():
        score = _finite_number(value, field=f"momentum[{symbol}]")
        if positive_only and score <= 0:
            continue
        rows.append((score, str(symbol).upper()))
    rows.sort(key=lambda row: (-row[0], row[1]))
    return [symbol for _, symbol in rows[:selection_count]]


def inverse_volatility_weights(
    volatilities: Mapping[str, Any],
    *,
    max_weight: float,
) -> dict[str, float]:
    maximum = _finite_number(max_weight, field="maxWeight")
    if maximum <= 0 or maximum > 1:
        raise ValueError("maxWeight must be in (0, 1].")
    inverse: dict[str, float] = {}
    for symbol, raw_value in volatilities.items():
        volatility = _finite_number(raw_value, field=f"volatility[{symbol}]")
        if volatility <= 1e-8:
            continue
        inverse[str(symbol).upper()] = 1.0 / volatility
    active = sorted(inverse)
    weights: dict[str, float] = {}
    remaining_mass = 1.0
    while active and remaining_mass > EPSILON:
        denominator = sum(inverse[symbol] for symbol in active)
        if denominator <= 0 or not math.isfinite(denominator):
            break
        proposed = {
            symbol: remaining_mass * inverse[symbol] / denominator
            for symbol in active
        }
        capped = [
            symbol
            for symbol in active
            if proposed[symbol] > maximum + EPSILON
        ]
        if not capped:
            weights.update(proposed)
            break
        for symbol in capped:
            weights[symbol] = maximum
            remaining_mass = max(0.0, remaining_mass - maximum)
            active.remove(symbol)
    return {symbol: weights[symbol] for symbol in sorted(weights)}


def volatility_targeted_weights(
    weights: Mapping[str, Any],
    volatilities: Mapping[str, Any],
    *,
    target_volatility: float,
) -> tuple[dict[str, float], float | None, float]:
    target = _finite_number(target_volatility, field="targetVolatility")
    if target <= 0:
        raise ValueError("targetVolatility must be positive.")
    clean_weights = {
        str(symbol).upper(): _finite_number(value, field=f"weight[{symbol}]")
        for symbol, value in weights.items()
    }
    clean_vols = {
        str(symbol).upper(): _finite_number(value, field=f"volatility[{symbol}]")
        for symbol, value in volatilities.items()
    }
    estimate = math.sqrt(
        sum(
            (weight * clean_vols.get(symbol, 0.0)) ** 2
            for symbol, weight in clean_weights.items()
        )
    )
    if not math.isfinite(estimate) or estimate <= EPSILON:
        return {}, None, 0.0
    scale = min(1.0, target / estimate)
    scaled = {
        symbol: weight * scale
        for symbol, weight in clean_weights.items()
    }
    return scaled, estimate, scale


def one_way_turnover(
    current_weights: Mapping[str, Any],
    target_weights: Mapping[str, Any],
    *,
    symbols: Iterable[str] | None = None,
) -> float:
    universe = (
        {str(symbol).upper() for symbol in symbols}
        if symbols is not None
        else {
            *(str(symbol).upper() for symbol in current_weights),
            *(str(symbol).upper() for symbol in target_weights),
        }
    )
    current = {
        str(symbol).upper(): _finite_number(value, field=f"current[{symbol}]")
        for symbol, value in current_weights.items()
    }
    target = {
        str(symbol).upper(): _finite_number(value, field=f"target[{symbol}]")
        for symbol, value in target_weights.items()
    }
    return 0.5 * sum(
        abs(target.get(symbol, 0.0) - current.get(symbol, 0.0))
        for symbol in universe
    )


def turnover_limited_targets(
    current_weights: Mapping[str, Any],
    requested_targets: Mapping[str, Any],
    *,
    universe: Sequence[str],
    tradable_symbols: Iterable[str],
    max_turnover: float,
) -> tuple[dict[str, float], float, float]:
    maximum = _finite_number(max_turnover, field="maxTurnover")
    if maximum <= 0 or maximum > 1:
        raise ValueError("maxTurnover must be in (0, 1].")
    normalized_universe = [str(symbol).upper() for symbol in universe]
    tradable = {str(symbol).upper() for symbol in tradable_symbols}
    current = {
        str(symbol).upper(): _finite_number(value, field=f"current[{symbol}]")
        for symbol, value in current_weights.items()
    }
    requested = {
        str(symbol).upper(): _finite_number(value, field=f"target[{symbol}]")
        for symbol, value in requested_targets.items()
    }
    frozen_gross = sum(
        max(0.0, current.get(symbol, 0.0))
        for symbol in normalized_universe
        if symbol not in tradable
    )
    available_gross = max(0.0, 1.0 - frozen_gross)
    requested_gross = sum(
        max(0.0, requested.get(symbol, 0.0))
        for symbol in normalized_universe
        if symbol in tradable
    )
    allocation_scale = (
        min(1.0, available_gross / requested_gross)
        if requested_gross > EPSILON
        else 0.0
    )
    desired = {
        symbol: (
            requested.get(symbol, 0.0) * allocation_scale
            if symbol in tradable
            else current.get(symbol, 0.0)
        )
        for symbol in normalized_universe
    }
    requested_turnover = one_way_turnover(
        current,
        desired,
        symbols=normalized_universe,
    )
    if requested_turnover <= maximum + EPSILON:
        return desired, requested_turnover, requested_turnover
    scale = maximum / requested_turnover
    limited = {
        symbol: current.get(symbol, 0.0)
        + (desired[symbol] - current.get(symbol, 0.0)) * scale
        for symbol in normalized_universe
    }
    applied = one_way_turnover(
        current,
        limited,
        symbols=normalized_universe,
    )
    return limited, requested_turnover, applied


def static_equal_weight_baseline(
    symbols: Sequence[str],
    *,
    current_weights: Mapping[str, Any] | None = None,
    tradable_symbols: Iterable[str] | None = None,
    max_turnover: float = 1.0,
) -> dict[str, Any]:
    universe = sorted({str(symbol).upper() for symbol in symbols if str(symbol).strip()})
    if not universe:
        raise ValueError("static baseline requires at least one symbol.")
    requested = {symbol: 1.0 / len(universe) for symbol in universe}
    current = current_weights or {}
    tradable = set(tradable_symbols or universe)
    limited, requested_turnover, applied_turnover = turnover_limited_targets(
        current,
        requested,
        universe=universe,
        tradable_symbols=tradable,
        max_turnover=max_turnover,
    )
    return {
        "strategy": "static_equal_weight",
        "selected": universe,
        "requestedTargets": requested,
        "targets": limited,
        "requestedTurnover": requested_turnover,
        "appliedTurnover": applied_turnover,
    }


def rotation_reference(
    prices_by_symbol: Mapping[str, Sequence[Any]],
    parameters: Mapping[str, Any],
    *,
    current_weights: Mapping[str, Any] | None = None,
    tradable_symbols: Iterable[str] | None = None,
) -> dict[str, Any]:
    universe = sorted(
        {
            str(symbol).upper()
            for symbol in prices_by_symbol
            if str(symbol).strip()
        }
    )
    if len(universe) < 2:
        raise ValueError("ETF rotation requires at least two symbols.")
    clean_parameters = validate_parameters(parameters, symbol_count=len(universe))
    lookback = int(clean_parameters["lookback"])
    volatility_lookback = int(clean_parameters["volatilityLookback"])
    selection_count = int(clean_parameters["selectionCount"])
    tradable = {
        str(symbol).upper()
        for symbol in (tradable_symbols if tradable_symbols is not None else universe)
    }
    momentum: dict[str, float] = {}
    volatilities: dict[str, float] = {}
    exclusions: dict[str, str] = {}
    normalized_prices = {
        str(symbol).upper(): values
        for symbol, values in prices_by_symbol.items()
    }
    for symbol in universe:
        if symbol not in tradable:
            exclusions[symbol] = "not_tradable"
            continue
        prices = normalized_prices[symbol]
        try:
            score = momentum_score(prices, lookback)
            volatility = annualized_volatility(prices, volatility_lookback)
        except ValueError:
            exclusions[symbol] = "invalid_price_history"
            continue
        if score is None:
            exclusions[symbol] = "insufficient_momentum_history"
            continue
        if volatility is None:
            exclusions[symbol] = "invalid_or_zero_volatility"
            continue
        momentum[symbol] = score
        volatilities[symbol] = volatility

    selected = stable_rank(
        momentum,
        selection_count=selection_count,
        positive_only=True,
    )
    selected_volatilities = {
        symbol: volatilities[symbol]
        for symbol in selected
    }
    requested_targets: dict[str, float] = {}
    diagonal_estimate: float | None = None
    volatility_scale = 0.0
    failure_reasons: list[str] = []
    if selected_volatilities:
        risk_weights = inverse_volatility_weights(
            selected_volatilities,
            max_weight=float(clean_parameters["maxWeight"]),
        )
        requested_targets, diagonal_estimate, volatility_scale = (
            volatility_targeted_weights(
                risk_weights,
                selected_volatilities,
                target_volatility=float(clean_parameters["targetVolatility"]),
            )
        )
        if not requested_targets:
            failure_reasons.append("volatility_target_unavailable")
    else:
        failure_reasons.append("zero_eligible_candidates")

    current = current_weights or {}
    limited, requested_turnover, applied_turnover = turnover_limited_targets(
        current,
        requested_targets,
        universe=universe,
        tradable_symbols=tradable,
        max_turnover=float(clean_parameters["maxTurnover"]),
    )
    return {
        "strategy": "momentum_inverse_volatility_target",
        "schemaVersion": SCHEMA_VERSION,
        "selected": selected,
        "momentum": {symbol: momentum[symbol] for symbol in sorted(momentum)},
        "annualizedVolatility": {
            symbol: volatilities[symbol]
            for symbol in sorted(volatilities)
        },
        "exclusions": {symbol: exclusions[symbol] for symbol in sorted(exclusions)},
        "requestedTargets": {
            symbol: requested_targets.get(symbol, 0.0)
            for symbol in universe
        },
        "targets": {symbol: limited[symbol] for symbol in universe},
        "requestedTurnover": requested_turnover,
        "appliedTurnover": applied_turnover,
        "diagonalVolatilityEstimate": diagonal_estimate,
        "volatilityScale": volatility_scale,
        "grossExposure": sum(limited.values()),
        "failureReasons": failure_reasons,
    }


def trading_session_due_indexes(
    fresh_session_flags: Sequence[bool],
    *,
    rebalance_days: int,
) -> list[int]:
    if rebalance_days < 1:
        raise ValueError("rebalanceDays must be positive.")
    due: list[int] = []
    sessions = 0
    for index, is_fresh in enumerate(fresh_session_flags):
        if not is_fresh:
            continue
        sessions += 1
        if sessions >= rebalance_days:
            due.append(index)
            sessions = 0
    return due


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _metric_payload(payload: Mapping[str, Any], *, label: str) -> dict[str, float]:
    source = payload.get("metrics") if isinstance(payload.get("metrics"), Mapping) else payload
    metrics: dict[str, float] = {}
    for key in REQUIRED_METRICS:
        if key not in source:
            raise ValueError(f"{label} missing metric: {key}")
        metrics[key] = _finite_number(source[key], field=f"{label}.{key}")
    if metrics["maxDrawdown"] < 0:
        raise ValueError(f"{label}.maxDrawdown must be a non-negative ratio.")
    if metrics["turnover"] < 0:
        raise ValueError(f"{label}.turnover must be non-negative.")
    if metrics["tradeCount"] < 0 or int(metrics["tradeCount"]) != metrics["tradeCount"]:
        raise ValueError(f"{label}.tradeCount must be a non-negative integer.")
    return metrics


def _lineage_payload(payload: Mapping[str, Any], *, label: str) -> dict[str, str]:
    source = payload.get("lineage")
    if not isinstance(source, Mapping):
        raise ValueError(f"{label} missing lineage.")
    lineage: dict[str, str] = {}
    for key in REQUIRED_LINEAGE:
        value = str(source.get(key) or "").strip()
        if not value:
            raise ValueError(f"{label} missing lineage field: {key}")
        lineage[key] = value
    return lineage


def build_certification_report(
    *,
    candidate: Mapping[str, Any],
    baseline: Mapping[str, Any],
    gates: Mapping[str, Any],
    deterministic_fingerprints: Sequence[str],
) -> dict[str, Any]:
    candidate_metrics = _metric_payload(candidate, label="candidate")
    baseline_metrics = _metric_payload(baseline, label="baseline")
    candidate_lineage = _lineage_payload(candidate, label="candidate")
    baseline_lineage = _lineage_payload(baseline, label="baseline")
    fingerprints = [str(value).strip() for value in deterministic_fingerprints if str(value).strip()]

    failures: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, **details: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "details": details})
        if not passed:
            failures.append(name)

    check(
        "deterministic_rerun_match",
        len(fingerprints) >= 2 and len(set(fingerprints)) == 1,
        fingerprints=fingerprints,
    )
    check(
        "data_release_match",
        candidate_lineage["dataReleaseId"] == baseline_lineage["dataReleaseId"],
        candidate=candidate_lineage["dataReleaseId"],
        baseline=baseline_lineage["dataReleaseId"],
    )
    check(
        "cost_model_match",
        candidate_lineage["costModelId"] == baseline_lineage["costModelId"],
        candidate=candidate_lineage["costModelId"],
        baseline=baseline_lineage["costModelId"],
    )

    optional_gate_specs = (
        ("minimum_sharpe", "minimumSharpe", candidate_metrics["sharpe"], ">="),
        ("maximum_drawdown", "maximumDrawdown", candidate_metrics["maxDrawdown"], "<="),
        ("maximum_turnover", "maximumTurnover", candidate_metrics["turnover"], "<="),
        ("minimum_trade_count", "minimumTradeCount", candidate_metrics["tradeCount"], ">="),
    )
    for name, gate_key, actual, operator in optional_gate_specs:
        if gate_key not in gates:
            continue
        threshold = _finite_number(gates[gate_key], field=gate_key)
        passed = actual >= threshold if operator == ">=" else actual <= threshold
        check(name, passed, actual=actual, operator=operator, threshold=threshold)

    sharpe_tolerance = _finite_number(
        gates.get("sharpeVsBaselineTolerance", 0.0),
        field="sharpeVsBaselineTolerance",
    )
    drawdown_tolerance = _finite_number(
        gates.get("drawdownVsBaselineTolerance", 0.0),
        field="drawdownVsBaselineTolerance",
    )
    check(
        "sharpe_not_worse_than_baseline",
        candidate_metrics["sharpe"] + sharpe_tolerance >= baseline_metrics["sharpe"],
        candidate=candidate_metrics["sharpe"],
        baseline=baseline_metrics["sharpe"],
        tolerance=sharpe_tolerance,
    )
    check(
        "drawdown_not_worse_than_baseline",
        candidate_metrics["maxDrawdown"]
        <= baseline_metrics["maxDrawdown"] + drawdown_tolerance,
        candidate=candidate_metrics["maxDrawdown"],
        baseline=baseline_metrics["maxDrawdown"],
        tolerance=drawdown_tolerance,
    )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "passed": not failures,
        "failureReasons": failures,
        "candidate": {
            "metrics": candidate_metrics,
            "lineage": candidate_lineage,
        },
        "baseline": {
            "metrics": baseline_metrics,
            "lineage": baseline_lineage,
        },
        "metricDelta": {
            key: candidate_metrics[key] - baseline_metrics[key]
            for key in REQUIRED_METRICS
        },
        "checks": checks,
        "deterministicFingerprints": fingerprints,
    }


def run_regression_matrix(fixture: Mapping[str, Any]) -> dict[str, Any]:
    parameters = fixture.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("fixture.parameters must be an object.")
    rows: list[dict[str, Any]] = []
    for scenario in fixture.get("scenarios") or []:
        if not isinstance(scenario, Mapping):
            raise ValueError("fixture.scenarios entries must be objects.")
        result = rotation_reference(
            scenario.get("prices") or {},
            {**parameters, **(scenario.get("parameters") or {})},
            current_weights=scenario.get("currentWeights") or {},
            tradable_symbols=scenario.get("tradableSymbols"),
        )
        rows.append(
            {
                "id": str(scenario.get("id") or ""),
                "fingerprint": canonical_fingerprint(result),
                "result": result,
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "rows": rows,
        "fingerprint": canonical_fingerprint(
            [{"id": row["id"], "fingerprint": row["fingerprint"]} for row in rows]
        ),
    }
