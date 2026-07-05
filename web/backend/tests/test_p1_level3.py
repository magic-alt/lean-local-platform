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


def test_china_strategy_template_hard_fails_without_real_benchmark():
    from app.services.strategies import render_python_template

    code = render_python_template("UnitAlgorithm", "ema_cross")

    assert "constant benchmark fallback is disabled" in code
    assert "backtest is blocked" in code
    assert "set_benchmark(lambda time: 1)" not in code


def test_reports_api_exposes_backtest_result_and_stored_objects(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.db import json_dump, utc_now
    from app.main import app
    from app.services.db_object_store import put_bytes

    report_path = tmp_path / "reports" / "run-1.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("<html>report</html>", encoding="utf-8")
    raw_object = put_bytes(
        "backtest-results",
        "run-1/result.json",
        b'{"ok":true}',
        content_type="application/json",
        metadata={"job_id": "run-1", "kind": "lean-result"},
    )
    summary_object = put_bytes(
        "backtest-results",
        "run-1/summary.json",
        b'{"Net Profit":"1%"}',
        content_type="application/json",
        metadata={"job_id": "run-1", "kind": "lean-summary"},
    )
    now = utc_now()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, symbol, asset_class, venue, resolution, data_type, parameters_json, status,
                 docker_image, results_dir, result_json_path, summary_json_path, report_html_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-1",
                "600519",
                "equity",
                "china",
                "daily",
                "trade",
                json_dump({"benchmarkSymbol": "000300"}),
                "completed",
                "lean:test",
                str(tmp_path / "runs" / "run-1"),
                str(tmp_path / "runs" / "run-1" / "result.json"),
                str(tmp_path / "runs" / "run-1" / "summary.json"),
                str(report_path),
                now,
            ),
        )
        connection.execute(
            """
            insert into backtest_results
                (id, job_id, summary_metrics_json, equity_curve_json, drawdown_curve_json, orders_json,
                 trades_json, holdings_json, statistics_json, performance_json, raw_result_path,
                 raw_result_object_id, summary_object_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "result-1",
                "run-1",
                json_dump({"Alpha": "0.1", "Beta": "0.9"}),
                json_dump([]),
                json_dump([]),
                json_dump([]),
                json_dump([]),
                json_dump([]),
                json_dump({"Alpha": "0.1", "Beta": "0.9"}),
                json_dump({"excess_return": 0.01}),
                str(tmp_path / "runs" / "run-1" / "result.json"),
                raw_object["id"],
                summary_object["id"],
                now,
            ),
        )

    client = TestClient(app)
    reports = client.get("/api/reports")
    assert reports.status_code == 200
    payload = reports.json()
    item = next(report for report in payload if report["id"] == "backtest:run-1")
    assert item["source"] == "backtest_run"
    assert item["result"]["summary_metrics"]["Alpha"] == "0.1"
    assert {stored["id"] for stored in item["storedObjects"]} == {raw_object["id"], summary_object["id"]}

    detail = client.get("/api/reports/run-1")
    assert detail.status_code == 200
    assert detail.json()["raw_result_object_id"] == raw_object["id"]

    html = client.get("/api/reports/backtest:run-1/file")
    assert html.status_code == 200
    assert "report" in html.text


def test_reference_data_coverage_api_exposes_level3_data_gaps(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.ashare_repository import import_security_master, import_trade_status, upsert_corporate_actions
    from app.services.pit_data import import_index_members

    import_index_members(
        [{"universe_code": "CSI300", "symbol": "600519", "start_date": "2024-01-01", "announce_date": "2023-12-15"}],
        source="unit",
    )
    import_security_master(
        [
            {
                "symbol": "600519",
                "name": "Kweichow Moutai",
                "listed_date": "2001-08-27",
                "status": "listed",
                "is_st": True,
            },
            {
                "symbol": "000001",
                "name": "Ping An Bank",
                "listed_date": "1991-04-03",
                "delisted_date": "2024-01-31",
                "status": "delisted",
            },
        ],
        source="unit",
        universe_code="ALL_A",
    )
    import_trade_status(
        [
            {
                "symbol": "600519",
                "tradeDate": "2024-01-02",
                "isSuspended": True,
                "isSt": True,
                "canBuy": False,
                "canSell": False,
            }
        ],
        source="unit",
    )
    upsert_corporate_actions(
        [{"symbol": "600519", "exDate": "2024-06-30", "actionType": "dividend", "cashDividend": 10.0}],
        source="unit",
    )

    response = TestClient(app).get("/api/ashare/reference-data/coverage", params={"indexCode": "CSI300"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["securities"]["delisted"] == 1
    assert payload["securities"]["st"] == 1
    assert payload["tradeStatus"]["suspendedDays"] == 1
    assert payload["corporateActions"]["rows"] == 1
    assert payload["pit"]["rows"] == 1
