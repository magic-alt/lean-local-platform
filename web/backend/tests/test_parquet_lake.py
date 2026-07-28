import pytest


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


def test_export_market_daily_bars_to_parquet_and_query_duckdb(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake

    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")

    with db_module.db() as connection:
        for trade_date, close in (
            ("2025-12-31", 100.0),
            ("2026-01-02", 101.0),
            ("2026-02-02", 102.0),
        ):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                     data_type, open, high, low, close, volume, adjust, source, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "inst-600519",
                    "600519",
                    "equity",
                    "china",
                    "china",
                    trade_date,
                    "daily",
                    "trade",
                    close - 1,
                    close + 1,
                    close - 2,
                    close,
                    1000,
                    "raw",
                    "akshare",
                    "now",
                ),
            )

    progress = []
    exported = parquet_lake.export_market_daily_bars(
        source="akshare",
        progress_callback=progress.append,
    )

    assert exported["rowCount"] == 3
    assert exported["fileCount"] == 2
    assert progress[-1]["stage"] == "parquet_export"
    assert progress[-1]["rowsProcessed"] == 3
    assert progress[-1]["expectedRows"] == 3
    assert all(item["size"] > 0 for item in exported["files"])

    datasets = parquet_lake.list_datasets()
    assert datasets[0]["row_count"] == 3
    assert datasets[0]["metadata"]["exported_from"] == "market_daily_bars"
    assert datasets[0]["metadata"]["read_batch"] == "streaming_cursor_100000_rows"
    assert datasets[0]["root_path"].startswith("parquet/")
    with db_module.db() as connection:
        stored_files = connection.execute("select file_path from parquet_files order by file_path").fetchall()
    assert stored_files
    assert all(row["file_path"].startswith("parquet/") for row in stored_files)

    result = parquet_lake.query_duckdb_bars(
        asset_class="equity",
        symbol="SH600519",
        market="china",
        venue="china",
        provider_source="akshare",
        start_date="2026-01-01",
        allow_research_source=True,
    )

    assert result["enabled"] is True
    assert result["source"] == "duckdb"
    assert result["count"] == 2
    assert result["items"][0]["timestamp"] == "2026-01-02"
    assert result["items"][0]["close"] == 101.0

    consistency = parquet_lake.parquet_consistency_report(
        sources=["akshare"],
        include_research_sources=True,
        persist=False,
    )
    assert consistency["severity"] == "ok"
    assert consistency["datasetCount"] == 1
    assert consistency["items"][0]["mysql"]["rowCount"] == 3
    assert consistency["items"][0]["duckdb"]["rowCount"] == 3


def test_rebuild_all_market_parquet_exports_all_matching_scopes_and_persists_report(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake
    from app.services.ashare_multisource import list_quality_reports

    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")

    with db_module.db() as connection:
        for source, symbol, close in (("akshare", "600519", 100.0), ("baostock", "000001", 10.0)):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                     data_type, open, high, low, close, volume, adjust, source, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"inst-{symbol}-{source}",
                    symbol,
                    "equity",
                    "china",
                    "china",
                    "2026-07-03",
                    "daily",
                    "trade",
                    close - 1,
                    close + 1,
                    close - 2,
                    close,
                    1000,
                    "raw",
                    source,
                    "now",
                ),
            )

    result = parquet_lake.rebuild_all_market_parquet(
        asset_class="equity",
        market="china",
        include_research_sources=True,
    )

    assert result["scopeCount"] == 2
    assert result["rebuiltCount"] == 2
    assert result["consistencyReport"]["severity"] == "ok"
    saved = list_quality_reports()
    assert saved[0]["report_type"] == "parquet_consistency"

    research_result = parquet_lake.rebuild_all_market_parquet(
        asset_class="equity",
        market="china",
        sources=["akshare", "baostock"],
        include_research_sources=True,
    )
    assert research_result["scopeCount"] == 2
    assert saved[0]["severity"] == "ok"


def test_rebuild_certifies_only_consistent_tushare_dataset(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake
    from app.services.db_object_store import put_bytes
    from app.services.source_gate import source_certification

    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")
    stored = put_bytes("provider-raw", "daily/evidence.json.gz", b"provider-evidence")

    with db_module.db() as connection:
        connection.execute(
            """
            insert into data_import_batches
                (id, provider, market, asset_class, status, config_json, qa_report_json,
                 started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "batch-tushare", "tushare", "china", "equity", "success",
                '''{"environment":"research","synthetic":false,"provenance":{"environment":"production","syncRunId":"sync-tushare","datasetKey":"daily","scopeKey":"600519","providerEvidence":"ingestion_manifest_and_raw_archive"}}''',
                '{"passed":true,"severity":"ok"}', "now", "now",
            ),
        )
        connection.execute(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,coverage_start,
                 coverage_end,status,validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "manifest-tushare", "sync-tushare", "tushare", "daily", "600519", "{}",
                1, 1, 0, "payload", "keys", "2026-07-03", "2026-07-03", "success",
                '{"status":"passed"}', '{"daily":1}', "now",
            ),
        )
        connection.execute(
            """
            insert into provider_raw_archives
                (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "archive-tushare", "tushare", "daily", "sync-tushare", stored["id"], 1,
                "payload", "archive", 17, 17, "gzip", "now",
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                 data_type, open, high, low, close, volume, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519-tushare", "600519", "equity", "china", "china",
                "2026-07-03", "daily", "trade", 100.0, 102.0, 99.0, 101.0,
                10000, "raw", "tushare", "batch-tushare", "now",
            ),
        )

    before = parquet_lake.export_market_daily_bars(source="tushare")
    assert before["rowCount"] == 1
    assert source_certification("tushare")["isCertified"] is False

    rebuilt = parquet_lake.rebuild_all_market_parquet(
        asset_class="equity",
        market="china",
        sources=["tushare"],
    )

    assert rebuilt["consistencyReport"]["passed"] is True
    assert rebuilt["certifiedDatasetIds"] == [before["id"]]
    certification = source_certification("tushare")
    assert certification["isProduction"] is True
    assert certification["isCertified"] is True
    assert certification["qaStatus"] == "ok"
    assert certification["qaReportId"] == rebuilt["consistencyReport"]["reportId"]
    assert certification["fileManifestSha256"]

    from app.services.market_repository import upsert_market_daily_bars

    upsert_market_daily_bars(
        [
            {
                "symbol": "600519",
                "trade_date": "2026-07-06",
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 11000,
            }
        ],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
        batch_id="batch-tushare",
    )
    assert source_certification("tushare")["isCertified"] is False
    assert source_certification("tushare")["qaStatus"] == "stale"


@pytest.mark.parametrize(
    ("run_mode", "resume_base_mode"),
    [("full_rebuild", None), ("resume_checkpoint", "full_rebuild")],
)
def test_source_lineage_uses_exact_governed_full_rebuild_evidence(
    tmp_path, monkeypatch, run_mode, resume_base_mode
):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import data_sync, parquet_lake
    from app.services.db_object_store import put_bytes

    run = data_sync.create_sync_run(
        requested=["daily"],
        mode="full_rebuild" if run_mode == "resume_checkpoint" else run_mode,
    )
    stored = put_bytes("provider-raw", "daily/governed.json.gz", b"governed-provider-evidence")
    summary = {
        "completionEvidence": {
            "passed": True,
            "items": [
                {
                    "datasetKey": "daily",
                    "passed": True,
                    "responseRows": 1,
                }
            ],
        }
    }
    if resume_base_mode:
        summary["resumeBaseMode"] = resume_base_mode
    with db_module.db() as connection:
        connection.execute(
            """
            update data_sync_runs
            set status='success',canonical_status='ready',mode=?,summary_json=?,finished_at=?
            where id=?
            """,
            (run_mode, db_module.json_dump(summary), "2026-07-23T00:00:00+00:00", run["id"]),
        )
        connection.execute(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,coverage_start,
                 coverage_end,status,validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "manifest-governed", run["id"], "tushare", "daily", "600519", "{}",
                1, 1, 0, "payload", "keys", "2026-07-03", "2026-07-03", "success",
                '{"status":"passed"}', '{"daily":1}', "now",
            ),
        )
        connection.execute(
            """
            insert into provider_raw_archives
                (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "archive-governed", "tushare", "daily", run["id"], stored["id"], 1,
                "payload", "archive", 27, 27, "gzip", "now",
            ),
        )
        connection.execute(
            """
            insert into data_import_batches
                (id, provider, market, asset_class, status, config_json, qa_report_json,
                 started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "batch-before-governed-rebuild", "tushare", "china", "equity", "running",
                '{"environment":"research","synthetic":false}',
                '{}',
                "2026-07-22T00:00:00+00:00", None,
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                 data_type, open, high, low, close, volume, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-governed-lineage", "600519", "equity", "china", "china",
                "2026-07-03", "daily", "trade", 100.0, 102.0, 99.0, 101.0,
                10000, "raw", "tushare", "batch-before-governed-rebuild",
                "2026-07-22T00:01:00+00:00",
            ),
        )

    lineage = parquet_lake._market_source_lineage(
        parquet_lake._normalize_scope(source="tushare"),
        "2026-07-03",
        "2026-07-03",
        expected_row_count=1,
    )

    assert lineage["passed"] is True
    assert lineage["validationMode"] == "governed_full_rebuild"
    assert lineage["runId"] == run["id"]
    assert lineage["responseRows"] == 1
    assert lineage["archivedRows"] == 1

    fallback_lineage = parquet_lake._market_source_lineage(
        parquet_lake._normalize_scope(source="tushare"),
        "2026-07-03",
        "2026-07-03",
        expected_row_count=2,
    )

    assert fallback_lineage["passed"] is True
    assert fallback_lineage["invalidBatches"] == []


def test_rebuild_never_certifies_synthetic_tushare_fixture(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake
    from app.services.source_gate import source_certification

    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")

    with db_module.db() as connection:
        connection.execute(
            """
            insert into data_import_batches
                (id, provider, market, asset_class, status, config_json, qa_report_json,
                 started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "batch-synthetic", "tushare", "china", "equity", "success",
                '{"environment":"research","synthetic":true}',
                '{"passed":true,"severity":"ok","environment":"research","synthetic":true}',
                "now", "now",
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                 data_type, open, high, low, close, volume, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-e2e", "510300", "equity", "china", "china", "2024-01-02",
                "daily", "trade", 3.8, 3.9, 3.7, 3.85, 10000, "raw", "tushare",
                "batch-synthetic", "now",
            ),
        )

    rebuilt = parquet_lake.rebuild_all_market_parquet(
        asset_class="equity",
        market="china",
        sources=["tushare"],
    )

    assert rebuilt["consistencyReport"]["passed"] is False
    assert rebuilt["certifiedDatasetIds"] == []
    assert source_certification("tushare")["isCertified"] is False
    lineage = rebuilt["consistencyReport"]["items"][0]["sourceLineage"]
    assert lineage["invalidBatches"][0]["synthetic"] is True


def test_consistency_report_fails_closed_when_requested_dataset_is_missing(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake

    report = parquet_lake.parquet_consistency_report(
        asset_class="equity",
        market="china",
        sources=["tushare"],
        persist=False,
    )

    assert report["passed"] is False
    assert report["severity"] == "critical"
    assert report["datasetCount"] == 0
    assert report["issues"] == ["parquet_dataset_missing"]


def test_data_api_exports_parquet_and_queries_duckdb(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake

    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path / "parquet")
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")

    with db_module.db() as connection:
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                 data_type, open, high, low, close, volume, adjust, source, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-000001",
                "000001",
                "equity",
                "china",
                "china",
                "2026-07-03",
                "daily",
                "trade",
                10.0,
                11.0,
                9.0,
                10.5,
                10000,
                "raw",
                "akshare",
                "now",
            ),
        )

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    exported = client.post(
        "/api/data/parquet/export",
        json={"assetClass": "equity", "market": "china", "venue": "china", "providerSource": "akshare"},
    )
    assert exported.status_code == 400

    exported = client.post(
        "/api/data/parquet/export",
        json={
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "providerSource": "akshare",
            "allowResearchSource": True,
        },
    )
    assert exported.status_code == 200
    assert exported.json()["rowCount"] == 1

    queried = client.get(
        "/api/data/query",
        params={
            "source": "duckdb",
            "assetClass": "equity",
            "symbol": "000001",
            "market": "china",
            "venue": "china",
                "providerSource": "akshare",
                "allowResearchSource": True,
            },
    )
    assert queried.status_code == 200
    payload = queried.json()
    assert payload["source"] == "duckdb"
    assert payload["count"] == 1
    assert payload["items"][0]["close"] == 10.5


def test_duckdb_query_remaps_host_parquet_path_to_visible_parquet_dir(tmp_path, monkeypatch):
    pytest.importorskip("polars")
    pytest.importorskip("duckdb")
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services import parquet_lake

    visible_root = tmp_path / "parquet"
    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", visible_root)
    monkeypatch.setattr(parquet_lake, "PARQUET_COMPRESSION", "uncompressed")

    with db_module.db() as connection:
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                 data_type, open, high, low, close, volume, adjust, source, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519",
                "600519",
                "equity",
                "china",
                "china",
                "2026-07-03",
                "daily",
                "trade",
                100.0,
                102.0,
                99.0,
                101.0,
                10000,
                "raw",
                "akshare",
                "now",
            ),
        )

    parquet_lake.export_market_daily_bars(source="akshare")
    with db_module.db() as connection:
        rows = connection.execute("select id, file_path from parquet_files").fetchall()
        for row in rows:
            relative = row["file_path"].removeprefix("parquet/")
            connection.execute("update parquet_files set file_path = ? where id = ?", (f"/host/parquet/{relative}", row["id"]))

    result = parquet_lake.query_duckdb_bars(
        symbol="600519",
        provider_source="akshare",
        market="china",
        allow_research_source=True,
    )
    assert result["count"] == 1
    assert result["items"][0]["close"] == 101.0

    consistency = parquet_lake.parquet_consistency_report(
        sources=["akshare"],
        include_research_sources=True,
        persist=False,
    )
    assert consistency["severity"] == "ok"
    assert consistency["items"][0]["resolvedFiles"][0]["visiblePath"].startswith(str(visible_root))
