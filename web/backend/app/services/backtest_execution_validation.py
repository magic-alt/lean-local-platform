from __future__ import annotations

import json
import hashlib
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..db import db, json_dump, utc_now
from ..repositories.backtest_repository import get_backtest, update_backtest
from .run_paths import run_file


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


def _canonical_result_value(value: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        in_state = bool(path and path[-1].lower() == "state")
        in_closed_trades = any(part.lower() == "closedtrades" for part in path)
        in_algorithm_parameters = tuple(part.lower() for part in path[-2:]) == (
            "algorithmconfiguration",
            "parameters",
        )
        for key in sorted(value):
            normalized = key.lower()
            if in_state and normalized in {"starttime", "endtime", "hostname"}:
                continue
            if in_closed_trades and normalized == "id":
                continue
            if in_algorithm_parameters and normalized == "strategysnapshotdir":
                continue
            result[key] = _canonical_result_value(value[key], (*path, key))
        return result
    if isinstance(value, list):
        return [_canonical_result_value(item, path) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_result_sha256(payload: dict[str, Any]) -> str:
    canonical = _canonical_result_value(payload)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _event_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def _trend_order_contract(payload: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    orders_payload = payload.get("orders") or payload.get("Orders") or {}
    orders = list(orders_payload.values()) if isinstance(orders_payload, dict) else list(orders_payload) if isinstance(orders_payload, list) else []
    filled_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        order_id = str(event.get("orderId") or event.get("OrderId") or "")
        if order_id:
            filled_by_id[order_id] = event
    checked = 0
    next_open_violations: list[dict[str, Any]] = []
    t_plus_one_violations: list[dict[str, Any]] = []
    last_buy: dict[str, str] = {}
    chronological: list[tuple[str, str, float, str]] = []
    for order in orders:
        tag = str(order.get("tag") or order.get("Tag") or "")
        if not tag.startswith("ASHARE_TREND|"):
            continue
        try:
            metadata = json.loads(tag.split("|", 1)[1])
        except json.JSONDecodeError:
            next_open_violations.append({"orderId": order.get("id"), "reason": "invalid_tag"})
            continue
        order_id = str(order.get("id") or order.get("Id") or "")
        event = filled_by_id.get(order_id)
        if not event:
            continue
        fill_date = _event_date(
            event.get("utcTime") or event.get("time") or event.get("fillTime")
            or order.get("lastFillTime") or order.get("time")
        )
        signal_date = str(metadata.get("signalDate") or "")[:10]
        symbol = str(
            event.get("symbolValue")
            or ((order.get("symbol") or {}).get("value") if isinstance(order.get("symbol"), dict) else order.get("symbol"))
            or ""
        )
        quantity = _number(event.get("fillQuantity")) or 0.0
        checked += 1
        if not fill_date or not signal_date or fill_date <= signal_date:
            next_open_violations.append(
                {"orderId": order_id, "symbol": symbol, "signalDate": signal_date, "fillDate": fill_date}
            )
        if fill_date:
            chronological.append((fill_date, symbol, quantity, order_id))
    for fill_date, symbol, quantity, order_id in sorted(chronological):
        if quantity > 0:
            last_buy[symbol] = fill_date
        elif quantity < 0 and last_buy.get(symbol) == fill_date:
            t_plus_one_violations.append({"orderId": order_id, "symbol": symbol, "date": fill_date})
    return {
        "checkedOrders": checked,
        "nextOpenViolations": next_open_violations,
        "tPlusOneViolations": t_plus_one_violations,
    }


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
    actionable_error_lines: list[str] = []
    ignored_error_lines: list[str] = []
    for path in (result_path.parent / "log.txt", result_path.parent / "stdout.log", result_path.parent / f"{result_path.stem}-log.txt"):
        if not path.exists():
            continue
        try:
            file_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        lines.extend(file_lines)
        indexed_errors = [
            (index, line.strip())
            for index, line in enumerate(file_lines)
            if "ERROR::" in line
        ]
        shutdown_indexes = [
            index
            for index, line in enumerate(file_lines)
            if "PythonInitializer.Shutdown(): start" in line
        ]
        shutdown_index = shutdown_indexes[-1] if shutdown_indexes else None
        python_shutdown_timeout = bool(
            indexed_errors
            and shutdown_index is not None
            and all(
                index > shutdown_index
                and (
                    "Security.ExecuteWithTimeLimit(): Execution Security Error: Operation timed out"
                    in line
                    or "Program.Exit(): Failed to shutdown python" in line
                )
                for index, line in indexed_errors
            )
            and any(
                "Program.Exit(): Failed to shutdown python" in line
                for _, line in indexed_errors
            )
        )
        target = ignored_error_lines if python_shutdown_timeout else actionable_error_lines
        target.extend(line for _, line in indexed_errors)
    error_lines = list(dict.fromkeys(actionable_error_lines))
    ignored_error_lines = list(dict.fromkeys(ignored_error_lines))
    error_codes: list[str] = []
    for line in error_lines:
        if "Zero reference price" in line and "dividend" in line:
            error_codes.append("factor_file_zero_reference_price")
        elif "Subscription worker task exception" in line:
            error_codes.append("subscription_worker_exception")
        elif "Error running backtest analysis" in line:
            error_codes.append("lean_result_analysis_error")
        else:
            error_codes.append("lean_error")
    completed_date = None
    for line in lines:
        match = re.search(r"Debug:\s+(\d{4}-\d{2}-\d{2}).*Algorithm Id:.*completed", line)
        if match:
            completed_date = match.group(1)
    return {
        "errorLines": error_lines[:20],
        "errorCount": len(error_lines),
        "errorCodes": list(dict.fromkeys(error_codes)),
        "observedErrorCount": len(error_lines) + len(ignored_error_lines),
        "ignoredErrorLines": ignored_error_lines[:20],
        "ignoredErrorCodes": (
            ["lean_python_shutdown_timeout"] if ignored_error_lines else []
        ),
        "completedDate": completed_date,
        "cashAccountConfigured": any("AShare execution account type: cash" in line for line in lines),
        "trendNextOpenContract": any(
            "ASHARE_TREND_PULLBACK signal=close order=next_open" in line for line in lines
        ),
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
        raw_payload = result_path.read_bytes()
        payload = json.loads(raw_payload)
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
        _gate(
            "lean_log_errors",
            logs["errorCount"] == 0,
            errorCount=logs["errorCount"],
            errorCodes=logs["errorCodes"],
            errorLines=logs["errorLines"],
            observedErrorCount=logs["observedErrorCount"],
            ignoredErrorCodes=logs["ignoredErrorCodes"],
            ignoredErrorLines=logs["ignoredErrorLines"],
        ),
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
        if str(parameters.get("strategyTemplateKey") or "") == "ashare_trend_pullback_portfolio":
            contract = _trend_order_contract(payload, events)
            gates.extend(
                [
                    _gate(
                        "ashare_next_open_execution",
                        bool(logs.get("trendNextOpenContract")) and not contract["nextOpenViolations"],
                        declared=bool(logs.get("trendNextOpenContract")),
                        checkedOrders=contract["checkedOrders"],
                        violations=contract["nextOpenViolations"],
                    ),
                    _gate(
                        "ashare_t_plus_one",
                        not contract["tPlusOneViolations"],
                        checkedOrders=contract["checkedOrders"],
                        violations=contract["tPlusOneViolations"],
                    ),
                ]
            )
    passed = all(gate["passed"] for gate in gates)
    return {
        "schemaVersion": 2,
        "generatedAt": utc_now(),
        "passed": passed,
        "severity": "ok" if passed else "critical",
        "gates": gates,
        "ledger": ledger,
        "completedDate": completed_date,
        "expectedDataEnd": expected_end,
        "rawResultSha256": hashlib.sha256(raw_payload).hexdigest(),
        "canonicalResultSha256": canonical_result_sha256(payload),
        "tolerancePolicy": {
            "schemaVersion": 2,
            "numericComparison": "exact_after_json_parse",
            "excludedFields": [
                "state.StartTime",
                "state.EndTime",
                "state.Hostname",
                "algorithmConfiguration.parameters.strategySnapshotDir",
                "totalPerformance.closedTrades[].id",
            ],
        },
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
    return run_file(run_id, path_value, f"results/{run_id}.json")


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
