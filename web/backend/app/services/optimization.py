from __future__ import annotations

import hashlib
import itertools
import json
from typing import Any

from ..lean_engine.errors import LeanPlatformError


def _coerce_value(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            return text
    return value


def _as_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = [value]
    values = [_coerce_value(item) for item in raw_values]
    return [item for item in values if item not in (None, "")]


def normalize_parameter_grid(
    parameter_grid: dict[str, Any] | None = None,
    *,
    fast_values: list[Any] | None = None,
    slow_values: list[Any] | None = None,
    max_candidates: int = 50,
) -> dict[str, list[Any]]:
    grid = {str(key): _as_values(value) for key, value in (parameter_grid or {}).items()}
    grid = {key: values for key, values in grid.items() if key and values}
    if not grid and (fast_values or slow_values):
        if fast_values:
            grid["fast"] = _as_values(fast_values)
        if slow_values:
            grid["slow"] = _as_values(slow_values)
    if not grid:
        raise LeanPlatformError("parameterGrid must include at least one parameter with one or more values.")
    candidate_count = 1
    for key, values in grid.items():
        if not values:
            raise LeanPlatformError(f"parameterGrid.{key} must contain at least one value.")
        candidate_count *= len(values)
    if candidate_count > max_candidates:
        raise LeanPlatformError(f"parameterGrid expands to {candidate_count} candidates; maxCandidates is {max_candidates}.")
    return grid


def parameter_combinations(base_parameters: dict[str, Any], parameter_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(parameter_grid)
    candidates = []
    for values in itertools.product(*(parameter_grid[key] for key in keys)):
        overrides = dict(zip(keys, values, strict=True))
        candidates.append({**base_parameters, **overrides})
    return candidates


def candidate_suffix(index: int, overrides: dict[str, Any]) -> str:
    payload = json.dumps(overrides, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:8]
    return f"c{index:03d}-{digest}"


def best_candidate(candidates: list[dict[str, Any]], metric: str = "Sharpe Ratio") -> dict[str, Any] | None:
    def score(candidate: dict[str, Any]) -> float:
        value = (candidate.get("statistics") or {}).get(metric)
        if value in (None, ""):
            value = (candidate.get("metrics") or {}).get(metric)
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", "").strip()
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("-inf")

    valid = [candidate for candidate in candidates if candidate.get("status", "success") == "success"]
    return max(valid, key=score, default=None)
