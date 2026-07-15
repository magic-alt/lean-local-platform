from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR
from ..db import db, json_dump, utc_now
from ..repositories.backtest_repository import get_backtest, update_backtest


def _number(value: Any, *, percent: bool = False) -> float | None:
    if value in (None, "", "-"):
        return None
    text = str(value).strip().replace(",", "").replace("¥", "").replace("$", "")
    has_percent = text.endswith("%")
    if has_percent:
        text = text[:-1]
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result / 100.0 if has_percent or percent else result


def _gate(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": "ok" if passed else "critical",
        "details": details,
    }


def _filled_events(result_path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    events_path = result_path.parent / f"{result_path.stem}-order-events.json"
    if events_path.exists():
        try:
            events = json.loads(events_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            events = []
        return [event for event in events if str(event.get("status") or "").lower() == "filled"]
    orders = payload.get("orders") or payload.get("Orders") or {}
    values = list(orders.values()) if isinstance(orders, dict) else list(orders) if isinstance(orders, list) else []
    return [
        {
            "orderId": order.get("id"),
            "symbolValue": ((order.get("symbol") or {}).get("value") if isinstance(order.get("symbol"), dict) else order.get("symbol")),
            "fillQuantity": order.get("quantity"),
            "fillPrice": order.get("price"),
            "orderFeeAmount": 0,
            "status": "filled",
        }
        for order in values
        if order.get("status") in {2, 3, "filled", "Filled"}
    ]


def _position_and_cash(events: list[dict[str, Any]], initial_cash: float) -> dict[str, Any]:
    positions: dict[str, float] = {}
    cash = initial_cash
    minimum_cash = cash
    oversells: list[dict[str, Any]] = []
    for event in events:
        symbol = str(event.get("symbolValue") or event.get("symbolPermtick") or event.get("symbol") or "")
        quantity = _number(event.get("fillQuantity")) or 0.0
        price = _number(event.get("fillPrice")) or 0.0
        fee = _number(event.get("orderFeeAmount")) or 0.0
        previous = positions.get(symbol, 0.0)
        current = previous + quantity
        positions[symbol] = current
        cash -= quantity * price + fee
        minimum_cash = min(minimum_cash, cash)
        if previous >= 0 and current < -1e-9:
            oversells.append(
                {
                    "orderId": event.get("orderId"),
                    "symbol": symbol,
                    "previousQuantity": previous,
                    "fillQuantity": quantity,
                    "resultingQuantity": current,
                }
            )
    return {
        "positions": positions,
        "negativePositions": {symbol: quantity for symbol, quantity in positions.items() if quantity < -1e-9},
        "oversells": oversells,
        "endingCash": cash,
        "minimumCash": minimum_cash,
        "fillCount": len(events),
    }


def _log_evidence(result_path: Path) -> dict[str, Any]:
    lines: list[str] = []
    for path in (result_path.parent / "log.txt", result_path.parent / "stdout.log", result_path.parent / f"{result_path.stem}-log.txt"):
        if not path.exists():
            continue
        try:
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
        except OSError:
            continue
    error_lines = [line.strip() for line in lines if "ERROR::" in line]
    completed_date = None
    for line in lines:
        match = re.search(r"Debug:\s+(\d{4}-\d{2}-\d{2}).*Algorithm Id:.*completed", line)
        if match:
            completed_date = match.group(1)
    return {
        "errorLines": error_lines[:20],
        "errorCount": len(error_lines),
        "completedDate": completed_date,
        "cashAccountConfigured": any("AShare execution account type: cash" in line for line in lines),
    }


def _last_equity_date(payload: dict[str, Any]) -> str | None:
    values = (((payload.get("charts") or {}).get("Strategy Equity") or {}).get("series") or {}).get("Equity", {}).get("values") or []
    if not values:
        return None
    try:
        return datetime.fromtimestamp(float(values[-1][0]), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, IndexError, OSError):
        return None


def audit_backtest_execution(
    result_path: Path,
    parameters: dict[str, Any],
    preflight_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": 1,
            "generatedAt": utc_now(),
            "passed": False,
            "severity": "critical",
            "gates": [_gate("result_payload_readable", False, error=str(exc))],
        }
    statistics = payload.get("statistics") or payload.get("Statistics") or {}
    state = payload.get("state") or payload.get("State") or {}
    end_equity = _number(statistics.get("End Equity"))
    drawdown = _number(statistics.get("Drawdown"))
    runtime_error = str(state.get("RuntimeError") or state.get("runtimeError") or "").strip()
    is_china_equity = (
        str(parameters.get("assetClass") or "equity").lower() == "equity"
        and str(parameters.get("market") or parameters.get("venue") or "").lower() == "china"
    )
    events = _filled_events(result_path, payload)
    ledger = _position_and_cash(events, float(parameters.get("initialCash") or parameters.get("cash") or 0))
    logs = _log_evidence(result_path)
    completed_date = logs.get("completedDate") or _last_equity_date(payload)
    data_validation = (preflight_validation or {}).get("data") or {}
    expected_end = ((data_validation.get("endCoverage") or {}).get("actualLastDate") or parameters.get("end"))
    completion_passed = bool(completed_date) and (not expected_end or str(completed_date) >= str(expected_end))
    result_analysis_complete = end_equity is not None and drawdown is not None
    gates = [
        _gate("lean_runtime_error", not runtime_error, runtimeError=runtime_error or None),
        _gate("lean_log_errors", logs["errorCount"] == 0, errorCount=logs["errorCount"], errorLines=logs["errorLines"]),
        _gate(
            "result_analysis_complete",
            result_analysis_complete,
            hasEndEquity=end_equity is not None,
            hasDrawdown=drawdown is not None,
        ),
        _gate("positive_end_equity", end_equity is not None and end_equity > 0, endEquity=end_equity),
        _gate("drawdown_not_over_100pct", drawdown is not None and drawdown <= 1.0, drawdown=drawdown),
        _gate(
            "backtest_reached_data_end",
            completion_passed,
            completedDate=completed_date,
            expectedDataEnd=expected_end,
        ),
    ]
    if is_china_equity:
        gates.extend(
            [
                _gate("ashare_no_short_positions", not ledger["negativePositions"], negativePositions=ledger["negativePositions"]),
                _gate("ashare_no_oversell", not ledger["oversells"], oversells=ledger["oversells"]),
                _gate(
                    "ashare_cash_account",
                    bool(logs["cashAccountConfigured"]),
                    configured=logs["cashAccountConfigured"],
                    reconstructedMinimumCash=ledger["minimumCash"],
                    reconstructedEndingCash=ledger["endingCash"],
                ),
            ]
        )
    passed = all(gate["passed"] for gate in gates)
    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "passed": passed,
        "severity": "ok" if passed else "critical",
        "gates": gates,
        "ledger": ledger,
        "completedDate": completed_date,
        "expectedDataEnd": expected_end,
    }


def merge_execution_validation(preflight: dict[str, Any] | None, execution: dict[str, Any]) -> dict[str, Any]:
    merged = dict(preflight or {})
    previous_execution = merged.pop("execution", None) or {}
    previous_gate_names = {gate.get("name") for gate in previous_execution.get("gates") or []}
    preflight_gates = [
        gate for gate in merged.get("gates") or [] if gate.get("name") not in previous_gate_names
    ]
    preflight_passed = (
        all(gate.get("passed") for gate in preflight_gates)
        if preflight_gates
        else bool(merged.get("passed", True))
    )
    merged["execution"] = execution
    merged["gates"] = [*preflight_gates, *(execution.get("gates") or [])]
    merged["passed"] = preflight_passed and bool(execution.get("passed"))
    merged["severity"] = "ok" if merged["passed"] else "critical"
    return merged


def execution_failure_message(execution: dict[str, Any]) -> str | None:
    failed = [gate["name"] for gate in execution.get("gates") or [] if not gate.get("passed")]
    return f"execution_validation_failed:{','.join(failed)}" if failed else None


def _host_result_path(path_value: Any, run_id: str) -> Path:
    original = Path(str(path_value or ""))
    candidates = [original]
    try:
        relative = original.relative_to("/workspace")
    except ValueError:
        pass
    else:
        candidates.append(PLATFORM_DIR / relative)
    candidates.append(PLATFORM_DIR / "web" / "runtime" / "runs" / run_id / "results" / f"{run_id}.json")
    return next((candidate for candidate in candidates if candidate.is_file()), original)


def revalidate_persisted_backtest(run_id: str) -> dict[str, Any]:
    run = get_backtest(run_id)
    if not run:
        raise KeyError(f"Backtest run not found: {run_id}")
    result_path = _host_result_path(run.get("result_json_path"), run_id)
    execution = audit_backtest_execution(result_path, run.get("parameters") or {}, run.get("validation") or {})
    validation = merge_execution_validation(run.get("validation") or {}, execution)
    failure = execution_failure_message(execution)
    status = "success" if execution.get("passed") else "failed"
    update_backtest(
        run_id,
        status=status,
        validation_json=validation,
        error=failure,
        error_message=failure,
    )
    experiment = dict(run.get("experiment") or {})
    experiment["validation"] = {
        "passed": validation.get("passed"),
        "severity": validation.get("severity"),
        "schemaVersion": validation.get("schemaVersion"),
    }
    with db() as connection:
        connection.execute(
            "update backtest_runs set experiment_json = ? where id = ?",
            (json_dump(experiment), run_id),
        )
        connection.execute(
            "update experiments set validation_json = ?, experiment_json = ?, updated_at = ? where run_id = ?",
            (json_dump(validation), json_dump(experiment), utc_now(), run_id),
        )
        if run.get("task_id"):
            connection.execute(
                "update tasks set status = ?, error = ?, finished_at = coalesce(finished_at, ?) where id = ?",
                (status, failure, utc_now(), run["task_id"]),
            )
    return get_backtest(run_id) or {}
