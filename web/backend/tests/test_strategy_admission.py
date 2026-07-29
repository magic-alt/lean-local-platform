from __future__ import annotations

from fastapi.testclient import TestClient


def _seed_runs(db_module, project_id: str = "strategy-1") -> tuple[list[str], dict[str, str]]:
    from app.db import json_dump, utc_now

    run_ids = ["run-bull", "run-bear", "run-range", "run-high-vol"]
    regimes = dict(zip(run_ids, ("bull", "bear", "range", "high-vol")))
    now = utc_now()
    summary = {
        "Net Profit": "15%",
        "Compounding Annual Return": "20%",
        "Drawdown": "10%",
        "Sharpe Ratio": "0.8",
        "Win Rate": "60%",
        "Profit-Loss Ratio": "1.5",
        "Expectancy": "0.4",
        "Total Trades": "10",
    }
    curves = {
        "run-bull": [100.0, 102.0, 105.0, 108.0],
        "run-bear": [100.0, 99.0, 101.0, 103.0],
        "run-range": [100.0, 101.0, 100.5, 102.0],
        "run-high-vol": [100.0, 104.0, 101.0, 106.0],
    }
    with db_module.db() as connection:
        connection.execute(
            """
            insert into projects
                (id, name, language, algorithm_class, project_path, main_file, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, "Admission Unit", "Python", "AdmissionAlgorithm", "/tmp/project", "main.py", json_dump({}), now, now),
        )
        for run_id in run_ids:
            connection.execute(
                """
                insert into backtest_runs
                    (id, project_id, symbol, asset_class, venue, resolution, data_type, parameters_json,
                     status, docker_image, results_dir, validation_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_id,
                    "SPY",
                    "equity",
                    "usa",
                    "daily",
                    "trade",
                    json_dump({"ticker": "SPY", "start": "2024-01-01", "end": "2024-12-31", "fast": 10}),
                    "success",
                    "lean:test",
                    f"/tmp/{run_id}",
                    json_dump({"passed": True, "severity": "ok", "gates": []}),
                    now,
                ),
            )
            connection.execute(
                """
                insert into experiments
                    (id, run_id, strategy_version_id, dataset_version_id, parameter_hash, fingerprint_json,
                     validation_json, experiment_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"experiment-{run_id}",
                    run_id,
                    "strategy-version-1",
                    f"dataset-{run_id}",
                    "full-run-parameter-hash",
                    json_dump({}),
                    json_dump({"passed": True}),
                    json_dump({}),
                    now,
                    now,
                ),
            )
            curve = [
                {"time": f"2024-01-0{index + 1}T00:00:00+00:00", "value": value}
                for index, value in enumerate(curves[run_id])
            ]
            connection.execute(
                """
                insert into backtest_results
                    (id, job_id, summary_metrics_json, equity_curve_json, drawdown_curve_json, orders_json,
                     trades_json, holdings_json, statistics_json, performance_json, raw_result_path, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"result-{run_id}",
                    run_id,
                    json_dump(summary),
                    json_dump(curve),
                    json_dump([]),
                    json_dump([]),
                    json_dump([]),
                    json_dump([]),
                    json_dump(summary),
                    json_dump({"strategy_return": 0.15, "sharpe_recomputed_from_equity": 0.8, "calmar": 2.0}),
                    f"/tmp/{run_id}/result.json",
                    now,
                ),
            )
    return run_ids, regimes


def test_admission_registers_baseline_and_promotes_passing_runs():
    from app import db as db_module
    from app.services.strategy_admission import evaluate_admission, register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)

    baseline = register_baseline(
        "strategy-1",
        run_ids=run_ids,
        regimes=regimes,
        parameters={"fast": 10},
    )
    assert baseline["current_stage"] == "baseline_registered"
    assert baseline["baselineSnapshot"]["aggregate"]["sharpe"] == 0.8

    admitted = evaluate_admission(
        "strategy-1",
        run_ids=run_ids,
        regimes=regimes,
        parameters={"fast": 10},
    )
    assert admitted["current_stage"] == "admission_passed"
    assert admitted["evaluation"]["status"] == "pass"
    assert all(gate["passed"] for gate in admitted["evaluation"]["gates"])
    assert [event["stage"] for event in admitted["events"]] == ["baseline_registered", "admission_passed"]


def test_admission_requires_all_market_regimes():
    from app import db as db_module
    from app.services.strategy_admission import register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    regimes.pop("run-high-vol")

    try:
        register_baseline("strategy-1", run_ids=run_ids[:-1], regimes=regimes, parameters={"fast": 10})
    except ValueError as exc:
        assert "Missing required regimes" in str(exc)
    else:
        raise AssertionError("Expected an incomplete regime set to be rejected.")


def test_source_replica_template_is_ineligible_for_admission():
    from app import db as db_module
    from app.db import json_dump
    from app.services.strategy_admission import register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    with db_module.db() as connection:
        connection.execute(
            "update projects set config_json = ? where id = ?",
            (
                json_dump({"templateKey": "gap_buy_source_replica"}),
                "strategy-1",
            ),
        )

    try:
        register_baseline(
            "strategy-1",
            run_ids=run_ids,
            regimes=regimes,
            parameters={"fast": 10},
        )
    except ValueError as exc:
        assert "research-only" in str(exc)
        assert "cannot enter strategy admission" in str(exc)
    else:
        raise AssertionError("Expected SOURCE_REPLICA admission to be rejected.")


def test_persisted_source_replica_contract_cannot_be_hidden_by_project_reconfiguration():
    from app import db as db_module
    from app.db import json_dump
    from app.services.strategy_admission import register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    with db_module.db() as connection:
        for run_id in run_ids:
            connection.execute(
                "update backtest_runs set parameters_json = ? where id = ?",
                (
                    json_dump(
                        {
                            "ticker": "SPY",
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "fast": 10,
                            "strategyTemplateKey": "gap_buy_source_replica",
                            "strategyMode": "SOURCE_REPLICA",
                            "researchOnly": True,
                            "tradable": False,
                            "admissionEligible": False,
                        }
                    ),
                    run_id,
                ),
            )
        connection.execute(
            "update projects set config_json = ? where id = ?",
            (
                json_dump({"templateKey": "gap_buy_ashare_next_open"}),
                "strategy-1",
            ),
        )

    try:
        register_baseline(
            "strategy-1",
            run_ids=run_ids,
            regimes=regimes,
            parameters={"fast": 10},
        )
    except ValueError as exc:
        assert "SOURCE_REPLICA" in str(exc)
        assert "cannot enter strategy admission" in str(exc)
    else:
        raise AssertionError("Expected the immutable SOURCE_REPLICA run contract to win.")


def test_executable_gap_template_requires_intraday_execution_evidence():
    from app import db as db_module
    from app.db import json_dump
    from app.services.strategy_admission import register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    with db_module.db() as connection:
        connection.execute(
            "update projects set config_json = ? where id = ?",
            (
                json_dump({"templateKey": "gap_buy_ashare_next_open"}),
                "strategy-1",
            ),
        )

    try:
        register_baseline(
            "strategy-1",
            run_ids=run_ids,
            regimes=regimes,
            parameters={"fast": 10},
        )
    except ValueError as exc:
        assert "missing required admission execution gates" in str(exc)
        assert "ashare_no_same_bar_signal_fill" in str(exc)
    else:
        raise AssertionError("Expected missing executable gap evidence to block admission.")


def test_admitted_runs_can_be_used_by_portfolio_optimizer():
    from datetime import date, timedelta

    from app import db as db_module
    from app.db import json_dump
    from app.services.portfolio_optimization import optimize_portfolio
    from app.services.strategy_admission import evaluate_admission, register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    register_baseline("strategy-1", run_ids=run_ids, regimes=regimes, parameters={"fast": 10})
    evaluate_admission("strategy-1", run_ids=run_ids, regimes=regimes, parameters={"fast": 10})
    start = date(2024, 1, 1)
    with db_module.db() as connection:
        for offset, run_id in enumerate(run_ids[:2]):
            curve = [
                {
                    "time": (start + timedelta(days=index)).isoformat(),
                    "value": 100 + index * (1 + offset * 0.1),
                }
                for index in range(65)
            ]
            connection.execute(
                "update backtest_results set equity_curve_json=? where job_id=?",
                (json_dump(curve), run_id),
            )

    result = optimize_portfolio(run_ids[:2], step=0.2, max_weight=0.8)

    assert sum(result["weights"].values()) == 1.0
    assert set(result["weights"]) == set(run_ids[:2])
    assert result["alignedPoints"] == 65
    assert result["candidateCount"] > 0


def test_backtest_admission_endpoint_returns_parameter_fingerprint():
    from app import db as db_module
    from app.main import app
    from app.services.strategy_admission import register_baseline

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    baseline = register_baseline("strategy-1", run_ids=run_ids, regimes=regimes, parameters={"fast": 10})

    response = TestClient(app).get(f"/api/backtests/{run_ids[0]}/admission")

    assert response.status_code == 200
    assert response.json()["parametersSha256"] == baseline["parameters_sha256"]
    assert response.json()["registrationStatus"] == "registered"
    assert response.json()["admission"]["current_stage"] == "baseline_registered"


def test_admission_parameter_fingerprint_ignores_run_specific_snapshot_metadata():
    from app.services.strategy_admission import parameters_sha256

    first = {
        "ticker": "600460",
        "start": "2024-01-01",
        "end": "2026-07-13",
        "cash": 50000,
        "initial_cash": 50000,
        "fast": 10,
        "slow": 120,
        "feeModel": "default",
        "slippageModel": "default",
        "strategySnapshotDir": "/runtime/runs/run-1/strategy",
        "strategySnapshotMainFile": "main.py",
        "datasetVersion": "batch-1",
    }
    second = {
        **first,
        "ticker": "000300",
        "start": "2023-01-01",
        "end": "2024-01-01",
        "cash": 100000,
        "initial_cash": 100000,
        "strategySnapshotDir": "/runtime/runs/run-2/strategy",
        "datasetVersion": "batch-2",
    }
    second.pop("feeModel")
    second.pop("slippageModel")

    assert parameters_sha256(first) == parameters_sha256(second)


def test_backtest_admission_endpoint_distinguishes_unregistered_parameters():
    from app import db as db_module
    from app.main import app

    db_module.init_db()
    run_ids, _ = _seed_runs(db_module)

    response = TestClient(app).get(f"/api/backtests/{run_ids[0]}/admission")

    assert response.status_code == 200
    assert response.json()["registrationStatus"] == "not_registered"
    assert response.json()["admission"] is None


def test_stopped_clean_paper_session_promotes_admission():
    from app import db as db_module
    from app.db import json_dump, utc_now
    from app.services.strategy_admission import evaluate_admission, register_baseline, validate_paper_stage

    db_module.init_db()
    run_ids, regimes = _seed_runs(db_module)
    register_baseline("strategy-1", run_ids=run_ids, regimes=regimes, parameters={"fast": 10})
    evaluate_admission("strategy-1", run_ids=run_ids, regimes=regimes, parameters={"fast": 10})
    now = utc_now()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id, project_id, name, status, symbol, asset_class, venue, resolution, cash, equity,
                 parameters_json, created_at, updated_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("paper-1", "strategy-1", "Paper Unit", "stopped", "SPY", "equity", "usa", "daily", 100000, 101000,
             json_dump({"fast": 10}), now, now, now),
        )
        for index in range(2):
            connection.execute(
                """
                insert into paper_daily_reports
                    (id, session_id, trade_date, report_json, signals_json, orders_json, trades_json,
                     rejects_json, positions_json, snapshot_json, benchmark_json, qa_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"paper-report-{index}", "paper-1", f"2024-01-0{index + 2}", json_dump({}), json_dump([]),
                 json_dump([]), json_dump([]), json_dump([]), json_dump([]), json_dump({}), json_dump({}),
                 json_dump({"passed": True, "severity": "ok"}), now),
            )

    admission = validate_paper_stage(
        "strategy-1", session_id="paper-1", parameters={"fast": 10}, min_report_days=2
    )

    assert admission["current_stage"] == "paper_validated"
    assert admission["events"][-1]["source_id"] == "paper-1"
    assert admission["events"][-1]["payload"]["reportDays"] == 2
