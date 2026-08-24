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


def test_scheduled_maintenance_persists_independent_layer_watermarks(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.db import db
    from app.services import derived_maintenance, parquet_lake
    from app.services.market_repository import upsert_market_daily_bars

    upsert_market_daily_bars(
        [
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
            {"trade_date": "2024-01-03", "open": 10.5, "high": 12, "low": 10, "close": 11, "volume": 120},
        ],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    scope = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "adjust": "raw",
        "source": "tushare",
    }
    monkeypatch.setattr(parquet_lake, "_available_scopes", lambda **_kwargs: [scope])
    monkeypatch.setattr(
        parquet_lake,
        "export_market_daily_bars",
        lambda **_kwargs: {
            "id": "parquet-dataset",
            "rowCount": 2,
            "fileCount": 1,
            "files": [{"relativePath": "year=2024/part-00000.parquet", "sha256": "a" * 64, "rowCount": 2}],
        },
    )
    monkeypatch.setattr(
        parquet_lake,
        "parquet_consistency_report",
        lambda **_kwargs: {"passed": True, "reportId": "quality-report"},
    )
    monkeypatch.setattr(
        derived_maintenance,
        "_clickhouse_incremental",
        lambda _scope, _start: {"status": "ready", "enabled": True, "inserted": 2, "skipped": 0, "batches": 1, "errors": []},
    )

    run = derived_maintenance.create_maintenance_run(trigger_type="schedule")
    completed = derived_maintenance.run_maintenance(run["id"])
    payload = derived_maintenance.watermarks()

    assert completed["status"] == "success"
    assert {(item["layer_key"], item["status"]) for item in payload["items"]} == {
        ("parquet", "ready"),
        ("clickhouse", "ready"),
    }
    assert {item["materialized_end"] for item in payload["items"]} == {"2024-01-03"}
    assert payload["layers"]["parquet"]["watermark"] == "2024-01-03"
    assert payload["layers"]["clickhouse"]["watermark"] == "2024-01-03"
    with db() as connection:
        assert connection.execute("select count(*) as count from derived_maintenance_runs").fetchone()["count"] == 1


def test_celery_beat_schedules_weekday_derived_maintenance():
    from app.tasks.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule["maintain-derived-layers-after-close"]

    assert schedule["task"] == "lean_web.maintain_derived_layers"
    assert "1-5" in str(schedule["schedule"])


def test_source_certification_recovery_resumes_orphaned_maintenance_run(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from types import SimpleNamespace

    from app.db import db
    from app.services import derived_maintenance
    from app.tasks import worker

    orphaned = derived_maintenance.create_maintenance_run(
        layers=["parquet"],
        trigger_type="source_recertification",
    )
    with db() as connection:
        connection.execute(
            "update derived_maintenance_runs set status='running',started_at=? where id=?",
            ("2026-07-29T13:57:47+00:00", orphaned["id"]),
        )

    discarded = []
    monkeypatch.setattr(
        worker,
        "source_certification",
        lambda *_args, **_kwargs: {"isCertified": False, "isProduction": False},
    )
    monkeypatch.setattr(derived_maintenance, "maintenance_lease_active", lambda: False)
    monkeypatch.setattr(
        worker,
        "_discard_orphaned_maintenance_message",
        lambda run_id: discarded.append(run_id) or 1,
    )
    monkeypatch.setattr(
        worker.maintain_derived_layers_task,
        "apply_async",
        lambda **_kwargs: SimpleNamespace(id="celery-recovery"),
    )

    result = worker.recover_source_certifications_task()

    assert result["status"] == "orphan_checkpoint_resumed"
    assert result["runId"] == orphaned["id"]
    assert discarded == [orphaned["id"]]
    with db() as connection:
        stale = connection.execute(
            "select status,error,finished_at from derived_maintenance_runs where id=?",
            (orphaned["id"],),
        ).fetchone()
    assert stale["status"] == "queued"
    assert stale["error"] == "orphaned_after_worker_restart"
    assert stale["finished_at"] is None


def test_parquet_authority_does_not_require_database_export_start(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.db import db
    from app.services import derived_maintenance
    from app.services.market_repository import upsert_market_daily_bars

    successful = derived_maintenance.create_maintenance_run(layers=["parquet"])
    with db() as connection:
        connection.execute(
            """
            update derived_maintenance_runs
            set status='success',started_at=?,finished_at=?
            where id=?
            """,
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:01:00+00:00", successful["id"]),
        )
    upsert_market_daily_bars(
        [{"trade_date": "2005-04-08", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    scope = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "adjust": "raw",
        "source": "tushare",
    }

    incremental_start = derived_maintenance._parquet_incremental_start(
        scope,
        {
            "materialized_end": "2026-07-22",
            "dataset_id": "stale-parquet-dataset",
        },
        current_row_count=1,
    )

    assert incremental_start is None


def test_clickhouse_child_failure_schedules_checkpoint_retry(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services import derived_maintenance, parquet_lake
    from app.services.market_repository import upsert_market_daily_bars

    upsert_market_daily_bars(
        [{"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    scope = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "adjust": "raw",
        "source": "tushare",
    }
    monkeypatch.setattr(parquet_lake, "_available_scopes", lambda **_kwargs: [scope])
    monkeypatch.setattr(
        derived_maintenance,
        "_clickhouse_incremental",
        lambda _scope, _start: {
            "status": "failed",
            "enabled": True,
            "inserted": 0,
            "errors": [{"symbol": "600519", "error": "mirror unavailable"}],
        },
    )

    run = derived_maintenance.create_maintenance_run(layers=["clickhouse"])
    completed = derived_maintenance.run_maintenance(run["id"])

    assert completed["status"] == "retry_wait"
    assert completed["next_retry_at"]
    assert completed["summary"]["errors"][0]["error"] == "mirror unavailable"
    assert derived_maintenance.watermarks()["items"][0]["status"] == "failed"


def test_clickhouse_bootstrap_replays_only_dates_with_missing_rows(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services import derived_maintenance, market_data
    from app.services.market_repository import upsert_market_daily_bars

    upsert_market_daily_bars(
        [
            {"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100},
            {"trade_date": "2024-01-03", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 120},
        ],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    scope = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "adjust": "raw",
        "source": "tushare",
    }
    captured = []
    monkeypatch.setattr(market_data, "scope_date_counts", lambda _scope: {"2024-01-03": 1})

    def mirror(entries):
        captured.extend(entries)
        return [{"enabled": True, "inserted": len(rows), "skipped": 0, "batches": 1} for _metadata, rows in entries]

    monkeypatch.setattr(market_data, "mirror_rows_batch", mirror)
    monkeypatch.setattr(
        market_data,
        "scope_stats",
        lambda _scope: {
            "enabled": True,
            "rowCount": 2,
            "firstDate": "2024-01-02",
            "lastDate": "2024-01-03",
        },
    )

    result = derived_maintenance._clickhouse_reconcile_dates(scope)

    assert result["status"] == "ready"
    assert result["repairDates"] == 1
    assert result["inserted"] == 1
    assert captured[0][1][0]["date"] == "2024-01-02"


def test_clickhouse_bootstrap_refuses_to_hide_surplus_rows(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services import derived_maintenance, market_data
    from app.services.market_repository import upsert_market_daily_bars

    upsert_market_daily_bars(
        [{"trade_date": "2024-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100}],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    scope = {
        "asset_class": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "adjust": "raw",
        "source": "tushare",
    }
    monkeypatch.setattr(market_data, "scope_date_counts", lambda _scope: {"2024-01-02": 2})

    result = derived_maintenance._clickhouse_reconcile_dates(scope)

    assert result["status"] == "failed"
    assert result["errors"][0]["error"] == "clickhouse_surplus_rows_require_explicit_rebuild"
