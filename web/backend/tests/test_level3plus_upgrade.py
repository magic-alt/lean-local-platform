import hashlib
import json
import sys

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


def seed_level3plus_data(db_module):
    now = "2026-07-07T00:00:00+00:00"
    symbols = ["600519", "000001"]
    dates = ["2026-06-01", "2026-06-02"]
    with db_module.db() as connection:
        connection.execute(
            """
            insert into parquet_datasets
                (id,dataset_key,asset_class,market,venue,resolution,data_type,adjust,source,
                 root_path,schema_version,start_date,end_date,row_count,file_count,metadata_json,
                 created_at,updated_at,dataset_version,environment,is_production,is_certified,
                 certified_at,certified_by,coverage_start,coverage_end,qa_status,qa_report_id)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "dataset-tushare", "equity/china/tushare", "equity", "china", "china",
                "daily", "trade", "raw", "tushare", "parquet/test", 1,
                dates[0], dates[-1], 6, 1, "{}", now, now, "tushare-test-v1",
                "production", 1, 1, now, "unit-consistency-report", dates[0], dates[-1],
                "ok", "qa-unit",
            ),
        )
        connection.execute(
            """
            insert into parquet_files
                (id,dataset_id,file_path,partition_json,row_count,first_timestamp,last_timestamp,
                 sha256,size,created_at)
            values (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "file-tushare", "dataset-tushare", "parquet/test/part.parquet", "{}", 6,
                dates[0], dates[-1], "a" * 64, 1, now,
            ),
        )
        for symbol in symbols:
            connection.execute(
                """
                insert into securities
                    (symbol, name, exchange, market, listed_date, status, is_st, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol, symbol, "SH" if symbol.startswith("6") else "SZ", "china", "2000-01-01", "listed", 0, now, now),
            )
            connection.execute(
                """
                insert into instruments
                    (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange,
                     venue, status, metadata_json, source, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (f"inst-{symbol}", symbol, symbol, symbol, "equity", "china", "SH" if symbol.startswith("6") else "SZ", "china", "active", "{}", "unit", now, now),
            )
            for index, trade_date in enumerate(dates):
                close = 10 + index
                for source in ("tushare", "jqdata", "akshare"):
                    connection.execute(
                        """
                        insert into ashare_daily_bars
                            (symbol, trade_date, open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (symbol, trade_date, close, close + 1, close - 1, close, 1000, 100000, "raw", source, "batch", now),
                    )
                    connection.execute(
                        """
                        insert into market_daily_bars
                            (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                             open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (f"inst-{symbol}", symbol, "equity", "china", "china", trade_date, "daily", "trade", close, close + 1, close - 1, close, 1000, 100000, "raw", source, "batch", now),
                    )
                connection.execute(
                    """
                    insert into ashare_trade_status
                        (symbol, trade_date, is_suspended, limit_up, limit_down, can_buy, can_sell, is_st, source, batch_id)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (symbol, trade_date, 0, close * 1.1, close * 0.9, 1, 1, 0, "akshare:unit", "batch"),
                )
                connection.execute(
                    "insert into adjustment_factors (symbol, trade_date, adj_factor, source, batch_id) values (?, ?, ?, ?, ?)",
                    (symbol, trade_date, 1.0, "jqdata", "batch"),
                )
        for trade_date in dates:
            for source in ("tushare", "jqdata", "akshare"):
                connection.execute(
                    """
                    insert into market_daily_bars
                        (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                         open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("index-000300", "000300", "equity", "china", "china", trade_date, "daily", "trade", 100, 101, 99, 100, 1000, 100000, "raw", source, "batch", now),
                )
        connection.execute(
            """
            update parquet_datasets
            set environment='production',is_production=1,is_certified=1,
                certified_at=?,certified_by='unit-consistency-report',qa_status='ok',qa_report_id='qa-unit'
            where id='dataset-tushare'
            """,
            (now,),
        )
        file_manifest = [
            {
                "path": "parquet/test/part.parquet",
                "rowCount": 6,
                "sha256": "a" * 64,
            }
        ]
        manifest_sha256 = hashlib.sha256(
            json.dumps(file_manifest, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        connection.execute(
            "update parquet_datasets set dataset_version=? where id='dataset-tushare'",
            (f"tushare-{'dataset-tushare'[:12]}-{manifest_sha256[:12]}",),
        )
    return symbols


def test_full_identifier_backfill_scans_all_tables(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    seed_level3plus_data(db_module)

    from app.services.instrument_identity import identifier_coverage, identifiers_for_symbol, upsert_instrument_identifiers

    result = upsert_instrument_identifiers(source="jqdata", dry_run=False)
    assert result["symbols"] >= 3
    coverage = identifier_coverage()
    assert coverage["coverageRatio"] == 1.0
    assert coverage["missingReasons"] == {}
    types = {item["identifier_type"] for item in identifiers_for_symbol("000300")["items"]}
    assert {"raw_symbol", "exchange_symbol", "ts_code", "lean_symbol", "provider_symbol"} <= types


def test_provider_availability_reports_credential_missing(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)

    from app.services.provider_certification import provider_availability_report

    payload = provider_availability_report(["tushare", "jqdata"], persist=True)
    reasons = {item["provider"]: item["unavailableReason"] for item in payload["providers"]}
    assert "credential_missing" in reasons["tushare"]
    assert payload["primaryProvider"] == "tushare"
    assert [item["role"] for item in payload["providers"] if item["provider"] == "tushare"] == ["primary"]
    assert [item["role"] for item in payload["providers"] if item["provider"] == "jqdata"] == ["commercial"]
    assert payload["count"] == 2


def test_certified_universe_records_accepted_warning(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    symbols = seed_level3plus_data(db_module)

    from app.services.instrument_identity import upsert_instrument_identifiers
    from app.services.universe_certification import build_certified_universe, certified_symbols

    upsert_instrument_identifiers(source="tushare", dry_run=False)
    payload = build_certified_universe(
        universe_code="A_SHARE_L3P_TEST",
        source="tushare",
        benchmark="000300",
        start_date="2026-06-01",
        end_date="2026-06-02",
        target_size=2,
        min_size=2,
        candidates=symbols,
        allow_warning_codes=["provider_secondary_missing"],
    )
    assert payload["status"] == "certified"
    assert payload["symbolCount"] == 2
    assert payload["acceptedWarnings"]
    assert certified_symbols("A_SHARE_L3P_TEST") == sorted(symbols)


def test_pipeline_and_alert_api(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.alerts import emit_alert
    from app.services.pipeline_tracking import finish_pipeline_run, record_pipeline_step, start_pipeline_run

    run = start_pipeline_run(universe_code="A_SHARE_L3P_TEST", source="jqdata", benchmark_symbol="000300")
    record_pipeline_step(run["id"], "environment_check", status="ok", details={"ok": True})
    finish_pipeline_run(run["id"], status="passed", severity="ok", decision="LEVEL3_PASS", summary={"ok": True}, warnings=[], errors=[], perf_start=run["perfStart"])
    alert = emit_alert("benchmark_missing", severity="critical", source="unit", related_id=run["id"], details={"benchmark": "999999"})

    client = TestClient(app)
    assert client.get("/api/pipeline-runs").status_code == 200
    assert client.get(f"/api/pipeline-runs/{run['id']}").json()["steps"][0]["step_name"] == "environment_check"
    alert_page = client.get("/api/alert-events").json()
    assert alert_page["items"][0]["id"] == alert["id"]
    assert alert_page["count"] == 1
    assert alert_page["limit"] == 20
    assert alert_page["offset"] == 0
    assert len(alert_page["items"][0]["deliveries"]) <= 3
    assert alert_page["items"][0]["deliveryCount"] >= len(alert_page["items"][0]["deliveries"])
    assert client.post(f"/api/alert-events/{alert['id']}/acknowledge").status_code == 200


def test_retention_policy_dry_run_reports_freed_bytes(tmp_path, monkeypatch, capsys):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services.db_object_store import put_bytes
    from scripts import cleanup_report_artifacts

    item = put_bytes("debug-logs", "old.log", b"debug", metadata={"status": "ok"})
    with db_module.db() as connection:
        connection.execute("update stored_objects set updated_at = ? where id = ?", ("2000-01-01T00:00:00+00:00", item["id"]))
    policy = tmp_path / "retention.yaml"
    policy.write_text("protect_recent_days: 0\nclasses:\n  - name: debug_logs\n    namespaces: [debug-logs]\n    retain_days: 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["cleanup_report_artifacts.py", "--policy", str(policy), "--dry-run", "--json"])
    assert cleanup_report_artifacts.main() == 0
    payload = capsys.readouterr().out
    assert '"wouldDelete": 1' in payload
    assert '"freedBytes": 5' in payload
