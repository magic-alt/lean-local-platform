from fastapi.testclient import TestClient


def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    return db_module


def test_provider_availability_reports_missing_env_without_network(monkeypatch):
    from app.services.data import provider_availability

    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)

    result = provider_availability("alpha_vantage")

    assert result["networkChecked"] is False
    assert result["count"] == 1
    assert result["items"][0]["available"] is False
    assert "credential_missing" in result["items"][0]["reason"]


def test_provider_manager_exposes_dsa_style_sources_and_jqdata_window_fallback():
    from app.services.data_provider_manager import DATA_PROVIDER_MANAGER

    providers = {item["key"] for item in DATA_PROVIDER_MANAGER.providers()}
    assert {"efinance", "tencent", "pytdx", "yfinance", "tickflow", "longbridge", "finnhub"} <= providers

    chain = DATA_PROVIDER_MANAGER.chain(
        "jqdata",
        market="china",
        asset_class="equity",
        start_date="2026-06-01",
        end_date="2026-06-30",
    )
    assert chain[0] == "tushare"
    assert "jqdata" not in chain


def test_stored_objects_api_supports_namespace_pagination(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.db_object_store import put_bytes

    put_bytes("unit", "a.json", b"a")
    put_bytes("unit", "b.json", b"b")
    put_bytes("unit", "c.json", b"c")
    put_bytes("other", "d.json", b"d")

    response = TestClient(app).get("/api/object-store/_stored-objects", params={"namespace": "unit", "limit": 2, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert len(payload["items"]) == 2
    assert {item["namespace"] for item in payload["items"]} == {"unit"}


def test_reports_api_supports_paged_backtest_and_report_rows(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.db import json_dump
    from app.main import app

    with db_module.db() as connection:
        connection.execute(
            "insert into reports (id, run_id, status, created_at) values (?, ?, ?, ?)",
            ("report-1", "run-a", "success", "2026-07-05T00:00:00+00:00"),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id, symbol, asset_class, venue, resolution, data_type, parameters_json, status,
                 docker_image, results_dir, result_json_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-b",
                "600519",
                "equity",
                "china",
                "daily",
                "trade",
                json_dump({}),
                "completed",
                "lean:test",
                str(tmp_path / "run-b"),
                str(tmp_path / "run-b" / "result.json"),
                "2026-07-05T00:01:00+00:00",
            ),
        )

    response = TestClient(app).get("/api/reports", params={"paged": True, "limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1


def test_generic_optimization_grid_expands_candidates():
    from app.services.optimization import best_candidate, normalize_parameter_grid, parameter_combinations

    grid = normalize_parameter_grid({"period": "10,20", "threshold": [0.1, 0.2]}, max_candidates=10)
    candidates = parameter_combinations({"ticker": "SPY", "cash": 100000}, grid)

    assert grid == {"period": [10, 20], "threshold": [0.1, 0.2]}
    assert len(candidates) == 4
    assert candidates[0]["period"] == 10
    assert candidates[-1]["threshold"] == 0.2
    assert best_candidate(
        [
            {"status": "success", "statistics": {"Sharpe Ratio": "0.50"}},
            {"status": "success", "statistics": {"Sharpe Ratio": "1.25"}},
        ]
    )["statistics"]["Sharpe Ratio"] == "1.25"


def test_compare_api_and_report_exports_use_parsed_backtest_results(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.db import json_dump
    from app.main import app

    with db_module.db() as connection:
        for index, run_id in enumerate(("run-a", "run-b"), start=1):
            connection.execute(
                """
                insert into backtest_runs
                    (id, symbol, asset_class, venue, resolution, data_type, parameters_json, status,
                     docker_image, results_dir, result_json_path, statistics_json, validation_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "SPY",
                    "equity",
                    "usa",
                    "daily",
                    "trade",
                    json_dump({"start": "2020-01-01", "end": "2020-12-31"}),
                    "success",
                    "lean:test",
                    str(tmp_path / run_id),
                    str(tmp_path / run_id / "result.json"),
                    json_dump(
                        {
                            "Sharpe Ratio": str(index),
                            "Recomputed Sharpe": 3 - index,
                            "Compounding Annual Return": f"{index * 10}%",
                        }
                    ),
                    json_dump({"passed": True, "severity": "ok", "gates": []}),
                    f"2026-07-05T00:0{index}:00+00:00",
                ),
            )
            connection.execute(
                """
                insert into backtest_results
                    (id, job_id, summary_metrics_json, equity_curve_json, drawdown_curve_json,
                     orders_json, trades_json, holdings_json, statistics_json, performance_json,
                     raw_result_path, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"result-{run_id}",
                    run_id,
                    json_dump({"Sharpe Ratio": str(index), "Compounding Annual Return": f"{index * 10}%"}),
                    json_dump([{"time": "2020-01-01T00:00:00+00:00", "value": 100}, {"time": "2020-12-31T00:00:00+00:00", "value": 100 + index}]),
                    json_dump([{"time": "2020-12-31T00:00:00+00:00", "value": -0.01 * index}]),
                    json_dump([]),
                    json_dump([]),
                    json_dump([]),
                    json_dump({"Sharpe Ratio": str(index)}),
                    json_dump(
                        {
                            "strategy_return": 0.01 * index,
                            "calmar": index,
                            "sharpe_recomputed_from_equity": 3 - index,
                            "sharpe_recomputed_sample_count": 80,
                            "short_window_unstable": False,
                            "sharpe_recompute_status": "computed_from_equity_curve",
                        }
                    ),
                    str(tmp_path / run_id / "result.json"),
                    f"2026-07-05T00:1{index}:00+00:00",
                ),
            )

    client = TestClient(app)
    compare = client.post("/api/compare/backtests", json={"runIds": ["run-a", "run-b"]})
    assert compare.status_code == 200
    payload = compare.json()
    assert payload["rankings"]["bySharpe"][0] == "run-a"
    assert payload["items"][0]["metrics"]["sharpeRatio"] == 2
    assert payload["items"][0]["metrics"]["leanSharpeRatio"] == 1
    assert payload["items"][0]["metrics"]["shortWindowUnstable"] is False
    assert payload["items"][0]["equityCurve"]

    markdown = client.get("/api/reports/backtest:run-a/export", params={"format": "markdown"})
    assert markdown.status_code == 200
    assert "Backtest Report" in markdown.text
    csv_response = client.get("/api/reports/backtest:run-a/export", params={"format": "csv"})
    assert csv_response.status_code == 200
    assert "metrics,Sharpe Ratio,1" in csv_response.text
    json_response = client.get("/api/reports/backtest:run-a/export", params={"format": "json"})
    assert json_response.status_code == 200
    assert json_response.json()["runId"] == "run-a"
    pdf_response = client.get("/api/reports/backtest:run-a/export", params={"format": "pdf"})
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF-1.4")


def test_optimization_worker_persists_child_backtest_runs(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    import json
    import app.services.projects as projects_module
    import app.services.tasks as tasks_module
    import app.tasks.worker as worker_module
    from app.db import json_dump
    from app.services.projects import create_project
    from app.services.tasks import create_task

    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(tasks_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(worker_module, "RUNS_DIR", tmp_path / "runs")

    class DummyLeanRunner:
        def __init__(self, timeout_seconds):
            self.timeout_seconds = timeout_seconds

        def run_backtest(self, run_id, parameters, run_dir, output_callback, **kwargs):
            results_dir = run_dir / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "config.json").write_text(json.dumps({"parameters": parameters}), encoding="utf-8")
            result_json = results_dir / f"{run_id}.json"
            result_json.write_text(
                json.dumps(
                    {
                        "statistics": {"Sharpe Ratio": str(parameters["fast"])},
                        "charts": {
                            "Strategy Equity": {
                                "series": {
                                    "Equity": {"values": [[0, 100000], [86400, 101000]]},
                                    "Return": {"values": [[0, 0], [86400, 0.01]]},
                                }
                            },
                            "Drawdown": {"series": {"Equity Drawdown": {"values": [[0, 0], [86400, -0.01]]}}},
                        },
                    }
                ),
                encoding="utf-8",
            )
            report_html = results_dir / "report.html"
            report_html.write_text("<html></html>", encoding="utf-8")
            return {
                "exit_code": 0,
                "timed_out": False,
                "container_name": f"lean-{run_id}"[:60],
                "work_dir": str(run_dir),
                "results_dir": str(results_dir),
                "result_json_path": str(result_json),
                "summary_json_path": None,
                "report_html_path": str(report_html),
                "artifact_manifest_path": str(results_dir / "artifact-manifest.json"),
                "statistics": {"Sharpe Ratio": str(parameters["fast"])},
                "error": None,
            }

    monkeypatch.setattr(worker_module, "LeanRunner", DummyLeanRunner)
    project = create_project("Optimization Unit", template_key="ema_cross")
    parameters = {
        "ticker": "SPY",
        "assetClass": "equity",
        "market": "usa",
        "venue": "usa",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2020-01-01",
        "end": "2020-12-31",
        "cash": 100000,
        "dockerImage": "lean:test",
        "parameterGrid": {"fast": [5, 10]},
        "parameterSchema": [],
    }
    task = create_task("optimization", "Optimize SPY", parameters, project["id"], "opt-1")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into optimization_runs
                (id, task_id, project_id, status, parameters_json, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            ("opt-1", task["id"], project["id"], "queued", json_dump(parameters), str(tmp_path / "runs" / "optimization-opt-1"), "2026-07-07T00:00:00+00:00"),
        )

    worker_module.optimize_task.run(task["id"], "opt-1")

    with db_module.db() as connection:
        child_runs = connection.execute("select * from backtest_runs where task_id = ? order by created_at", (task["id"],)).fetchall()
        result_count = connection.execute("select count(*) as count from backtest_results").fetchone()["count"]
        optimization = connection.execute("select * from optimization_runs where id = ?", ("opt-1",)).fetchone()
    assert len(child_runs) == 2
    assert {row["status"] for row in child_runs} == {"success"}
    assert result_count == 2
    assert json.loads(optimization["result_json"])["candidateCount"] == 2


def test_data_assets_are_retained_and_marked_superseded(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.data import record_data_asset

    first = record_data_asset(
        {
            "symbol": "600519",
            "source": "akshare",
            "rows": 1,
            "first_date": "2026-07-03",
            "last_date": "2026-07-03",
            "lean_file": "equity/china/daily/600519.zip",
            "asset_class": "equity",
            "venue": "china",
            "resolution": "daily",
            "data_type": "trade",
        }
    )
    second = record_data_asset(
        {
            "symbol": "600519",
            "source": "akshare",
            "rows": 5000,
            "first_date": "2005-01-04",
            "last_date": "2026-07-03",
            "lean_file": "equity/china/daily/600519.zip",
            "asset_class": "equity",
            "venue": "china",
            "resolution": "daily",
            "data_type": "trade",
        }
    )

    client = TestClient(app)
    all_assets = client.get("/api/data-assets", params={"paged": True}).json()
    active_assets = client.get("/api/data-assets", params={"includeSuperseded": False, "paged": True}).json()

    assert all_assets["count"] == 2
    old = next(item for item in all_assets["items"] if item["id"] == first["id"])
    new = next(item for item in all_assets["items"] if item["id"] == second["id"])
    assert old["status"] == "superseded"
    assert old["superseded_by"] == second["id"]
    assert new["status"] == "active"
    assert active_assets["count"] == 1
    assert active_assets["items"][0]["id"] == second["id"]
