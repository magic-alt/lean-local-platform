from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


DEFAULT_ABSOLUTE_TOLERANCE = 1e-8


def _payload(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("lean_result_must_be_object")
    return value


def _items(payload: dict[str, Any], *names: str) -> list[dict[str, Any]]:
    value: Any = None
    for name in names:
        if name in payload:
            value = payload[name]
            break
    if isinstance(value, dict):
        return [value[key] for key in sorted(value, key=str)]
    return list(value) if isinstance(value, list) else []


def _statistic(payload: dict[str, Any], name: str) -> float | None:
    statistics = payload.get("statistics") or payload.get("Statistics") or {}
    value = statistics.get(name)
    if value is None:
        return None
    text = str(value).replace("%", "").replace("$", "").replace(",", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _close(left: float | None, right: float | None, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def compare_results(
    docker_result: Path,
    native_result: Path,
    *,
    tolerance: float = DEFAULT_ABSOLUTE_TOLERANCE,
) -> dict[str, Any]:
    docker = _payload(docker_result)
    native = _payload(native_result)
    docker_orders = _items(docker, "orders", "Orders")
    native_orders = _items(native, "orders", "Orders")
    docker_trades = _items(docker, "totalPerformance", "TotalPerformance", "trades", "Trades")
    native_trades = _items(native, "totalPerformance", "TotalPerformance", "trades", "Trades")
    checks = {
        "resultSchema": sorted(docker) == sorted(native),
        "orders": docker_orders == native_orders,
        "tradeCount": len(docker_trades) == len(native_trades),
        "endingEquity": _close(
            _statistic(docker, "End Equity"),
            _statistic(native, "End Equity"),
            tolerance,
        ),
        "sharpe": _close(
            _statistic(docker, "Sharpe Ratio"),
            _statistic(native, "Sharpe Ratio"),
            tolerance,
        ),
        "drawdown": _close(
            _statistic(docker, "Drawdown"),
            _statistic(native, "Drawdown"),
            tolerance,
        ),
    }
    return {
        "schemaVersion": 1,
        "passed": all(checks.values()),
        "absoluteTolerance": tolerance,
        "checks": checks,
        "dockerResult": str(docker_result),
        "nativeResult": str(native_result),
    }
