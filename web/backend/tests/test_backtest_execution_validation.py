import json
from pathlib import Path


def _write_result(
    tmp_path: Path,
    *,
    statistics: dict[str, str],
    events: list[dict],
    log_lines: list[str],
    state: dict | None = None,
) -> Path:
    result_path = tmp_path / "run.json"
    result_path.write_text(
        json.dumps({"statistics": statistics, "state": state or {}}),
        encoding="utf-8",
    )
    (tmp_path / "run-order-events.json").write_text(json.dumps(events), encoding="utf-8")
    (tmp_path / "run-log.txt").write_text("\n".join(log_lines), encoding="utf-8")
    return result_path


def _parameters() -> dict:
    return {
        "ticker": "600460",
        "assetClass": "equity",
        "market": "china",
        "start": "2024-01-01",
        "end": "2026-07-13",
        "cash": 800000,
        "initialCash": 800000,
    }


def test_execution_audit_rejects_negative_equity_short_oversell_and_lean_errors(tmp_path):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result_path = _write_result(
        tmp_path,
        statistics={"End Equity": "-30942.62", "Drawdown": "102.900%"},
        events=[
            {
                "orderId": 1,
                "symbolValue": "600460",
                "fillQuantity": 30100,
                "fillPrice": 25,
                "orderFeeAmount": 10,
                "status": "filled",
            },
            {
                "orderId": 2,
                "symbolValue": "600460",
                "fillQuantity": -30100,
                "fillPrice": 26,
                "orderFeeAmount": 10,
                "status": "filled",
            },
            {
                "orderId": 3,
                "symbolValue": "600460",
                "fillQuantity": -30100,
                "fillPrice": 27,
                "orderFeeAmount": 10,
                "status": "filled",
            },
        ],
        log_lines=[
            "ERROR:: AlgorithmManager.Run(): Portfolio value is less than or equal to zero, stopping algorithm.",
            "Debug: 2026-06-29 03:00:00 Algorithm Id:(run) completed in 1 seconds.",
        ],
    )

    audit = audit_backtest_execution(result_path, _parameters())
    failed = {gate["name"] for gate in audit["gates"] if not gate["passed"]}

    assert audit["passed"] is False
    assert {
        "lean_log_errors",
        "positive_end_equity",
        "drawdown_not_over_100pct",
        "backtest_reached_data_end",
        "ashare_no_short_positions",
        "ashare_no_oversell",
    } <= failed
    assert audit["ledger"]["negativePositions"] == {"600460": -30100.0}
    log_gate = next(gate for gate in audit["gates"] if gate["name"] == "lean_log_errors")
    assert log_gate["details"]["errorCodes"] == ["lean_error"]


def test_execution_audit_accepts_completed_cash_only_ashare_run(tmp_path):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result_path = _write_result(
        tmp_path,
        statistics={"End Equity": "801000", "Drawdown": "2.5%"},
        events=[
            {
                "orderId": 1,
                "symbolValue": "600460",
                "fillQuantity": 100,
                "fillPrice": 25,
                "orderFeeAmount": 5,
                "status": "filled",
            },
            {
                "orderId": 2,
                "symbolValue": "600460",
                "fillQuantity": -100,
                "fillPrice": 35,
                "orderFeeAmount": 5,
                "status": "filled",
            },
        ],
        log_lines=[
            "Debug: AShare execution account type: cash; short selling disabled.",
            "Debug: 2026-07-13 03:00:00 Algorithm Id:(run) completed in 1 seconds.",
        ],
    )

    audit = audit_backtest_execution(result_path, _parameters())

    assert audit["passed"] is True
    assert all(gate["passed"] for gate in audit["gates"])
    assert audit["ledger"]["positions"] == {"600460": 0.0}
    assert audit["ledger"]["minimumCash"] >= 0


def test_execution_audit_retains_but_ignores_post_completion_python_shutdown_timeout(
    tmp_path,
):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result_path = _write_result(
        tmp_path,
        statistics={"End Equity": "801000", "Drawdown": "2.5%"},
        events=[],
        state={"Status": "Completed", "RuntimeError": ""},
        log_lines=[
            "Debug: AShare execution account type: cash; short selling disabled.",
            "Debug: 2026-07-13 03:00:00 Algorithm Id:(run) completed in 1 seconds.",
            "TRACE:: PythonInitializer.Shutdown(): start",
            "ERROR:: Security.ExecuteWithTimeLimit(): Execution Security Error: Operation timed out - 0.166 minutes max.",
            "ERROR:: Program.Exit(): Failed to shutdown python System.TimeoutException: Execution Security Error.",
        ],
    )

    audit = audit_backtest_execution(result_path, _parameters())
    gate = next(item for item in audit["gates"] if item["name"] == "lean_log_errors")

    assert audit["passed"] is True
    assert gate["passed"] is True
    assert gate["details"]["errorCount"] == 0
    assert gate["details"]["observedErrorCount"] == 2
    assert gate["details"]["ignoredErrorCodes"] == ["lean_python_shutdown_timeout"]


def test_execution_audit_does_not_ignore_algorithm_timeout_before_shutdown(tmp_path):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result_path = _write_result(
        tmp_path,
        statistics={"End Equity": "801000", "Drawdown": "2.5%"},
        events=[],
        log_lines=[
            "Debug: AShare execution account type: cash; short selling disabled.",
            "ERROR:: Security.ExecuteWithTimeLimit(): Execution Security Error: Operation timed out.",
            "Debug: 2026-07-13 03:00:00 Algorithm Id:(run) completed in 1 seconds.",
            "TRACE:: PythonInitializer.Shutdown(): start",
            "ERROR:: Program.Exit(): Failed to shutdown python System.TimeoutException.",
        ],
    )

    audit = audit_backtest_execution(result_path, _parameters())
    gate = next(item for item in audit["gates"] if item["name"] == "lean_log_errors")

    assert audit["passed"] is False
    assert gate["passed"] is False
    assert gate["details"]["errorCount"] == 2
    assert gate["details"]["ignoredErrorCodes"] == []


def test_canonical_result_digest_excludes_run_local_snapshot_directory():
    from app.services.backtest_execution_validation import canonical_result_sha256

    payload = {
        "algorithmConfiguration": {
            "parameters": {
                "strategySnapshotDir": "/workspace/web/runtime/runs/run-a/strategy",
                "strategySnapshotMainFile": "main.py",
                "fastPeriod": "20",
            }
        },
        "statistics": {"End Equity": "100000"},
    }

    same_inputs_new_run = json.loads(json.dumps(payload))
    same_inputs_new_run["algorithmConfiguration"]["parameters"]["strategySnapshotDir"] = (
        "/workspace/web/runtime/runs/run-b/strategy"
    )
    changed_parameter = json.loads(json.dumps(payload))
    changed_parameter["algorithmConfiguration"]["parameters"]["fastPeriod"] = "30"

    assert canonical_result_sha256(payload) == canonical_result_sha256(same_inputs_new_run)
    assert canonical_result_sha256(payload) != canonical_result_sha256(changed_parameter)


def test_execution_validation_merge_replaces_previous_execution_gates():
    from app.services.backtest_execution_validation import merge_execution_validation

    preflight = {
        "passed": False,
        "gates": [
            {"name": "data", "passed": True},
            {"name": "old_execution", "passed": False},
        ],
        "execution": {
            "passed": False,
            "gates": [{"name": "old_execution", "passed": False}],
        },
    }
    execution = {
        "passed": True,
        "gates": [{"name": "new_execution", "passed": True}],
    }

    merged = merge_execution_validation(preflight, execution)

    assert merged["passed"] is True
    assert [gate["name"] for gate in merged["gates"]] == ["data", "new_execution"]


def test_execution_audit_classifies_factor_file_and_analysis_errors(tmp_path):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result_path = _write_result(
        tmp_path,
        statistics={"End Equity": "50000", "Drawdown": "0%"},
        events=[],
        log_lines=[
            "ERROR:: Subscription worker task exception. Zero reference price for 600460 dividend at 6/25/2024",
            "ERROR:: BacktestingResultHandler.SendFinalResult(): Error running backtest analysis",
            "Debug: AShare execution account type: cash; short selling disabled.",
            "Debug: 2026-07-13 03:00:00 Algorithm Id:(run) completed in 1 seconds.",
        ],
    )

    audit = audit_backtest_execution(result_path, _parameters())
    gate = next(item for item in audit["gates"] if item["name"] == "lean_log_errors")

    assert gate["passed"] is False
    assert gate["details"]["errorCodes"] == [
        "factor_file_zero_reference_price",
        "lean_result_analysis_error",
    ]
