from fastapi.testclient import TestClient
import sys


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


def test_demo_algorithm_hard_fails_without_real_ashare_benchmark():
    from pathlib import Path

    code = Path(__file__).resolve().parents[3].joinpath("DockerDemoAlgorithm.py").read_text(encoding="utf-8")

    assert "constant benchmark fallback is disabled" in code
    assert "backtest is blocked" in code
    assert "set_benchmark(lambda time: 1)" not in code


def test_strategy_templates_include_p1_standard_set():
    from app.services.strategies import list_templates, render_python_template

    templates = {item["key"]: item for item in list_templates()}

    assert {
        "buy_hold",
        "sma_cross",
        "donchian_breakout",
        "rsi_reversion",
        "bollinger_reversion",
        "etf_rotation",
        "future_trend",
        "risk_parity",
        "turning_point",
    } <= set(templates)
    assert templates["donchian_breakout"]["parameters"][0]["key"] == "lookback"
    assert templates["etf_rotation"]["parameters"][0]["key"] == "symbols"
    assert templates["sma_cross"]["template_path"].replace("\\", "/").endswith("strategies/templates/sma_cross")
    assert "max(self.highs" in render_python_template("DonchianAlgorithm", "donchian_breakout")
    assert "self.rotation_symbols" in render_python_template("RotationAlgorithm", "etf_rotation")
    assert "inverse_volatility" in render_python_template("RiskParityAlgorithm", "risk_parity")
    assert "self.gap_weight" in render_python_template("TurningPointAlgorithm", "turning_point")


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
    order_events_object = put_bytes(
        "backtest-results",
        "run-1/artifacts/run-1-order-events.json",
        b"[]",
        content_type="application/json",
        metadata={"job_id": "run-1", "kind": "lean-order-events"},
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
    assert item["type"] == "backtest"
    assert item["hasStoredObjects"] is True
    assert item["summaryMetrics"]["Alpha"] == "0.1"
    assert "result" not in item
    assert "storedObjects" not in item

    full_reports = client.get("/api/reports", params={"detail": True})
    assert full_reports.status_code == 200
    full_item = next(report for report in full_reports.json() if report["id"] == "backtest:run-1")
    assert full_item["result"]["summary_metrics"]["Alpha"] == "0.1"
    assert {stored["id"] for stored in full_item["storedObjects"]} == {raw_object["id"], summary_object["id"], order_events_object["id"]}

    detail = client.get("/api/reports/run-1")
    assert detail.status_code == 200
    assert detail.json()["raw_result_object_id"] == raw_object["id"]

    objects = client.get("/api/reports/backtest:run-1/objects")
    assert objects.status_code == 200
    assert {stored["id"] for stored in objects.json()["items"]} == {raw_object["id"], summary_object["id"], order_events_object["id"]}

    html = client.get("/api/reports/backtest:run-1/file")
    assert html.status_code == 200
    assert "report" in html.text


def test_reference_data_coverage_api_exposes_level3_data_gaps(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.db import json_dump, utc_now
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
    import app.db as db_module

    with db_module.db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id, report_type, asset_class, market, symbol, start_date, end_date,
                 sources_json, severity, result_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "reference-report-1",
                "ashare_reference_public_import",
                "equity",
                "china",
                None,
                "2026-07-03",
                "2026-07-03",
                json_dump(["akshare"]),
                "warning",
                json_dump(
                    {
                        "warnings": ["st_endpoint_unavailable"],
                        "sourceStatus": {
                            "provider": "akshare",
                            "errors": [{"source": "stock_zh_a_st_em", "error": "connection reset"}],
                        },
                    }
                ),
                utc_now(),
            ),
        )

    response = TestClient(app).get("/api/ashare/reference-data/coverage", params={"indexCode": "CSI300"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is True
    assert payload["severity"] == "warning"
    assert payload["warnings"] == ["st_endpoint_unavailable"]
    assert payload["referenceSources"]["errors"][0]["source"] == "stock_zh_a_st_em"
    assert payload["securities"]["delisted"] == 1
    assert payload["securities"]["st"] == 1
    assert payload["tradeStatus"]["suspendedDays"] == 1
    assert payload["corporateActions"]["rows"] == 1
    assert payload["pit"]["rows"] == 1


def test_reference_public_import_persists_provider_warning(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    import app.db as db_module
    from scripts.import_ashare_reference_public import persist_reference_import_report

    result = {
        "source": "akshare",
        "asOfDate": "2026-07-03",
        "delisted": {"count": 1},
        "st": {"count": 0},
        "suspended": {"count": 2},
        "corporateActions": {"count": 3},
        "errors": [{"source": "stock_zh_a_st_em", "error": "connection reset"}],
    }

    persist_reference_import_report(result)

    with db_module.db() as connection:
        row = connection.execute("select * from data_quality_reports where report_type = 'ashare_reference_public_import'").fetchone()
    assert row["severity"] == "warning"
    payload = db_module.row_to_dict(row)
    assert payload["result"]["warnings"] == ["st_endpoint_unavailable"]
    assert payload["result"]["sourceStatus"]["counts"]["corporateActions"] == 3


def test_daily_pipeline_cli_dry_run_lists_level3_steps(tmp_path, monkeypatch, capsys):
    configure_temp_db(tmp_path, monkeypatch)

    from scripts import run_daily_pipeline

    monkeypatch.setattr(sys, "argv", ["run_daily_pipeline.py", "--dry-run", "--date", "2026-07-06"])

    assert run_daily_pipeline.main() == 0
    payload = capsys.readouterr().out
    assert "reference" in payload
    assert "multi_source_qa" in payload
    assert "paper_replay" in payload


def test_csi300_public_pit_manifest_reads_csindex_cache_local_path(tmp_path):
    from scripts.import_csi300_pit_public import _read_source

    source_file = tmp_path / "notice.xlsx"
    source_file.write_bytes(b"official-cache-bytes")

    content, local_path = _read_source(
        {"url": "csindex-cache:notice.xlsx", "local_path": str(source_file)},
        cache_dir=tmp_path / "cache",
        source_url="csindex-cache:notice.xlsx",
    )

    assert content == b"official-cache-bytes"
    assert local_path == str(source_file)


def test_csi300_public_pit_manifest_loads_top_level_manual_events():
    from scripts.import_csi300_pit_public import _manual_manifest_events

    events, warnings = _manual_manifest_events(
        {
            "manual_events": [
                {
                    "source_url": "csindex-notice:unit",
                    "announce_date": "2025-01-02",
                    "effective_date": "2025-01-03",
                    "adjustment_type": "temp",
                    "events": [
                        {"symbol": "600001", "name": "Delete Me", "action_type": "delete"},
                        {"symbol": "600002", "name": "Add Me", "action_type": "add"},
                    ],
                }
            ]
        },
        index_code="CSI300",
        batch_id="unit-batch",
        dry_run=True,
    )

    assert warnings == []
    assert {event["action_type"] for event in events} == {"add", "delete"}
    assert {event["symbol"] for event in events} == {"600001", "600002"}


def test_csi300_public_pit_manifest_initial_date_accepts_cached_shape():
    from scripts.import_csi300_pit_public import _initial_date

    assert _initial_date({"initial_effective_date": "2020-01-01"}, "initial_effective_date", "as_of_date") == "2020-01-01"
    assert (
        _initial_date(
            {"coverage_start": "2017-12-08", "initial_reconstruction": {"as_of_date": "2017-12-08"}},
            "initial_effective_date",
            "as_of_date",
        )
        == "2017-12-08"
    )
