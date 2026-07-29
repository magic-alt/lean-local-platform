from __future__ import annotations

from datetime import date, timedelta

import pytest


def test_openapi_exposes_only_unified_optimization_paths():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/optimizations" in paths
    assert "/api/optimizations/preview" in paths
    assert "/api/portfolio-optimizations" in paths
    assert "/api/optimize" not in paths
    assert "/api/portfolios/optimize" not in paths


def test_optimization_summary_ranks_the_configured_single_objective():
    from app.services.experiment_batches import _summary

    items = [
        {
            "id": "return-winner",
            "project_id": "project",
            "symbol": "SPY",
            "status": "success",
            "parameters": {
                "parameters": {
                    "optimizationCandidateKey": "fast=5",
                    "optimizationOverrides": {"fast": 5},
                }
            },
            "result": {
                "statistics": {
                    "Sharpe Ratio": "0.5",
                    "Total Return": "25%",
                    "Drawdown": "20%",
                }
            },
        },
        {
            "id": "sharpe-winner",
            "project_id": "project",
            "symbol": "SPY",
            "status": "success",
            "parameters": {
                "parameters": {
                    "optimizationCandidateKey": "fast=10",
                    "optimizationOverrides": {"fast": 10},
                }
            },
            "result": {
                "statistics": {
                    "Sharpe Ratio": "2.0",
                    "Total Return": "10%",
                    "Drawdown": "5%",
                }
            },
        },
    ]

    by_return = _summary(items, objective="return")
    by_drawdown = _summary(items, objective="drawdown")

    assert by_return["rankingMetric"] == "return"
    assert by_return["ranking"][0]["itemId"] == "return-winner"
    assert by_drawdown["ranking"][0]["itemId"] == "sharpe-winner"


def _seed_backtest(db_module, run_id: str, project_id: str, market: str) -> None:
    from app.db import json_dump
    from app.repositories.backtest_repository import save_result
    from app.services.strategy_admission import parameters_sha256

    parameters = {"market": market, "resolution": "daily", "ticker": run_id}
    created_at = "2026-01-01T00:00:00+00:00"
    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id,project_id,name,symbol,asset_class,venue,resolution,data_type,
                 parameters_json,status,docker_image,results_dir,created_at,finished_at)
            values (?,?,?,?,?,?,?,?,?,'success','lean:test',?,?,?)
            """,
            (
                run_id,
                project_id,
                run_id,
                run_id,
                "equity",
                market,
                "daily",
                "trade",
                json_dump(parameters),
                f"/tmp/{run_id}/results",
                created_at,
                created_at,
            ),
        )
        connection.execute(
            """
            insert into strategy_admissions
                (id,strategy_id,parameters_sha256,profile_name,profile_version,
                 sample_set,current_stage,baseline_snapshot_json,evaluation_json,
                 created_at,updated_at)
            values (?,?,?,?,?,?,'admission_passed','{}','{}',?,?)
            """,
            (
                f"admission-{run_id}",
                project_id,
                parameters_sha256(parameters),
                "institutional",
                "1",
                "default",
                created_at,
                created_at,
            ),
        )
    start = date(2025, 1, 1)
    curve = [
        {"time": (start + timedelta(days=index)).isoformat(), "value": 100 + index}
        for index in range(65)
    ]
    save_result(run_id, {"equity_curve": curve}, created_at)


def test_portfolio_runs_are_persisted_and_mixed_currency_is_blocked():
    import app.db as db_module
    from app.services import portfolio_optimization

    db_module.init_db()
    _seed_backtest(db_module, "run-cny-1", "project-1", "china")
    _seed_backtest(db_module, "run-cny-2", "project-2", "china")
    _seed_backtest(db_module, "run-usd", "project-3", "usa")

    with pytest.raises(ValueError, match="Mixed account currencies"):
        portfolio_optimization.preview_portfolio(["run-cny-1", "run-usd"])

    created = portfolio_optimization.create_run(
        name="CNY portfolio",
        run_ids=["run-cny-1", "run-cny-2"],
        objective="sharpe",
        step=0.5,
        max_weight=1,
        allow_short=False,
    )
    assert created["status"] == "success"
    assert created["base_currency"] == "CNY"
    assert created["result"]["alignedPoints"] == 65
    with db_module.db() as connection:
        edge_count = connection.execute(
            """
            select count(*) as count from workflow_lineage_edges
            where child_type='portfolio_optimization' and child_id=?
            """,
            (created["id"],),
        ).fetchone()["count"]
    assert edge_count == 2
