from contextlib import contextmanager
from dataclasses import replace
import json
import time
from types import SimpleNamespace

import pytest


def configure_temp_platform(tmp_path, monkeypatch):
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


def enable_bulk_dataset_for_test(data_sync, monkeypatch, dataset_key):
    monkeypatch.setattr(
        data_sync,
        "DATASET_REGISTRY",
        tuple(
            replace(spec, sync_policy="bulk") if spec.key == dataset_key else spec
            for spec in data_sync.DATASET_REGISTRY
        ),
    )


class PermissionPro:
    def query(self, api_name, **params):
        if api_name == "stock_basic":
            return [{"ts_code": "600519.SH", "name": "贵州茅台"}]
        if api_name == "daily":
            return []
        if api_name == "fund_basic":
            raise RuntimeError("抱歉，您没有访问该接口的权限，需要更多积分")
        raise RuntimeError("temporary connection timeout")


def test_tushare_permission_probe_distinguishes_available_empty_denied_and_retryable(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import probe_permissions

    adapter = SimpleNamespace(pro=PermissionPro())
    counts = probe_permissions(adapter, only={"stock_basic", "daily", "fund_basic", "trade_cal"})

    assert counts == {"available": 1, "empty": 1, "denied": 0, "retryable": 1, "unknown": 0}
    with db() as connection:
        rows = connection.execute(
            "select dataset_key,permission_status from provider_dataset_catalog where dataset_key in ('stock_basic','daily','fund_basic','trade_cal')"
        ).fetchall()
    assert {row["dataset_key"]: row["permission_status"] for row in rows} == {
        "stock_basic": "available",
        "daily": "empty",
        "fund_basic": "unknown",
        "trade_cal": "retryable",
    }


def test_catalog_active_run_includes_dataset_items(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stock_basic", "daily"])
    catalog = data_sync.catalog_payload()

    assert catalog["activeRun"]["id"] == run["id"]
    assert {item["dataset_key"] for item in catalog["activeRun"]["items"]} == {"stock_basic", "daily"}


def test_default_mysql_datasets_are_included_and_on_demand_markets_are_excluded(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run()
    assert "hk_daily" not in {item["dataset_key"] for item in run["items"]}
    assert "us_daily" not in {item["dataset_key"] for item in run["items"]}
    assert "daily_basic" in {item["dataset_key"] for item in run["items"]}
    assert "moneyflow" in {item["dataset_key"] for item in run["items"]}
    assert "stock_st" in {item["dataset_key"] for item in run["items"]}
    assert "dividend" in {item["dataset_key"] for item in run["items"]}
    assert "fut_basic" in {item["dataset_key"] for item in run["items"]}
    assert "opt_basic" in {item["dataset_key"] for item in run["items"]}
    assert "fut_daily" not in {item["dataset_key"] for item in run["items"]}
    assert "opt_daily" not in {item["dataset_key"] for item in run["items"]}


def test_permission_skip_message_distinguishes_denied_and_rate_limited():
    from app.services.data_sync import _permission_skip_message

    denied = _permission_skip_message("denied", "抱歉，您没有接口(us_daily)访问权限")
    limited = _permission_skip_message("retryable", "抱歉，您访问接口(hk_daily)频率超限")

    assert denied.startswith("Skipped: TuShare permission unavailable.")
    assert limited.startswith("Deferred: TuShare rate limit")
    assert "us_daily" in denied
    assert "hk_daily" in limited


def test_failed_work_is_not_treated_as_a_complete_checkpoint():
    from app.services.data_sync import _checkpoint_complete

    assert _checkpoint_complete({"dataset_key": "adj_factor", "failed": 0, "checkpoint": {"index": 10, "total": 10}})
    assert not _checkpoint_complete({"dataset_key": "adj_factor", "failed": 1, "checkpoint": {"index": 10, "total": 10}})
    assert not _checkpoint_complete({"dataset_key": "daily", "failed": 1, "checkpoint": {"index": 10, "total": 10}})


def test_throughput_uses_session_units_for_resume_rate_and_eta(monkeypatch):
    from app.services import data_sync

    monkeypatch.setattr(data_sync.time, "monotonic", lambda: 110.0)
    metrics = data_sync._throughput_metrics(
        100.0,
        phase="load",
        api_calls=10,
        downloaded=20,
        committed=20,
        processed_units=5_500,
        total_units=6_000,
        rate_units=50,
    )

    assert metrics["sessionProcessedUnits"] == 50
    assert metrics["fetchedUnits"] == 5_500
    assert metrics["unitsPerSecond"] == 5.0
    assert metrics["etaSeconds"] == 100.0


def test_rolling_throughput_uses_recent_window(monkeypatch):
    from app.services import data_sync

    times = iter([100.0, 130.0, 170.0])
    monkeypatch.setattr(data_sync.time, "time", lambda: next(times))
    first = data_sync._rolling_throughput_metrics(
        {
            "downloadedRows": 100,
            "committedRows": 80,
            "sessionProcessedUnits": 10,
            "apiCalls": 10,
            "downloadRowsPerSecond": 100.0,
            "writeRowsPerSecond": 80.0,
            "unitsPerSecond": 10.0,
            "apiCallsPerMinute": 500.0,
            "processedUnits": 10,
            "totalUnits": 100,
        },
        None,
    )
    second = data_sync._rolling_throughput_metrics(
        {**first, "downloadedRows": 400, "committedRows": 320, "sessionProcessedUnits": 40, "processedUnits": 40, "apiCalls": 40},
        first,
    )
    third = data_sync._rolling_throughput_metrics(
        {**second, "downloadedRows": 600, "committedRows": 480, "sessionProcessedUnits": 60, "processedUnits": 60, "apiCalls": 60},
        second,
    )

    assert third["rateWindowSeconds"] == 40.0
    assert third["rollingDownloadRowsPerSecond"] == 5.0
    assert third["rollingWriteRowsPerSecond"] == 4.0
    assert third["rollingUnitsPerSecond"] == 0.5
    assert third["rollingEtaSeconds"] == 80.0


def test_rolling_throughput_reports_zero_after_stall(monkeypatch):
    from app.services import data_sync

    times = iter([100.0, 170.0])
    monkeypatch.setattr(data_sync.time, "time", lambda: next(times))
    first = data_sync._rolling_throughput_metrics(
        {
            "downloadedRows": 100,
            "committedRows": 80,
            "sessionProcessedUnits": 10,
            "apiCalls": 10,
            "downloadRowsPerSecond": 100.0,
            "writeRowsPerSecond": 80.0,
            "unitsPerSecond": 10.0,
            "apiCallsPerMinute": 500.0,
            "processedUnits": 10,
            "totalUnits": 100,
        },
        None,
    )
    stalled = data_sync._rolling_throughput_metrics(first, first)

    assert stalled["rollingDownloadRowsPerSecond"] == 0.0
    assert stalled["rollingWriteRowsPerSecond"] == 0.0
    assert stalled["rollingUnitsPerSecond"] == 0.0
    assert stalled["rollingEtaSeconds"] is None


def test_postgres_connection_loss_pauses_sync_before_next_dataset(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stock_basic", "trade_cal"])
    with db() as connection:
        connection.execute(
            "update provider_dataset_catalog set permission_status='available' "
            "where dataset_key in ('stock_basic','trade_cal')"
        )
    monkeypatch.setattr(data_sync, "probe_permissions", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_sync, "_permission_summary", lambda keys: {})
    monkeypatch.setattr(data_sync, "_latest_open_trade_date", lambda end_date: end_date)
    calls = []

    def lose_database(*args, **kwargs):
        calls.append("stock_basic")
        error = RuntimeError("PostgreSQL connection reset by peer")
        error.sqlstate = "08006"
        raise error

    monkeypatch.setattr(data_sync, "_sync_stock_basic", lose_database)
    monkeypatch.setattr(
        data_sync,
        "_sync_calendar",
        lambda *args, **kwargs: calls.append("trade_cal") or (0, 0, 0),
    )

    result = data_sync.run_sync(run["id"], adapter=SimpleNamespace(pro=SimpleNamespace()))
    stored = data_sync.sync_run(run["id"])

    assert result["status"] == "paused"
    assert result["infrastructureFailure"]["code"] == "DATABASE_CONNECTION_LOST"
    assert calls == ["stock_basic"]
    assert stored["status"] == "paused"
    assert next(item for item in stored["items"] if item["dataset_key"] == "stock_basic")["failed"] == 0
    assert {item["dataset_key"]: item["status"] for item in stored["items"]} == {
        "stock_basic": "paused",
        "trade_cal": "queued",
    }
    resumed = data_sync.prepare_resume(run["id"])
    assert resumed["status"] == "queued"
    resumed_items = {item["dataset_key"]: item for item in resumed["items"]}
    assert resumed_items["stock_basic"]["status"] == "queued"
    assert resumed_items["stock_basic"]["failed"] == 0


def test_required_dataset_failure_stops_dependent_market_sync(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stock_basic", "daily"])
    with db() as connection:
        connection.execute(
            "update provider_dataset_catalog set permission_status='available' "
            "where dataset_key in ('stock_basic','daily')"
        )
    monkeypatch.setattr(data_sync, "_assert_disk_capacity", lambda *args, **kwargs: None)
    monkeypatch.setattr(data_sync, "probe_permissions", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_sync, "_permission_summary", lambda keys: {})
    monkeypatch.setattr(data_sync, "audit_existing_data", lambda: {"detected": 0})
    monkeypatch.setattr(data_sync, "_latest_open_trade_date", lambda end_date: end_date)
    calls = []

    def fail_master(*args, **kwargs):
        calls.append("stock_basic")
        raise RuntimeError("security master rejected")

    monkeypatch.setattr(data_sync, "_sync_stock_basic", fail_master)
    monkeypatch.setattr(
        data_sync,
        "_sync_daily",
        lambda *args, **kwargs: calls.append("daily") or (0, 0, 0, 0),
    )

    result = data_sync.run_sync(run["id"], adapter=SimpleNamespace(pro=SimpleNamespace()))

    assert result["status"] == "failed"
    assert result["blockingFailure"]["dataset"] == "stock_basic"
    assert calls == ["stock_basic"]


def test_paused_daily_resume_preserves_committed_checkpoint(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    checkpoint = {"index": 112, "total": 8_702, "lastCommittedWorkKey": "19910529"}
    with db() as connection:
        connection.execute("update data_sync_runs set status='paused' where id=?", (run["id"],))
        connection.execute(
            "update data_sync_items set status='paused',failed=0,checkpoint_json=? "
            "where run_id=? and dataset_key='daily'",
            (json_dump(checkpoint), run["id"]),
        )

    resumed = data_sync.prepare_resume(run["id"])
    daily = next(item for item in resumed["items"] if item["dataset_key"] == "daily")

    assert daily["status"] == "queued"
    assert daily["checkpoint"] == checkpoint
    assert daily["failed"] == 0


def test_cancelled_connection_loss_run_preserves_daily_and_adj_factor_checkpoints(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily", "adj_factor"])
    daily_checkpoint = {"index": 592, "total": 8_702, "symbol": "1993-04-16"}
    adj_checkpoint = {"index": 1_488, "total": 8_702, "symbol": "1996-11-07"}
    with db() as connection:
        connection.execute("update data_sync_runs set status='cancelled' where id=?", (run["id"],))
        connection.execute(
            "update data_sync_items set status='failed',failed=1,error=?,checkpoint_json=? "
            "where run_id=? and dataset_key='daily'",
            (
                "PostgreSQL connection reset by peer",
                json_dump(daily_checkpoint),
                run["id"],
            ),
        )
        connection.execute(
            "update data_sync_items set status='cancelled',failed=0,checkpoint_json=? "
            "where run_id=? and dataset_key='adj_factor'",
            (json_dump(adj_checkpoint), run["id"]),
        )

    resumed = data_sync.prepare_resume(run["id"])
    items = {entry["dataset_key"]: entry for entry in resumed["items"]}

    assert items["daily"]["status"] == "queued"
    assert items["daily"]["checkpoint"] == daily_checkpoint
    assert items["daily"]["failed"] == 0
    assert items["adj_factor"]["status"] == "queued"
    assert items["adj_factor"]["checkpoint"] == adj_checkpoint


def test_sync_batch_limits_cap_legacy_oversized_environment(monkeypatch):
    from app.services import data_sync

    monkeypatch.setenv("LEAN_DATA_SYNC_CHUNK_ROWS", "500000")
    monkeypatch.setenv("LEAN_DAILY_SYNC_BATCH_UNITS", "64")

    assert data_sync._sync_batch_rows("LEAN_DATA_SYNC_CHUNK_ROWS") == 100_000
    assert data_sync._sync_batch_units("LEAN_DAILY_SYNC_BATCH_UNITS") == 16


def test_daily_sync_flushes_legacy_large_configuration_in_bounded_batches(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setenv("LEAN_DAILY_SYNC_CHUNK_ROWS", "500000")
    monkeypatch.setenv("LEAN_DAILY_SYNC_BATCH_UNITS", "64")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": f"{index:06d}", "listed_date": "2026-07-17"}
            for index in range(1, 21)
        ],
    )
    monkeypatch.setattr(data_sync, "_latest_bars_by_symbol", lambda: {})
    monkeypatch.setattr(data_sync, "_archive_raw_batch", lambda *args, **kwargs: {})
    batch_sizes = []

    def fake_import(entries, **kwargs):
        batch_sizes.append(len(entries))
        return {
            "rows": len(entries),
            "changedRows": len(entries),
            "insertedRows": len(entries),
            "updatedRows": 0,
            "batch_id": "batch",
        }

    monkeypatch.setattr(data_sync, "import_ashare_research_batch", fake_import)

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            return [
                {
                    "symbol": symbol,
                    "trade_date": "2026-07-17",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]

    assert data_sync._sync_daily(Adapter(), run["id"], run["id"], "2026-07-17") == (20, 20, 0, 0)
    assert batch_sizes == [16, 4]


def test_initial_full_daily_uses_full_market_trade_date_partitions(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-16", "status": "listed"}],
    )
    monkeypatch.setattr(data_sync, "_archive_raw_batch", lambda *args, **kwargs: {})
    monkeypatch.setattr(data_sync, "_reconcile_daily_trade_date_batch", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        data_sync,
        "import_ashare_research_batch",
        lambda entries, **kwargs: {"batch_id": "batch", "updatedRows": 0},
    )
    with db() as connection:
        connection.executemany(
            "insert into trade_calendar(market,trade_date,is_open,source) values ('china',?,1,'test')",
            [("2026-07-16",), ("2026-07-17",)],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def daily_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [{
                "symbol": "000001", "date": trade_date, "open": 1, "high": 1,
                "low": 1, "close": 1, "volume": 1,
            }]

    adapter = Adapter()
    assert data_sync._sync_daily(
        adapter,
        run["id"],
        run["id"],
        "2026-07-17",
        full_refresh=True,
        reconcile_full_snapshot=False,
    ) == (2, 2, 0, 0)
    assert adapter.calls == ["2026-07-16", "2026-07-17"]


def test_daily_archive_enqueues_typed_lineage_when_async(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    monkeypatch.setenv("LEAN_TUSHARE_LINEAGE_ASYNC", "1")
    captured = []
    monkeypatch.setattr(
        data_sync,
        "enqueue_lineage_job",
        lambda **kwargs: captured.append(kwargs) or {"jobId": "job", "status": "pending"},
    )
    monkeypatch.setattr(
        data_sync,
        "persist_typed_source_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("typed source must be asynchronous")),
    )
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily")
    result = data_sync._archive_raw_batch(
        spec,
        [{"ts_code": "000001.SZ", "trade_date": "20260717", "close": 10}],
        "run-async",
    )

    assert result["typedSource"] == {"jobId": "job", "status": "pending"}
    assert captured[0]["dataset_key"] == "daily"
    assert captured[0]["row_count"] == 1


def test_daily_batch_write_failure_is_not_retried_as_symbol_failure(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"], mode="full_rebuild")
    monkeypatch.setenv("LEAN_DAILY_SYNC_BATCH_UNITS", "2")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": f"{index:06d}", "listed_date": "2026-07-17"}
            for index in range(1, 6)
        ],
    )
    monkeypatch.setattr(data_sync, "_latest_bars_by_symbol", lambda: {})
    monkeypatch.setattr(data_sync, "_archive_raw_batch", lambda *args, **kwargs: {})
    writes = []

    def fail_batch(entries, **kwargs):
        writes.append([entry["symbol"] for entry in entries])
        raise RuntimeError("canonical batch failed")

    monkeypatch.setattr(data_sync, "import_ashare_research_batch", fail_batch)

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            return [
                {
                    "symbol": symbol,
                    "trade_date": "2026-07-17",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]

    with pytest.raises(RuntimeError, match="canonical batch failed"):
        data_sync._sync_daily(
            Adapter(), run["id"], run["id"], "2026-07-17", full_refresh=True
        )

    assert writes == [["000001", "000002"]]
    with db() as connection:
        statuses = connection.execute(
            "select distinct status from data_sync_work_items where run_id=? and dataset_key='daily'",
            (run["id"],),
        ).fetchall()
    assert {row["status"] for row in statuses} == {"pending"}


def test_daily_resume_uses_committed_work_when_item_checkpoint_was_reset(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    securities = [
        {"symbol": f"{index:06d}", "listed_date": "2026-07-17"}
        for index in range(1, 6)
    ]
    monkeypatch.setattr(data_sync, "_listed_securities", lambda: securities)
    monkeypatch.setattr(data_sync, "_latest_bars_by_symbol", lambda: {})
    monkeypatch.setattr(data_sync, "_archive_raw_batch", lambda *args, **kwargs: {})
    data_sync._ensure_work_items(
        run["id"],
        "daily",
        [(item["symbol"], index) for index, item in enumerate(securities, start=1)],
    )
    with db() as connection:
        connection.execute(
            """
            update data_sync_work_items set status='committed',committed_at=?
            where run_id=? and dataset_key='daily' and sequence_no<=3
            """,
            (utc_now(), run["id"]),
        )
        connection.execute(
            """
            update data_sync_items
            set processed=0,inserted=0,updated=0,failed=0,checkpoint_json=null
            where run_id=? and dataset_key='daily'
            """,
            (run["id"],),
        )
    calls = []

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            calls.append(symbol)
            return [
                {
                    "symbol": symbol,
                    "trade_date": "2026-07-17",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]

    monkeypatch.setattr(
        data_sync,
        "import_ashare_research_batch",
        lambda entries, **kwargs: {
            "rows": len(entries),
            "changedRows": len(entries),
            "insertedRows": len(entries),
            "updatedRows": 0,
            "batch_id": "batch",
        },
    )

    assert data_sync._sync_daily(
        Adapter(), run["id"], run["id"], "2026-07-17", full_refresh=True
    ) == (5, 2, 0, 0)
    assert calls == ["000004", "000005"]


def test_suspend_resume_targets_only_open_failed_instruments(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["suspend_d"])
    with db() as connection:
        connection.execute("update data_sync_runs set status='partial' where id=?", (run["id"],))
        connection.execute(
            """
            update data_sync_items
            set status='partial', processed=5865, failed=2,
                checkpoint_json='{"index":5865,"total":5865}'
            where run_id=? and dataset_key='suspend_d'
            """,
            (run["id"],),
        )
        connection.executemany(
            """
            insert into data_record_issues
                (id,dataset_key,source,instrument_code,start_date,end_date,issue_code,
                 severity,status,details_json,detected_at)
            values (?,'suspend_d','tushare',?,'2020-01-01','2026-07-17','sync_failed',
                    'error','open','{}','2026-07-19T00:00:00+00:00')
            """,
            [("retry-1", "688646"), ("retry-2", "688655")],
        )

    resumed = data_sync.prepare_resume(run["id"])
    item = next(entry for entry in resumed["items"] if entry["dataset_key"] == "suspend_d")

    assert item["status"] == "queued"
    assert item["processed"] == 0
    assert item["failed"] == 0
    assert item["checkpoint"] == {"index": 0, "total": 2, "retryFailedOnly": True}


def test_daily_sync_scope_excludes_b_shares(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.ashare_repository import upsert_security
    from app.services.data_sync import _listed_securities

    for symbol, name, exchange in [
        ("600000", "A share", "SSE"),
        ("900901", "Shanghai B", "SSE"),
        ("200002", "Shenzhen B", "SZSE"),
        ("920001", "Beijing A", "BSE"),
    ]:
        upsert_security(symbol=symbol, name=name, exchange=exchange, listed_date="1990-01-01")

    assert [row["symbol"] for row in _listed_securities()] == ["600000", "920001"]


def test_full_daily_snapshot_reconciliation_removes_absent_canonical_rows(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.services import market_lake
    from app.services.ashare_repository import upsert_daily_bars
    from app.services.data import _reconcile_market_daily_snapshot

    rows = [
        {
            "symbol": "600519",
            "trade_date": trade_date,
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "volume": 1000,
        }
        for trade_date, close in (("2020-07-21", 100.0), ("2026-07-22", 101.0))
    ]
    upsert_daily_bars(rows, source="tushare", batch_id="old", adjust="raw", bulk=True)

    deleted = _reconcile_market_daily_snapshot(
        [
            {
                "symbol": "600519",
                "snapshot_start": "2020-07-21",
                "snapshot_end": "2026-07-22",
            }
        ],
        {"600519": [{**rows[1], "source": "tushare", "adjust": "raw"}]},
    )

    market = market_lake.query_rows(
        kind="bars", source="tushare", columns="trade_date",
        predicates=("symbol='600519'",), order_by="trade_date",
    )
    assert deleted == 1
    assert [row["trade_date"] for row in market] == ["2026-07-22"]


def test_parquet_daily_change_detection_reads_only_market_lake(monkeypatch):
    from app.services import data
    calls = []
    monkeypatch.setattr(data.market_lake, "query_rows", lambda **kwargs: calls.append(kwargs) or [])
    changed, inserted = data._changed_daily_rows(
        [
            {
                "symbol": "000001",
                "trade_date": "2026-07-17",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "amount": 10000,
                "turnover_rate": 1,
                "prev_close": 10,
                "pct_change": 5,
                "adj_factor": 1,
            }
        ]
    )

    assert len(changed) == inserted == 1
    assert len(calls) == 1
    assert calls[0]["kind"] == "bars"


def test_parquet_market_date_change_detection_uses_bounded_source_date_scan(monkeypatch):
    from app.services import data

    calls = []

    rows = [
        {
            "symbol": f"{index:06d}",
            "trade_date": "2026-07-17",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 1000,
            "amount": 10000,
            "turnover_rate": 1,
            "prev_close": 10,
            "pct_change": 5,
            "adj_factor": 1,
        }
        for index in range(1, 501)
    ]
    monkeypatch.setattr(data.market_lake, "query_rows", lambda **kwargs: calls.append(kwargs) or [])
    changed, inserted = data._changed_daily_rows(rows)
    assert len(changed) == inserted == 500
    assert len(calls) == 1
    assert calls[0]["predicates"][:2] == ("trade_date >= ?", "trade_date <= ?")


def test_full_daily_manifest_scope_removes_orphan_symbols(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db
    from app.services import data_sync
    from app.services.ashare_repository import upsert_daily_bars

    run = data_sync.create_sync_run(requested=["daily"], mode="full_rebuild")
    upsert_daily_bars(
        [
            {
                "symbol": "000300",
                "trade_date": "2026-07-22",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1000,
            }
        ],
        source="tushare",
        batch_id="legacy-index",
        adjust="raw",
        bulk=True,
    )
    with db() as connection:
        connection.execute(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,status,
                 validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "manifest-600519", run["id"], "tushare", "daily", "600519", "{}",
                0, 0, 0, "payload", "keys", "success", "{}", "{}", "now",
            ),
        )

    deleted = data_sync._reconcile_daily_manifest_scope(run["id"])

    from app.services import market_lake
    market_count = len(market_lake.query_rows(
        kind="bars", source="tushare", columns="symbol", predicates=("symbol='000300'",),
    ))
    assert deleted == 1
    assert market_count == 0


def test_latest_open_trade_date_avoids_weekend_fanout(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import _latest_open_trade_date

    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) values ('china','2026-07-17',1,'test','test')"
        )

    assert _latest_open_trade_date("2026-07-19") == "2026-07-17"


def test_throughput_api_rate_is_capped_at_configured_quota(monkeypatch):
    from app.services import data_sync

    monkeypatch.setattr(data_sync.time, "monotonic", lambda: 2.0)
    monkeypatch.setattr(data_sync, "_disk_metrics", lambda: {})
    metrics = data_sync._throughput_metrics(
        1.0,
        phase="load",
        api_calls=100,
        downloaded=0,
        committed=0,
    )

    assert metrics["apiCallsPerMinute"] == metrics["apiQuotaPerMinute"]


def test_postgres_storage_metrics_prefer_physical_observer_directory(tmp_path, monkeypatch):
    from app.services import data_sync

    observer = tmp_path / "postgres"
    observer.mkdir()
    (observer / "ibdata1").write_bytes(b"x" * 8192)
    monkeypatch.setattr(data_sync, "database_backend", lambda: "postgresql")
    monkeypatch.setenv("LEAN_POSTGRES_DATA_OBSERVER_DIR", str(observer))
    monkeypatch.setenv("LEAN_POSTGRES_ON_DEMAND_MAX_DATABASE_GB", "50")
    monkeypatch.setattr(data_sync, "_DATABASE_SIZE_CACHE", (0.0, {}))

    metrics = data_sync._database_storage_metrics()

    assert metrics["databaseBytes"] >= 8192
    assert metrics["databaseSizeSource"] == "physical_data_directory"
    assert metrics["databaseLimitBytes"] == 0
    assert metrics["databaseLimitEnforced"] is False
    assert metrics["onDemandDatabaseLimitBytes"] == 50 * 1024**3


def test_on_demand_ceiling_ignores_bulk_database_size_and_limits_single_write(monkeypatch):
    from app.services import data_sync

    gib = 1024**3
    monkeypatch.setattr(
        data_sync,
        "_disk_metrics",
        lambda: {
            "diskFreeBytes": 800 * gib,
            "diskTotalBytes": 1000 * gib,
            "databaseBytes": 153 * gib,
            "onDemandDatabaseLimitBytes": 50 * gib,
        },
    )

    data_sync._assert_disk_capacity(1024)
    data_sync._assert_disk_capacity(2 * 1024**2, enforce_database_limit=True)
    with pytest.raises(RuntimeError, match="on_demand_database_guard"):
        data_sync._assert_disk_capacity(50 * gib + 1, enforce_database_limit=True)


def test_disk_reserve_is_at_least_500_gib_or_half_the_disk(monkeypatch):
    from app.services import data_sync

    gib = 1024**3
    assert data_sync._disk_hard_reserve_bytes(800 * gib) == 500 * gib
    assert data_sync._disk_hard_reserve_bytes(1200 * gib) == 600 * gib

    monkeypatch.setattr(
        data_sync,
        "_disk_metrics",
        lambda: {
            "diskFreeBytes": 510 * gib,
            "diskTotalBytes": 800 * gib,
            "diskReserveBytes": 500 * gib,
            "databaseBytes": 0,
            "onDemandDatabaseLimitBytes": 0,
        },
    )
    data_sync._assert_disk_capacity(10 * gib)
    with pytest.raises(RuntimeError, match="data_sync_disk_guard"):
        data_sync._assert_disk_capacity(10 * gib + 1)


def test_disk_metrics_default_to_durable_data_volume_not_tmpfs(tmp_path, monkeypatch):
    from app.services import data_sync

    monkeypatch.delenv("LEAN_DATA_SYNC_SPOOL_DIR", raising=False)
    monkeypatch.delenv("LEAN_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(data_sync, "DATA_DIR", tmp_path / "data")

    path = data_sync._disk_capacity_path()

    assert path == str(tmp_path / "data")


def test_incremental_plan_replays_recent_dates_and_repairs_bronze_holes(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    monkeypatch.setattr(data_sync.market_lake, "PARQUET_DIR", tmp_path)
    monkeypatch.setenv("LEAN_DATA_SYNC_LOOKBACK_TRADING_DAYS", "2")
    monkeypatch.setenv("LEAN_DATA_SYNC_CATCHUP_TRADING_DAYS", "10")
    dates = [f"2026-07-{day:02d}" for day in range(1, 11)]
    with db() as connection:
        connection.executemany(
            "insert into trade_calendar (market,trade_date,is_open,source) values ('china',?,1,'test')",
            [(trade_date,) for trade_date in dates],
        )
    for trade_date in dates:
        if trade_date == "2026-07-07":
            continue
        partition = (
            tmp_path
            / "bronze"
            / "tushare"
            / "current"
            / "daily"
            / f"trade_date={trade_date.replace('-', '')}"
        )
        partition.mkdir(parents=True)
        (partition / "data.parquet").write_bytes(b"test")
        (partition / "manifest.json").write_text(
            json.dumps({"status": "success"}),
            encoding="utf-8",
        )

    start_after = data_sync._incremental_replay_start_after(
        "daily",
        "2026-07-10",
        "2026-07-10",
    )

    assert start_after == "2026-07-06"


def test_extended_daily_sync_gap_fills_market_and_replays_financials(tmp_path, monkeypatch):
    from app.services import market_lake, tushare_extended_sync

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)

    class Pro:
        def __getattr__(self, endpoint):
            return lambda **params: [{"ts_code": "000001.SZ", **params, "endpoint": endpoint}]

    class Adapter:
        pro = Pro()

        @staticmethod
        def _paged_records(endpoint, *, page_size, **params):
            return endpoint(**params)

    first = tushare_extended_sync.sync_extended_daily(
        Adapter(),
        run_id="run-1",
        end_date="2026-08-14",
        open_dates=["2026-08-12", "2026-08-13", "2026-08-14"],
        financial_lookback_calendar_days=80,
    )

    assert first["failed"] == 0
    assert first["changed"] == 62  # all extended endpoint families are covered
    assert (
        tmp_path
        / "bronze/tushare/current/extended/moneyflow_hsgt/trade_date=20260814/data.parquet"
    ).is_file()
    assert (
        tmp_path
        / "bronze/tushare/current/extended/fina_indicator_vip/trade_date=20260630/data.parquet"
    ).is_file()

    second = tushare_extended_sync.sync_extended_daily(
        Adapter(),
        run_id="run-2",
        end_date="2026-08-14",
        open_dates=["2026-08-12", "2026-08-13", "2026-08-14"],
        financial_lookback_calendar_days=80,
    )

    assert second["failed"] == 0
    assert second["processed"] == 41
    assert second["changed"] == 0


def test_raw_records_are_idempotent_and_changed_payloads_are_updated(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import DATASET_REGISTRY, _save_raw

    spec = next(item for item in DATASET_REGISTRY if item.key == "daily")
    row = {"ts_code": "600519.SH", "trade_date": "20260716", "close": 1500.0}
    assert _save_raw(spec, [row], "batch-1") == (1, 0)
    assert _save_raw(spec, [row], "batch-2") == (0, 0)
    assert _save_raw(spec, [{**row, "close": 1501.0}], "batch-3") == (0, 1)
    with db() as connection:
        stored = connection.execute(
            "select count(*) as count,max(batch_id) as batch_id,max(payload_json) as payload_json "
            "from provider_raw_records"
        ).fetchone()
    assert stored["count"] == 1
    assert stored["batch_id"] == "batch-3"
    assert stored["payload_json"] == ""


def test_legacy_provider_json_cleanup_archives_noncanonical_rows(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync
    from app.services.provider_raw_cleanup import cleanup_legacy_provider_json

    monkeypatch.setattr(data_sync, "_assert_disk_capacity", lambda *args, **kwargs: None)
    now = utc_now()
    with db() as connection:
        connection.executemany(
            """
            insert into provider_raw_records
                (provider,dataset_key,record_key,business_date,instrument_code,payload_json,
                 content_sha256,batch_id,ingested_at)
            values ('tushare',?,?,?,?,?,?,?,?)
            """,
            [
                ("stk_limit", "limit-1", "2026-07-17", "000001", json.dumps({"symbol": "000001", "trade_date": "20260717", "limit_up": 12.0}), "hash-1", "old", now),
                ("suspend_d", "suspend-1", "2026-07-17", "000001", json.dumps({"symbol": "000001", "suspend_date": "20260717", "reason": "test"}), "hash-2", "old", now),
            ],
        )

    result = cleanup_legacy_provider_json(archive_batch_size=1, clear_batch_size=1)

    assert result["before"]["rows"] == 2
    assert result["after"] == {"rows": 0, "jsonBytes": 0, "datasets": []}
    assert result["datasets"]["stk_limit"] == {"archived": 0, "cleared": 1}
    assert result["datasets"]["suspend_d"] == {"archived": 1, "cleared": 1}
    with db() as connection:
        assert connection.execute(
            "select count(*) count from provider_raw_records where payload_json<>''"
        ).fetchone()["count"] == 0
        assert connection.execute(
            "select count(*) count from provider_raw_archives where dataset_key='suspend_d'"
        ).fetchone()["count"] == 1
        assert len(connection.execute(
            "select run_id from provider_raw_archives where dataset_key='suspend_d'"
        ).fetchone()["run_id"]) <= 64


def test_raw_row_hashing_does_not_serialize_json(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily")
    archived = []
    monkeypatch.setattr(
        data_sync,
        "_archive_raw_batch",
        lambda selected, rows, batch_id: archived.append((selected.key, rows, batch_id)) or {},
    )
    monkeypatch.setattr(
        data_sync.json,
        "dumps",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("row JSON serialization is forbidden")),
    )

    assert data_sync._save_raw(
        spec,
        [{"ts_code": "600519.SH", "trade_date": "20260716", "close": 1500.0}],
        "batch-no-json",
    ) == (1, 0)
    assert archived == [
        (
            "daily",
            [{"ts_code": "600519.SH", "trade_date": "20260716", "close": 1500.0}],
            "batch-no-json",
        )
    ]


def test_daily_raw_evidence_is_one_compressed_archive_without_row_json(tmp_path, monkeypatch):
    import gzip
    import json

    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import DATASET_REGISTRY, _save_raw
    from app.services.db_object_store import read_bytes

    spec = next(item for item in DATASET_REGISTRY if item.key == "daily")
    rows = [
        {"ts_code": "600519.SH", "trade_date": "20260716", "close": 1500.0},
        {"ts_code": "600519.SH", "trade_date": "20260717", "close": 1510.0},
    ]

    assert spec.retain_raw is True
    assert _save_raw(spec, rows, "daily-archive-run") == (2, 0)
    with db() as connection:
        archive = connection.execute(
            "select * from provider_raw_archives where run_id='daily-archive-run' and dataset_key='daily'"
        ).fetchone()
        raw = connection.execute(
            "select count(*) as count,min(payload_json) as min_payload,max(payload_json) as max_payload "
            "from provider_raw_records where dataset_key='daily'"
        ).fetchone()

    assert archive["row_count"] == 2
    assert raw["count"] == 2
    assert raw["min_payload"] == raw["max_payload"] == ""
    assert json.loads(gzip.decompress(read_bytes(archive["object_id"]))) == rows


def test_retained_raw_data_uses_one_compressed_batch_archive(tmp_path, monkeypatch):
    import gzip
    import json

    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import DATASET_REGISTRY, _save_raw
    from app.services.db_object_store import read_bytes

    spec = next(item for item in DATASET_REGISTRY if item.key == "suspend_d")
    rows = [
        {"ts_code": "000001.SZ", "suspend_date": "20260716", "suspend_timing": "全天"},
        {"ts_code": "000002.SZ", "suspend_date": "20260716", "suspend_timing": "上午"},
    ]

    assert _save_raw(spec, rows, "archive-run") == (2, 0)
    assert _save_raw(spec, rows, "archive-run-retry") == (0, 0)
    with db() as connection:
        archive = connection.execute(
            "select * from provider_raw_archives where run_id='archive-run' and dataset_key='suspend_d'"
        ).fetchone()
        archive_counts = connection.execute(
            "select count(*) as references_count,count(distinct object_id) as objects_count "
            "from provider_raw_archives where dataset_key='suspend_d'"
        ).fetchone()
        raw = connection.execute(
            "select count(*) as count,min(payload_json) as min_payload,max(payload_json) as max_payload "
            "from provider_raw_records where dataset_key='suspend_d'"
        ).fetchone()

    assert archive["row_count"] == 2
    assert archive["compressed_size"] < archive["uncompressed_size"]
    assert archive_counts["references_count"] == 2
    assert archive_counts["objects_count"] == 1
    assert raw["count"] == 2
    assert raw["min_payload"] == raw["max_payload"] == ""
    assert json.loads(gzip.decompress(read_bytes(archive["object_id"]))) == rows


def test_raw_initial_load_can_skip_lookup_and_remains_idempotent(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import DATASET_REGISTRY, _save_raw

    spec = next(item for item in DATASET_REGISTRY if item.key == "adj_factor")
    rows = [
        {"ts_code": "000001.SZ", "trade_date": "20260716", "adj_factor": 1.0},
        {"ts_code": "000001.SZ", "trade_date": "20260717", "adj_factor": 1.1},
    ]
    assert _save_raw(spec, rows, "batch-1", assume_new=True) == (2, 0)
    assert _save_raw(spec, rows, "batch-2") == (0, 0)
    with db() as connection:
        assert connection.execute("select count(*) as count from provider_raw_records").fetchone()["count"] == 2


def test_only_one_full_database_update_can_be_active_and_cancelled_run_can_resume(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.data_sync import create_sync_run, prepare_resume, request_cancel

    run = create_sync_run(requested=["stock_basic", "daily"])
    assert run["status"] == "queued"
    assert [item["dataset_key"] for item in run["items"]] == ["daily", "stock_basic"]
    try:
        create_sync_run()
        assert False, "duplicate active run should be rejected"
    except ValueError as exc:
        assert "already" in str(exc)
    assert request_cancel(run["id"])["status"] == "cancelled"
    assert prepare_resume(run["id"])["status"] == "queued"


def test_running_full_database_update_is_revoked_and_cancelled_idempotently(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import tasks
    from app.services.data_sync import create_sync_run, request_cancel

    monkeypatch.setattr(tasks, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(tasks, "_revoke_celery", lambda task: None)
    run = create_sync_run(requested=["daily"])
    task = tasks.create_task("data_sync", "Test data sync", {}, related_id=run["id"], status="running")
    with db() as connection:
        connection.execute(
            "update data_sync_runs set task_id=?, status='running', started_at=? where id=?",
            (task["id"], "2026-07-17T00:00:00+00:00", run["id"]),
        )
        connection.execute(
            "update data_sync_items set status='running' where run_id=?",
            (run["id"],),
        )

    cancelled = request_cancel(run["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_requested"] == 1
    assert cancelled["finished_at"]
    assert {item["status"] for item in cancelled["items"]} == {"cancelled"}
    assert tasks.get_task(task["id"])["status"] == "cancelled"
    assert request_cancel(run["id"])["status"] == "cancelled"


def test_cancelled_database_update_is_not_restarted_by_a_delayed_worker(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.data_sync import create_sync_run, request_cancel, run_sync

    run = create_sync_run(requested=["daily"])
    assert request_cancel(run["id"])["status"] == "cancelled"

    class UnexpectedAdapter:
        @property
        def pro(self):
            raise AssertionError("A cancelled run must not contact TuShare.")

    result = run_sync(run["id"], adapter=UnexpectedAdapter())
    assert result == {"status": "cancelled", "cancelled": True, "datasets": {}}


def test_incomplete_success_checkpoint_can_resume_without_losing_progress(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["adj_factor"])
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status='success', finished_at='2026-07-19T00:00:00+00:00' where id=?",
            (run["id"],),
        )
        connection.execute(
            """
            update data_sync_items
            set status='success', processed=59, inserted=422670,
                checkpoint_json=?, finished_at='2026-07-19T00:00:00+00:00'
            where run_id=? and dataset_key='adj_factor'
            """,
            (json_dump({"index": 59, "total": 5893, "symbol": "000070"}), run["id"]),
        )

    resumed = data_sync.prepare_resume(run["id"])
    assert resumed["status"] == "queued"
    item = resumed["items"][0]
    assert item["status"] == "queued"
    assert item["processed"] == 59
    assert item["inserted"] == 422670
    assert item["checkpoint"]["index"] == 59


def test_resume_preserves_completed_partial_dataset(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily", "adj_factor"])
    with db() as connection:
        connection.execute("update data_sync_runs set status='cancelled' where id=?", (run["id"],))
        connection.execute(
            """
            update data_sync_items
            set status='partial', processed=5893, inserted=39004, failed=507,
                checkpoint_json=?
            where run_id=? and dataset_key='daily'
            """,
            (json_dump({"index": 5893, "total": 5893, "symbol": "920128"}), run["id"]),
        )
        connection.execute(
            """
            update data_sync_items set status='cancelled', processed=935, checkpoint_json=?
            where run_id=? and dataset_key='adj_factor'
            """,
            (json_dump({"index": 935, "total": 5893, "symbol": "002312"}), run["id"]),
        )

    resumed = data_sync.prepare_resume(run["id"])
    items = {entry["dataset_key"]: entry for entry in resumed["items"]}

    assert items["daily"]["status"] == "queued"
    assert items["daily"]["processed"] == 0
    assert items["daily"]["failed"] == 0
    assert items["daily"]["checkpoint"] is None
    assert items["adj_factor"]["status"] == "queued"
    assert items["adj_factor"]["checkpoint"]["index"] == 935


def test_superseded_worker_cannot_overwrite_a_resumed_database_update(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services.data_sync import create_sync_run, run_sync, sync_run

    run = create_sync_run(requested=["daily"])
    with db() as connection:
        connection.execute(
            "update data_sync_runs set task_id='new-task', status='queued' where id=?",
            (run["id"],),
        )

    result = run_sync(run["id"], adapter=object(), task_id="old-task")
    assert result == {
        "status": "cancelled",
        "cancelled": True,
        "superseded": True,
        "datasets": {},
    }
    current = sync_run(run["id"])
    assert current and current["status"] == "queued"
    assert current["task_id"] == "new-task"


def test_cancelled_daily_sync_continues_from_its_checkpoint(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    with db() as connection:
        connection.execute(
            """
            update data_sync_items
            set processed=1, inserted=10,
                checkpoint_json=?
            where run_id=? and dataset_key='daily'
            """,
            (json_dump({"index": 1, "symbol": "000001", "total": 3}), run["id"]),
        )
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "2020-01-01"},
            {"symbol": "000002", "listed_date": "2020-01-01"},
            {"symbol": "000003", "listed_date": "2020-01-01"},
        ],
    )
    monkeypatch.setattr(data_sync, "_latest_bar", lambda symbol: None)
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class Adapter:
        def __init__(self):
            self.symbols = []

        def daily_rows(self, symbol, start, end, adjust="raw"):
            self.symbols.append(symbol)
            return []

    adapter = Adapter()
    result = data_sync._sync_daily(adapter, run["id"], run["id"], "2026-07-17")
    assert result == (3, 10, 0, 0)
    assert adapter.symbols == ["000002", "000003"]
    item = data_sync.sync_run(run["id"])["items"][0]
    assert item["checkpoint"]["index"] == 3


def test_daily_sync_does_not_query_past_a_delisting_date(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {
                "symbol": "600001",
                "listed_date": "1990-12-19",
                "delisted_date": "2022-06-28",
                "status": "delisted",
            }
        ],
    )
    monkeypatch.setattr(data_sync, "_latest_bars_by_symbol", lambda: {"600001": "2022-06-28"})

    class Adapter:
        def daily_rows(self, *args, **kwargs):
            raise AssertionError("A fully covered delisted security must not contact TuShare.")

    assert data_sync._sync_daily(Adapter(), run["id"], run["id"], "2026-07-17") == (1, 0, 0, 0)


def test_daily_bulk_sync_uses_authoritative_absence_without_nested_suspend_calls(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-17"}],
    )
    monkeypatch.setattr(data_sync, "_latest_bars_by_symbol", lambda: {})
    imported = []
    progress_updates = []
    original_item = data_sync._item

    def capture_item(run_id, dataset, **fields):
        progress_updates.append(fields)
        return original_item(run_id, dataset, **fields)

    monkeypatch.setattr(data_sync, "_item", capture_item)

    def fake_import(entries, **kwargs):
        imported.append({"entries": entries, **kwargs})
        return {"rows": 1, "changedRows": 1, "insertedRows": 1, "updatedRows": 0, "batch_id": "batch"}

    monkeypatch.setattr(data_sync, "import_ashare_research_batch", fake_import)

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            return [{"symbol": symbol, "trade_date": "2026-07-17", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]

    assert data_sync._sync_daily(Adapter(), run["id"], run["id"], "2026-07-17") == (1, 1, 0, 0)
    assert imported[0]["entries"][0]["symbol"] == "000001"
    assert imported[0]["sync_run_id"] == run["id"]
    assert progress_updates[0]["metrics"]["phase"] == "fetch"
    assert progress_updates[0]["metrics"]["fetchedUnits"] == 0
    assert progress_updates[0]["metrics"]["totalUnits"] == 1
    assert progress_updates[-1]["metrics"]["phase"] == "load"
    assert progress_updates[-1]["metrics"]["fetchedUnits"] == 1


def test_daily_bulk_sync_validates_real_adapter_date_shape(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"], mode="full_rebuild")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-17"}],
    )
    imported = []

    def fake_import(entries, **kwargs):
        imported.append({"entries": entries, **kwargs})
        return {"rows": 1, "changedRows": 1, "insertedRows": 1, "updatedRows": 0, "batch_id": "batch"}

    monkeypatch.setattr(data_sync, "import_ashare_research_batch", fake_import)

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            # This is the actual canonical shape returned by
            # TushareAdapter.daily_rows; it intentionally has ``date`` rather
            # than the raw provider field ``trade_date``.
            return [
                {
                    "date": "2026-07-17",
                    "open": 1.0,
                    "high": 1.1,
                    "low": 0.9,
                    "close": 1.0,
                    "volume": 100,
                }
            ]

    assert data_sync._sync_daily(
        Adapter(), run["id"], run["id"], "2026-07-17", full_refresh=True
    ) == (1, 1, 0, 0)
    assert imported[0]["entries"][0]["rows"][0]["date"] == "2026-07-17"
    assert imported[0]["reconcile_full_snapshot"] is True
    with db() as connection:
        manifest = connection.execute(
            "select * from provider_ingestion_manifests where run_id=? and dataset_key='daily'",
            (run["id"],),
        ).fetchone()
        raw = connection.execute(
            "select * from provider_raw_records where batch_id=? and dataset_key='daily'",
            (run["id"],),
        ).fetchone()
        archive = connection.execute(
            "select * from provider_raw_archives where run_id=? and dataset_key='daily'",
            (run["id"],),
        ).fetchone()
    assert manifest["status"] == "success"
    assert manifest["response_rows"] == 1
    assert raw is None
    assert archive["row_count"] == 1


def test_initial_full_daily_skips_snapshot_deletes(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    assert run["mode"] == "initial_full"
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-17"}],
    )
    monkeypatch.setattr(data_sync, "_archive_raw_batch", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        data_sync,
        "_reconcile_daily_manifest_scope",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("initial full sync must not delete canonical snapshots")
        ),
    )
    imported = []

    def fake_import(entries, **kwargs):
        imported.append({"entries": entries, **kwargs})
        return {
            "rows": 1,
            "changedRows": 1,
            "insertedRows": 1,
            "updatedRows": 0,
            "batch_id": "batch",
        }

    monkeypatch.setattr(data_sync, "import_ashare_research_batch", fake_import)

    class Adapter:
        def daily_rows(self, symbol, start, end, **kwargs):
            return [
                {
                    "symbol": symbol,
                    "trade_date": "2026-07-17",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ]

    assert data_sync._sync_daily(
        Adapter(),
        run["id"],
        run["id"],
        "2026-07-17",
        full_refresh=True,
        reconcile_full_snapshot=False,
    ) == (1, 1, 0, 0)
    assert imported[0]["reconcile_full_snapshot"] is False


def test_empty_instrument_result_advances_coverage_watermark(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    enable_bulk_dataset_for_test(data_sync, monkeypatch, "daily_basic")
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily_basic")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-01"}],
    )

    class Adapter:
        def __init__(self):
            self.calls = 0

        def daily_basic_rows(self, symbol, start, end):
            self.calls += 1
            return []

    first = data_sync.create_sync_run(requested=["daily_basic"])
    adapter = Adapter()
    assert data_sync._sync_generic(adapter, spec, first["id"], first["id"], "2026-07-17") == (1, 0, 0, 0)
    with db() as connection:
        watermark = connection.execute(
            "select coverage_end,empty_result from provider_dataset_watermarks where dataset_key='daily_basic' and scope_key='000001'"
        ).fetchone()
        connection.execute("update data_sync_runs set status='success' where id=?", (first["id"],))
    assert watermark["coverage_end"] == "2026-07-17"
    assert watermark["empty_result"] == 1

    second = data_sync.create_sync_run(requested=["daily_basic"])
    assert data_sync._sync_generic(adapter, spec, second["id"], second["id"], "2026-07-17") == (1, 0, 0, 0)
    assert adapter.calls == 1


def test_quarantined_archive_reconciliation_preserves_ledger_and_records_resolution(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from scripts import reconcile_provider_archives

    with db() as connection:
        connection.execute(
            """
            insert into provider_raw_archive_issues
                (archive_id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,
                 archive_created_at,issue_code,detected_at)
            values ('old-archive','tushare','stock_basic','old-run','missing-object',1,
                    'payload','archive',1,1,'gzip','2026-01-01','stored_object_missing',
                    '2026-01-02')
            """
        )

    monkeypatch.setattr(
        reconcile_provider_archives,
        "_latest_ten_dataset_run",
        lambda: {"id": "verified-run"},
    )
    monkeypatch.setattr(
        reconcile_provider_archives,
        "_sync_completion_evidence",
        lambda run_id, keys: {
            "passed": True,
            "items": [
                {
                    "datasetKey": key,
                    "passed": True,
                    "archiveRequired": False,
                }
                for key in sorted(keys)
            ],
        },
    )
    monkeypatch.setattr(
        reconcile_provider_archives,
        "integrity_report",
        lambda: {"passed": True, "orphanArchives": [], "objectsWithoutChunks": []},
    )

    report = reconcile_provider_archives.reconcile(apply=True)

    assert report["passed"] is True
    assert report["reconciledCount"] == 1
    with db() as connection:
        issue = connection.execute(
            "select * from provider_raw_archive_issues where archive_id='old-archive'"
        ).fetchone()
    assert issue["status"] == "superseded_verified"
    assert issue["resolution_run_id"] == "verified-run"
    assert issue["resolution_code"] == "superseded_by_lossless_canonical_evidence"


def test_suspend_incremental_fetches_once_per_trade_date_not_once_per_symbol(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["suspend_d"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "suspend_d")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "600000", "listed_date": "1999-11-10"},
        ],
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) values ('china','2026-07-17',1,'test','test')"
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','suspend_d',?,'1990-01-01','2026-07-16','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def suspend_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": "000001",
                    "suspend_date": trade_date,
                    "resume_date": "2026-07-18",
                    "suspend_timing": None,
                    "is_full_day": True,
                    "source": "tushare:suspend_d",
                }
            ]

    adapter = Adapter()
    assert data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17") == (1, 1, 0, 0)
    assert adapter.calls == ["2026-07-17"]
    with db() as connection:
        watermarks = connection.execute(
            "select scope_key,coverage_end from provider_dataset_watermarks where dataset_key='suspend_d' order by scope_key"
        ).fetchall()
    assert [(row["scope_key"], row["coverage_end"]) for row in watermarks] == [
        ("000001", "2026-07-17"),
        ("600000", "2026-07-17"),
    ]


def test_daily_basic_increment_fetches_market_once_per_trade_date(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily_basic"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily_basic")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "600000", "listed_date": "1999-11-10"},
        ],
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','daily_basic',?,'1990-01-01','2026-07-16','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def daily_basic_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "factors": {"pe_ttm": 12.0},
                    "source": "tushare:daily_basic",
                }
                for symbol in ("000001", "600000")
            ]

    adapter = Adapter()
    result = data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17")

    assert result == (1, 2, 0, 0)
    assert adapter.calls == ["2026-07-17"]
    from app.services import market_lake
    factors = market_lake.query_rows(
        kind="daily_basic", data_type="metric", source="tushare:daily_basic",
        columns="symbol,trade_date,pe_ttm", order_by="symbol",
    )
    assert [(row["symbol"], row["trade_date"], row["pe_ttm"]) for row in factors] == [
        ("000001", "2026-07-17", 12.0), ("600000", "2026-07-17", 12.0),
    ]


def test_daily_increment_fetches_market_once_per_trade_date(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "600000", "listed_date": "1999-11-10"},
        ],
    )
    monkeypatch.setattr(
        data_sync,
        "import_ashare_research_batch",
        lambda entries, **kwargs: {
            "rows": sum(len(entry["rows"]) for entry in entries),
            "updatedRows": 0,
            "batch_id": "daily-date-batch",
        },
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','daily',?,'1990-01-01','2026-07-16','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def daily_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": symbol,
                    "date": trade_date,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "volume": 100,
                    "adj_factor": 1.0,
                }
                for symbol in ("000001", "600000")
            ]

    adapter = Adapter()
    assert data_sync._sync_daily(adapter, run["id"], run["id"], "2026-07-17") == (1, 2, 0, 0)
    assert adapter.calls == ["2026-07-17"]


def test_bronze_frontier_is_used_when_control_plane_watermark_is_stale(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync, market_lake

    run = data_sync.create_sync_run(requested=["daily"])
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03", "status": "listed"},
            {"symbol": "600000", "listed_date": "1999-11-10", "status": "listed"},
        ],
    )
    monkeypatch.setattr(
        data_sync,
        "import_ashare_research_batch",
        lambda entries, **kwargs: {
            "rows": sum(len(entry["rows"]) for entry in entries),
            "updatedRows": 0,
            "batch_id": "daily-date-batch",
        },
    )
    published = market_lake.PARQUET_DIR / "bronze" / "tushare" / "current" / "daily" / "trade_date=20260716"
    published.mkdir(parents=True)
    (published / "data.parquet").touch()
    (published / "manifest.json").write_text('{"status":"success"}', encoding="utf-8")
    with db() as connection:
        connection.executemany(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china',?,1,'test','test')",
            [("2026-07-16",), ("2026-07-17",)],
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','daily',?,'1990-01-01','2026-07-15','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def daily_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": symbol,
                    "date": trade_date,
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "volume": 100,
                }
                for symbol in ("000001", "600000")
            ]

    adapter = Adapter()
    assert data_sync._sync_daily(adapter, run["id"], run["id"], "2026-07-17") == (2, 4, 0, 0)
    assert adapter.calls == ["2026-07-16", "2026-07-17"]


def test_bronze_frontier_is_not_skipped_when_control_plane_is_ahead(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync, market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    published = tmp_path / "bronze" / "tushare" / "current" / "stk_limit" / "trade_date=20260812"
    published.mkdir(parents=True)
    (published / "data.parquet").touch()
    (published / "manifest.json").write_text('{"status":"success"}', encoding="utf-8")

    assert data_sync._incremental_start_after("stk_limit", "2026-08-17") == "2026-08-12"


def test_market_raw_initial_sync_backfills_without_existing_bronze(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["moneyflow"], mode="auto")
    assert run["mode"] == "initial_full"
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "moneyflow")
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )
    published = []
    monkeypatch.setattr(
        data_sync,
        "_publish_provider_bronze",
        lambda selected, trade_date, rows, *, run_id: published.append(
            (selected.key, trade_date, rows, run_id)
        ),
    )

    class Adapter:
        def market_raw_rows_for_date(self, dataset, trade_date):
            assert dataset == "moneyflow"
            return [{"ts_code": "000001.SZ", "trade_date": trade_date.replace("-", ""), "net_mf_amount": 10.0}]

    result = data_sync._sync_generic(
        Adapter(), spec, run["id"], run["id"], "2026-07-17", full_refresh=True
    )

    assert result == (1, 1, 0, 0)
    assert [(key, trade_date) for key, trade_date, _, _ in published] == [("moneyflow", "2026-07-17")]


def test_adj_factor_date_sync_advances_market_watermarks(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["adj_factor"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "adj_factor")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03", "status": "listed"},
            {"symbol": "600000", "listed_date": "1999-11-10", "status": "listed"},
        ],
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )

    class Adapter:
        def adjustment_factors_for_date(self, trade_date):
            return [
                {"symbol": "000001", "trade_date": trade_date, "adj_factor": 1.0},
                {"symbol": "600000", "trade_date": trade_date, "adj_factor": 2.0},
            ]

    assert data_sync._sync_adj_factor_fast(Adapter(), spec, run["id"], run["id"], "2026-07-17", None, full_refresh=False) == (1, 2, 0, 0)
    with db() as connection:
        rows = connection.execute(
            "select scope_key,coverage_end from provider_dataset_watermarks "
            "where dataset_key='adj_factor' order by scope_key"
        ).fetchall()
    assert [(row["scope_key"], row["coverage_end"]) for row in rows] == [
        ("000001", "2026-07-17"),
        ("600000", "2026-07-17"),
    ]


def test_dividend_increment_fetches_market_once_per_ex_date(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["dividend"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "dividend")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "600000", "listed_date": "1999-11-10"},
        ],
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','dividend',?,'1990-01-01','2026-07-16','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def dividend_rows_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": "600000",
                    "ex_date": trade_date,
                    "action_type": "dividend",
                    "cash_dividend": 0.1,
                    "source": "tushare:dividend",
                    "metadata": {"announce_date": "2026-06-01", "process": "实施"},
                }
            ]

    adapter = Adapter()
    assert data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17") == (1, 1, 0, 0)
    assert adapter.calls == ["2026-07-17"]
    with db() as connection:
        action = connection.execute(
            "select symbol,ex_date,cash_dividend from corporate_actions"
        ).fetchone()
    assert (action["symbol"], action["ex_date"], action["cash_dividend"]) == (
        "600000",
        "2026-07-17",
        0.1,
    )


def test_stk_limit_initial_load_batches_symbols_and_uses_bulk_status_writer(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stk_limit"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "stk_limit")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "2026-07-16", "delisted_date": None},
            {"symbol": "600000", "listed_date": "2026-07-16", "delisted_date": None},
        ],
    )
    bulk_calls = []
    real_normalize = data_sync._normalize_optional

    def capture_normalize(selected, rows, batch_id, *, bulk=False):
        bulk_calls.append((len(rows), bulk))
        return real_normalize(selected, rows, batch_id, bulk=bulk)

    monkeypatch.setattr(data_sync, "_normalize_optional", capture_normalize)

    class Adapter:
        def limit_prices(self, symbol, start, end, *, strict=False):
            assert strict is True
            return {"2026-07-17": {"limitUp": 11.0, "limitDown": 9.0}}

    result = data_sync._sync_generic(Adapter(), spec, run["id"], run["id"], "2026-07-17")

    assert result == (2, 2, 0, 0)
    assert bulk_calls == [(2, True)]
    assert spec.retain_raw is False
    with db() as connection:
        work = connection.execute(
            "select count(*) as count,min(status) as min_status,max(status) as max_status "
            "from data_sync_work_items where run_id=? and dataset_key='stk_limit'",
            (run["id"],),
        ).fetchone()
        manifests = connection.execute(
            "select count(*) as count from provider_ingestion_manifests where run_id=? and dataset_key='stk_limit'",
            (run["id"],),
        ).fetchone()
        raw = connection.execute(
            "select count(*) as count from provider_raw_records where dataset_key='stk_limit'"
        ).fetchone()
    assert work["count"] == 2
    assert work["min_status"] == work["max_status"] == "committed"
    from app.services import market_lake
    assert len(market_lake.query_matching(kind="trade_status", columns="symbol")) == 2
    assert manifests["count"] == 2
    assert raw["count"] == 0


def test_stk_limit_increment_fetches_once_per_trade_date(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stk_limit"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "stk_limit")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "600000", "listed_date": "1999-11-10"},
        ],
    )
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-17',1,'test','test')"
        )
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','stk_limit',?,'1990-01-01','2026-07-16','old',0,'passed',?)
            """,
            [("000001", utc_now()), ("600000", utc_now())],
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def limit_prices_for_date(self, trade_date):
            self.calls.append(trade_date)
            return [
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "limit_up": 11.0,
                    "limit_down": 9.0,
                    "source": "tushare:stk_limit",
                }
                for symbol in ("000001", "600000")
            ]

    adapter = Adapter()
    result = data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17")

    assert result == (1, 2, 0, 0)
    assert adapter.calls == ["2026-07-17"]
    with db() as connection:
        watermarks = connection.execute(
            "select scope_key,coverage_end,last_data_date from provider_dataset_watermarks "
            "where dataset_key='stk_limit' order by scope_key"
        ).fetchall()
    assert [(row["scope_key"], row["coverage_end"], row["last_data_date"]) for row in watermarks] == [
        ("000001", "2026-07-17", "2026-07-17"),
        ("600000", "2026-07-17", "2026-07-17"),
    ]


def test_sparse_increment_accepts_new_listings_after_existing_market_frontier(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["stk_limit"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "stk_limit")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03", "status": "listed"},
            {"symbol": "920238", "listed_date": "2026-07-24", "status": "listed"},
            {"symbol": "000003", "listed_date": "1991-01-14", "status": "delisted"},
        ],
    )
    with db() as connection:
        connection.executemany(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china',?,1,'test','test')",
            [("2026-07-23",), ("2026-07-24",)],
        )
        connection.execute(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_run_id,
                 empty_result,validation_status,updated_at)
            values ('tushare','stk_limit','000001','1991-04-03','2026-07-22',
                    'old',0,'passed',?)
            """,
            (utc_now(),),
        )

    class Adapter:
        def __init__(self):
            self.calls = []

        def limit_prices_for_date(self, trade_date):
            self.calls.append(trade_date)
            symbols = ["000001", *(["920238"] if trade_date == "2026-07-24" else [])]
            return [
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "limit_up": 11.0,
                    "limit_down": 9.0,
                    "source": "tushare:stk_limit",
                }
                for symbol in symbols
            ]

    adapter = Adapter()
    assert data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-24") == (2, 3, 0, 0)
    assert adapter.calls == ["2026-07-23", "2026-07-24"]
    with db() as connection:
        watermarks = connection.execute(
            "select scope_key,coverage_start,coverage_end from provider_dataset_watermarks "
            "where dataset_key='stk_limit' order by scope_key"
        ).fetchall()
    assert [(row["scope_key"], row["coverage_start"], row["coverage_end"]) for row in watermarks] == [
        ("000001", "1991-04-03", "2026-07-24"),
        ("920238", "2026-07-24", "2026-07-24"),
    ]


def test_catalog_basic_rows_store_listing_date_and_backfill_existing_index(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "index_basic")
    row = {"ts_code": "000300.SH", "name": "沪深300", "list_date": "20050408"}

    data_sync.ensure_catalog()
    assert spec.date_field is None
    assert spec.catalog_date_field == "list_date"
    assert data_sync._save_raw(spec, [row], "index-basic-1", archive=False) == (1, 0)
    with db() as connection:
        connection.execute(
            "update provider_raw_records set business_date=null where dataset_key='index_basic'"
        )
    assert data_sync._save_raw(spec, [row], "index-basic-2", archive=False) == (0, 1)
    data_sync._set_catalog_coverage(spec)

    with db() as connection:
        record = connection.execute(
            "select business_date from provider_raw_records where dataset_key='index_basic'"
        ).fetchone()
        catalog = connection.execute(
            "select first_data_date,last_data_date from provider_dataset_catalog "
            "where dataset_key='index_basic'"
        ).fetchone()
    assert record["business_date"] == "2005-04-08"
    assert (catalog["first_data_date"], catalog["last_data_date"]) == ("2005-04-08", "2005-04-08")


def test_incremental_resume_requeues_completed_dated_and_catalog_datasets(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["index_basic", "index_daily"])
    with db() as connection:
        connection.execute(
            "update data_sync_runs set mode='incremental',status='partial' where id=?",
            (run["id"],),
        )
        connection.execute(
            """
            update data_sync_items
            set status='success',processed=1,checkpoint_json=? where run_id=?
            """,
            (json_dump({"index": 1, "total": 1, "symbol": "global"}), run["id"]),
        )
        connection.executemany(
            """
            insert into data_sync_work_items
                (run_id,dataset_key,work_key,sequence_no,status)
            values (?,?,?,1,'committed')
            """,
            [
                (run["id"], "index_basic", "global"),
                (run["id"], "index_daily", "global"),
            ],
        )

    resumed = data_sync.prepare_resume(run["id"])

    assert {entry["dataset_key"]: entry["status"] for entry in resumed["items"]} == {
        "index_basic": "queued",
        "index_daily": "queued",
    }
    assert all(entry["checkpoint"] is None for entry in resumed["items"])
    with db() as connection:
        remaining = connection.execute(
            "select count(*) count from data_sync_work_items where run_id=?",
            (run["id"],),
        ).fetchone()
    assert remaining["count"] == 0


def test_run_sync_refreshes_market_cutoff_after_trade_calendar(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["trade_cal", "index_daily"])
    with db() as connection:
        connection.execute(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
            "values ('china','2026-07-22',1,'test','old')"
        )
        connection.execute(
            "update provider_dataset_catalog set permission_status='available' "
            "where dataset_key in ('trade_cal','index_daily')"
        )

    monkeypatch.setattr(
        data_sync,
        "audit_existing_data",
        lambda: (_ for _ in ()).throw(AssertionError("index-only sync must not scan A-share daily bars")),
    )
    monkeypatch.setattr(data_sync, "probe_permissions", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        data_sync,
        "_sync_completion_evidence",
        lambda *args, **kwargs: {"passed": True, "items": []},
    )
    monkeypatch.setattr(data_sync, "_set_catalog_coverage", lambda spec: None)

    def refresh_calendar(adapter, batch_id, end_date, *, full_refresh=False):
        with db() as connection:
            connection.execute(
                "insert into trade_calendar(market,trade_date,is_open,source,batch_id) "
                "values ('china','2026-07-29',1,'test',?)",
                (batch_id,),
            )
        return 1, 1, 0

    received_end_dates = []

    def sync_generic(adapter, spec, run_id, batch_id, end_date, *args, **kwargs):
        received_end_dates.append((spec.key, end_date))
        return 1, 1, 0, 0

    monkeypatch.setattr(data_sync, "_sync_calendar", refresh_calendar)
    monkeypatch.setattr(data_sync, "_sync_generic", sync_generic)

    summary = data_sync.run_sync(run["id"], adapter=SimpleNamespace(pro=SimpleNamespace()))

    assert summary["marketDataEndDate"] == "2026-07-29"
    assert received_end_dates == [("index_daily", "2026-07-29")]


def test_daily_derivatives_materialize_after_canonical_sync(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data, data_sync, lean_cache, market_data, parquet_lake

    run = data_sync.create_sync_run(requested=["daily"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily")
    row = {"ts_code": "000001.SZ", "trade_date": "20260717", "close": 10}
    data_sync._record_ingestion_manifest(
        run_id=run["id"],
        spec=spec,
        scope_key="000001",
        request={"startDate": "2026-07-17", "endDate": "2026-07-17"},
        rows=[row],
        validation=data_sync._validate_dataset_rows(spec, [row]),
        endpoint_counts={"daily": 1},
        coverage_start="2026-07-17",
        coverage_end="2026-07-17",
    )
    monkeypatch.setattr(lean_cache, "rebuild_ashare_lean_cache_from_db", lambda *args, **kwargs: {"symbol": "000001", "rows": 1})
    monkeypatch.setattr(
        market_data,
        "query_database_bars",
        lambda **kwargs: {"items": [{"timestamp": "2026-07-17", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1}]},
    )
    monkeypatch.setattr(
        market_data,
        "mirror_rows_batch",
        lambda entries: [{"enabled": True, "inserted": len(rows)} for _metadata, rows in entries],
    )
    assets = []
    monkeypatch.setattr(data, "record_data_asset", lambda metadata: assets.append(metadata) or metadata)
    monkeypatch.setattr(
        parquet_lake,
        "rebuild_all_market_parquet",
        lambda **kwargs: {
            "rebuiltCount": 1,
            "certifiedDatasetIds": ["dataset-tushare"],
            "consistencyReport": {"passed": True, "reportId": "qa-parquet"},
        },
    )

    result = data_sync.materialize_daily_run(run["id"])

    assert result["status"] == "ready"
    assert result["completed"] == 1
    assert assets[0]["clickhouse"]["inserted"] == 1
    assert result["parquet"]["passed"] is True
    assert data_sync.sync_run(run["id"])["derivedStatus"]["status"] == "ready"


def test_daily_derivatives_resume_from_persisted_checkpoint(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data, data_sync, lean_cache, market_data, parquet_lake

    run = data_sync.create_sync_run(requested=["daily"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily")
    for symbol in ("000001", "000002"):
        row = {"ts_code": f"{symbol}.SZ", "trade_date": "20260717", "close": 10}
        data_sync._record_ingestion_manifest(
            run_id=run["id"],
            spec=spec,
            scope_key=symbol,
            request={"startDate": "2026-07-17", "endDate": "2026-07-17"},
            rows=[row],
            validation=data_sync._validate_dataset_rows(spec, [row]),
            endpoint_counts={"daily": 1},
            coverage_start="2026-07-17",
            coverage_end="2026-07-17",
        )
    with db() as connection:
        connection.execute(
            "update data_sync_runs set derived_status_json=? where id=?",
            (
                json_dump(
                    {
                        "status": "running",
                        "total": 2,
                        "completed": 1,
                        "failed": 0,
                        "failureSamples": [],
                    }
                ),
                run["id"],
            ),
        )

    rebuilt: list[str] = []
    monkeypatch.setattr(
        lean_cache,
        "rebuild_ashare_lean_cache_from_db",
        lambda symbol, **kwargs: rebuilt.append(symbol) or {"symbol": symbol, "rows": 1},
    )
    monkeypatch.setattr(
        market_data,
        "query_database_bars",
        lambda **kwargs: {"items": [{"timestamp": "2026-07-17", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 1}]},
    )
    monkeypatch.setattr(
        market_data,
        "mirror_rows_batch",
        lambda entries: [{"enabled": True, "inserted": len(rows)} for _metadata, rows in entries],
    )
    monkeypatch.setattr(data, "record_data_asset", lambda metadata: metadata)
    monkeypatch.setattr(
        parquet_lake,
        "rebuild_all_market_parquet",
        lambda **kwargs: {
            "rebuiltCount": 1,
            "certifiedDatasetIds": ["dataset-tushare"],
            "consistencyReport": {"passed": True, "reportId": "qa-parquet"},
        },
    )

    result = data_sync.materialize_daily_run(run["id"])

    assert rebuilt == ["000002"]
    assert result["status"] == "ready"
    assert result["completed"] == 2


def test_on_demand_download_requires_selected_safe_storage_and_writes_jsonl(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    export_root = tmp_path / "external-data"
    monkeypatch.setattr(data_sync, "DATA_DIR", export_root)
    monkeypatch.setattr(data_sync, "HOST_DATA_DIR", export_root)
    monkeypatch.setattr(data_sync, "PARQUET_DIR", export_root / "parquet")
    monkeypatch.setattr(data_sync, "RUNTIME_DIR", tmp_path / "runtime")

    class Adapter:
        def namechange_rows(self, symbol):
            return [
                {
                    "symbol": symbol,
                    "name": "平安银行",
                    "start_date": "2026-07-17",
                    "end_date": None,
                    "is_st": False,
                }
            ]

    result = data_sync.download_on_demand_dataset(
        task_id="task-12345678",
        dataset_key="namechange",
        storage_target="data",
        relative_path="research/factors",
        file_format="jsonl",
        start_date="2026-07-17",
        end_date="2026-07-17",
        symbol="000001",
        adapter=Adapter(),
    )

    output = export_root / "research" / "factors"
    assert result["dataset"] == "namechange"
    assert result["rows"] == 1
    assert result["displayPath"].startswith(str(output))
    assert list(output.glob("*.jsonl"))
    with pytest.raises(ValueError, match="relative path"):
        data_sync._on_demand_destination("data", "../escape")


def test_generic_instrument_sync_uses_persisted_date_watermark(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump, utc_now
    from app.services import data_sync

    enable_bulk_dataset_for_test(data_sync, monkeypatch, "daily_basic")
    run = data_sync.create_sync_run(requested=["daily_basic"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily_basic")
    with db() as connection:
        connection.execute(
            """
            insert into provider_raw_records
                (provider,dataset_key,record_key,business_date,instrument_code,payload_json,
                 content_sha256,batch_id,ingested_at)
            values ('tushare','daily_basic','existing','2026-07-10','000001.SZ',?,
                    'hash','old-batch',?)
            """,
            (json_dump({"ts_code": "000001.SZ", "trade_date": "20260710"}), utc_now()),
        )
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "1991-04-03"}],
    )
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class Adapter:
        def __init__(self):
            self.range = None

        def daily_basic_rows(self, symbol, start, end):
            self.range = (symbol, start, end)
            return []

    adapter = Adapter()
    data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17")
    assert adapter.range == ("000001", "2026-07-11", "2026-07-17")


def test_generic_instrument_sync_preloads_watermarks_once(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    enable_bulk_dataset_for_test(data_sync, monkeypatch, "daily_basic")
    run = data_sync.create_sync_run(requested=["daily_basic"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily_basic")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [
            {"symbol": "000001", "listed_date": "1991-04-03"},
            {"symbol": "000002", "listed_date": "1991-01-29"},
        ],
    )
    preload_calls = []
    monkeypatch.setattr(
        data_sync,
        "_latest_raw_dates_by_instrument",
        lambda selected: preload_calls.append(selected.key) or {"000001": "2026-07-10", "000002": "2026-07-11"},
    )
    monkeypatch.setattr(
        data_sync,
        "_latest_raw_date",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("per-symbol watermark query is not allowed")),
    )
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class Adapter:
        def __init__(self):
            self.ranges = []

        def daily_basic_rows(self, symbol, start, end):
            self.ranges.append((symbol, start, end))
            return []

    adapter = Adapter()
    data_sync._sync_generic(adapter, spec, run["id"], run["id"], "2026-07-17")

    assert preload_calls == ["daily_basic"]
    assert adapter.ranges == [
        ("000001", "2026-07-11", "2026-07-17"),
        ("000002", "2026-07-12", "2026-07-17"),
    ]


def test_generic_normalizer_uses_bulk_loader(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    enable_bulk_dataset_for_test(data_sync, monkeypatch, "daily_basic")
    run = data_sync.create_sync_run(requested=["daily_basic"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily_basic")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "2026-07-17"}],
    )
    calls = []
    monkeypatch.setattr(
        data_sync,
        "_normalize_optional",
        lambda selected, rows, batch_id, *, bulk=False: calls.append((selected.key, len(rows), bulk)),
    )

    class Adapter:
        def daily_basic_rows(self, symbol, start, end):
            return [{"symbol": symbol, "trade_date": "2026-07-17", "factors": {"pe": 10.0}}]

    assert data_sync._sync_generic(Adapter(), spec, run["id"], run["id"], "2026-07-17") == (1, 1, 0, 0)
    assert calls == [("daily_basic", 1, True)]


def test_all_generic_date_parameters_use_requested_range():
    from app.services.data_sync import DATASET_REGISTRY, _generic_params

    for spec in DATASET_REGISTRY:
        params = _generic_params(spec, "2026-07-01", "2026-07-17", "600519" if spec.scope == "instrument" else None)
        if "start_date" in spec.probe:
            assert params["start_date"] == "20260701", spec.key
        for field in ("end_date", "trade_date", "ann_date", "nav_date"):
            if field in spec.probe:
                assert params[field] == "20260717", spec.key


def test_correct_tushare_endpoint_parameters_are_registered():
    from app.services.data_sync import DATASET_REGISTRY

    specs = {item.key: item for item in DATASET_REGISTRY}
    assert specs["fund_daily"].probe == {"trade_date": "20260109"}
    assert specs["fund_nav"].probe == {"nav_date": "20260109"}
    assert specs["fund_nav"].date_field == "nav_date"
    assert specs["lpr"].api_name == "shibor_lpr"


def test_complete_global_query_covers_all_contract_exchanges():
    from app.services import data_sync

    calls = []

    class Pro:
        def query(self, endpoint, **params):
            calls.append((endpoint, params))
            return [{"ts_code": f"{params['exchange']}.001"}]

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "fut_basic")
    rows = data_sync._complete_global_query(Pro(), spec, {"exchange": "CFFEX"})

    assert {params["exchange"] for _, params in calls} == {
        "CFFEX", "DCE", "CZCE", "SHFE", "INE", "GFEX"
    }
    assert len(rows) == 6


def test_complete_index_daily_query_splits_provider_capped_history():
    from datetime import date
    from app.services import data_sync

    calls = []

    class Pro:
        def query(self, endpoint, **params):
            calls.append(params)
            return [
                {
                    "ts_code": params["ts_code"],
                    "trade_date": params["end_date"],
                }
            ]

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "index_daily")
    rows = data_sync._complete_global_query(
        Pro(), spec, {"ts_code": "000300.SH", "start_date": "19900101", "end_date": "20260717"}
    )

    assert len(calls) > 1
    assert {params["ts_code"] for params in calls} == set(data_sync.DEFAULT_INDEX_DAILY_CODES)
    for params in calls:
        start = date.fromisoformat(
            f"{params['start_date'][:4]}-{params['start_date'][4:6]}-{params['start_date'][6:8]}"
        )
        end = date.fromisoformat(
            f"{params['end_date'][:4]}-{params['end_date'][4:6]}-{params['end_date'][6:8]}"
        )
        assert (end - start).days <= 2_499
    assert len(rows) == len(calls)


def test_index_daily_detects_default_codes_missing_behind_legacy_global_watermark(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import init_db
    from app.services import data_sync
    from app.services.market_repository import upsert_market_daily_bars

    init_db()
    upsert_market_daily_bars(
        [{"trade_date": "2026-07-17", "close": 4000}],
        symbol="000300",
        asset_class="index",
        market="china",
        venue="china",
        source="tushare",
    )

    missing = data_sync._missing_default_index_daily_codes()

    assert "000300" not in missing
    assert "000001" in missing
    assert missing == {code.split(".", 1)[0] for code in data_sync.DEFAULT_INDEX_DAILY_CODES} - {"000300"}


def test_index_daily_is_materialized_for_certified_benchmark_cache(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "index_daily")
    data_sync._normalize_optional(
        spec,
        [
            {
                "ts_code": "000300.SH",
                "trade_date": "20230703",
                "open": 3844.22,
                "high": 3893.36,
                "low": 3835.95,
                "close": 3892.88,
                "pre_close": 3842.45,
                "pct_chg": 1.3124,
                "vol": 123.5,
                "amount": 456.75,
            },
            {
                "ts_code": "000300.SH",
                "trade_date": "20030909",
                "open": float("nan"),
                "high": float("nan"),
                "low": float("nan"),
                "close": 1172.051,
                "pre_close": float("nan"),
                "pct_chg": float("nan"),
                "vol": float("nan"),
                "amount": float("nan"),
            },
        ],
        "governed-index-run",
        bulk=True,
    )

    from app.services import market_lake
    rows = market_lake.query_rows(
        kind="bars", asset_class="index", source="tushare",
        columns="trade_date,open,high,low,close,volume,amount,source,batch_id", order_by="trade_date",
    )
    assert len(rows) == 2
    assert rows[0]["open"] == rows[0]["close"] == 1172.051
    assert rows[0]["high"] == rows[0]["low"] == 1172.051
    assert rows[0]["volume"] == rows[0]["amount"] == 0
    assert rows[1]["volume"] == 12350
    assert rows[1]["amount"] == 456750
    assert rows[1]["source"] == "tushare"
    assert rows[1]["batch_id"] == "governed-index-run"


def test_index_daily_normalizer_batches_all_benchmark_symbols(monkeypatch):
    from app.services import data_sync

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "index_daily")
    calls = []
    monkeypatch.setattr(
        data_sync,
        "upsert_market_daily_bars_batch",
        lambda rows, **kwargs: calls.append((rows, kwargs)),
    )

    data_sync._normalize_optional(
        spec,
        [
            {"ts_code": "000300.SH", "trade_date": "20260717", "close": 4000},
            {"ts_code": "000905.SH", "trade_date": "20260717", "close": 6000},
        ],
        "batch",
        bulk=True,
    )

    assert len(calls) == 1
    rows, kwargs = calls[0]
    assert {row["symbol"] for row in rows} == {"000300", "000905"}
    assert kwargs["asset_class"] == "index"
    assert kwargs["bulk"] is True


def test_daily_catalog_coverage_uses_normalized_table(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync
    from app.services.ashare_repository import upsert_daily_bars

    data_sync.ensure_catalog()
    upsert_daily_bars(
        [
            {
                "symbol": "000001",
                "trade_date": "2026-07-17",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 1000,
                "adj_factor": 1,
            }
        ],
        source="tushare",
        batch_id="batch",
        adjust="raw",
    )
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "daily")
    data_sync._set_catalog_coverage(spec)
    with db() as connection:
        item = connection.execute(
            "select row_count,first_data_date,last_data_date from provider_dataset_catalog where dataset_key='daily'"
        ).fetchone()
    assert item["row_count"] == 1
    assert item["first_data_date"] == "2026-07-17"
    assert item["last_data_date"] == "2026-07-17"


def test_stock_basic_catalog_coverage_uses_canonical_instruments(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync
    from app.services.ashare_repository import import_security_master

    data_sync.ensure_catalog()
    import_security_master(
        [
            {
                "symbol": "000001",
                "name": "平安银行",
                "exchange": "SZSE",
                "listed_date": "1991-04-03",
                "status": "listed",
            }
        ],
        source="tushare:stock_basic",
        universe_code="ALL_A",
        bulk=True,
    )
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "stock_basic")
    data_sync._set_catalog_coverage(spec)

    with db() as connection:
        item = connection.execute(
            "select row_count,first_data_date,last_data_date from provider_dataset_catalog "
            "where dataset_key='stock_basic'"
        ).fetchone()
    assert item["row_count"] == 1
    assert item["first_data_date"] == "1991-04-03"
    assert item["last_data_date"] == "1991-04-03"


def test_adj_factor_sync_persists_only_normalized_rows(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["adj_factor"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "adj_factor")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "1991-04-03"}],
    )
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class Adapter:
        def adjustment_factors(self, symbol, start, end):
            assert (symbol, start, end) == ("000001", "1991-04-03", "2026-07-17")
            return {"2026-07-16": 123.4, "2026-07-17": 123.5}

    result = data_sync._sync_generic(Adapter(), spec, run["id"], run["id"], "2026-07-17")
    assert result == (1, 2, 0, 0)
    with db() as connection:
        raw = connection.execute(
            "select count(*) as count from provider_raw_records where dataset_key='adj_factor'"
        ).fetchone()
    from app.services import market_lake
    factors = market_lake.query_rows(
        kind="adjustment_factor", data_type="factor", source="tushare",
        columns="trade_date,adj_factor", predicates=("symbol='000001'",), order_by="trade_date",
    )
    assert raw["count"] == 0
    assert [(row["trade_date"], row["adj_factor"]) for row in factors] == [
        ("2026-07-16", 123.4),
        ("2026-07-17", 123.5),
    ]


def test_adj_factor_rebuild_filters_unchanged_rows_but_keeps_corrections(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync
    from app.services.ashare_repository import upsert_adjustment_factors

    row = {"symbol": "000001", "trade_date": "2026-07-17", "adj_factor": 123.5}
    upsert_adjustment_factors([row], source="tushare", batch_id="old", bulk=True)

    assert data_sync._changed_adjustment_factor_rows([row]) == []
    corrected = {**row, "adj_factor": 123.6}
    assert data_sync._changed_adjustment_factor_rows([corrected]) == [corrected]


def test_generic_sync_records_instrument_failure_instead_of_swallowing_it(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["adj_factor"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "adj_factor")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "1991-04-03"}],
    )
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class Adapter:
        def adjustment_factors(self, symbol, start, end):
            raise RuntimeError("TuShare rate limit")

    assert data_sync._sync_generic(Adapter(), spec, run["id"], run["id"], "2026-07-17") == (1, 0, 0, 1)
    item = data_sync.sync_run(run["id"])["items"][0]
    assert "TuShare rate limit" in item["error"]
    with db() as connection:
        issue = connection.execute(
            "select * from data_record_issues where dataset_key='adj_factor' and instrument_code='000001'"
        ).fetchone()
    assert issue["status"] == "open"
    assert "TuShare rate limit" in issue["details_json"]


def test_adj_factor_resume_retries_failed_work_item_without_restarting(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["adj_factor"])
    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "adj_factor")
    monkeypatch.setattr(
        data_sync,
        "_listed_securities",
        lambda: [{"symbol": "000001", "listed_date": "1991-04-03"}],
    )
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    class FailingAdapter:
        def adjustment_factors(self, symbol, start, end):
            raise RuntimeError("temporary")

    assert data_sync._sync_generic(FailingAdapter(), spec, run["id"], run["id"], "2026-07-17") == (1, 0, 0, 1)
    with db() as connection:
        connection.execute("update data_sync_runs set status='partial' where id=?", (run["id"],))
        connection.execute(
            "update data_sync_items set status='partial' where run_id=? and dataset_key='adj_factor'",
            (run["id"],),
        )
    resumed = data_sync.prepare_resume(run["id"])
    assert resumed["items"][0]["failed"] == 0

    class SuccessfulAdapter:
        def adjustment_factors(self, symbol, start, end):
            return {"2026-07-17": 2.0}

    assert data_sync._sync_generic(SuccessfulAdapter(), spec, run["id"], run["id"], "2026-07-17") == (1, 1, 0, 0)
    with db() as connection:
        work = connection.execute(
            "select status,attempts from data_sync_work_items where run_id=? and work_key='000001'",
            (run["id"],),
        ).fetchone()
    assert work["status"] == "committed"
    assert work["attempts"] == 2


def test_celery_routes_keep_data_and_backtests_on_separate_queues():
    from app.tasks.celery_app import celery_app
    from app.tasks.worker import sync_all_data_task

    routes = celery_app.conf.task_routes
    assert routes["lean_web.sync_all_data"]["queue"] == "data-bulk"
    assert routes["lean_web.materialize_sync_data"]["queue"] == "data-demand"
    assert routes["lean_web.download_on_demand_dataset"]["queue"] == "data-demand"
    assert routes["lean_web.recover_data_sync"]["queue"] == "default"
    assert routes["lean_web.fetch_data_batch"]["queue"] == "data-demand"
    assert routes["lean_web.run_backtest"]["queue"] == "backtest"
    assert "lean_web.optimize" not in routes
    assert sync_all_data_task.acks_late is True
    assert sync_all_data_task.reject_on_worker_lost is True
    assert celery_app.conf.broker_url.startswith("amqp://")
    assert str(celery_app.conf.result_backend).startswith("db+postgresql+psycopg://")
    assert celery_app.conf.broker_transport_options["confirm_publish"] is True
    assert celery_app.conf.task_default_delivery_mode == "persistent"
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert {queue.name for queue in celery_app.conf.task_queues} == {
        "default", "data-bulk", "data-lineage", "data-demand", "backtest", "ml"
    }
    assert all(queue.durable for queue in celery_app.conf.task_queues)


def test_recovery_requeues_stale_derived_materialization(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db, json_dump
    from app.services import data_sync
    from app.tasks import worker

    run = data_sync.create_sync_run(requested=["daily"])
    payload = {
        "status": "running",
        "total": 2,
        "completed": 1,
        "failed": 0,
        "heartbeatAt": "2000-01-01T00:00:00+00:00",
    }
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status='success',canonical_status='ready',finished_at=?,derived_status_json=? where id=?",
            ("2000-01-01T00:00:00+00:00", json_dump(payload), run["id"]),
        )

    monkeypatch.setattr(worker, "_materialization_lease_active", lambda run_id: False)
    queued: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        worker.materialize_sync_data_task,
        "apply_async",
        lambda *, args, queue: queued.append((args, queue)),
    )

    result = worker.recover_data_sync_task.run()

    assert result["recoveredDerived"] == [run["id"]]
    assert queued == [([run["id"]], "data-demand")]
    assert data_sync.sync_run(run["id"])["derivedStatus"]["status"] == "queued"
    assert data_sync.sync_run(run["id"])["derivedStatus"]["recoveryReason"] == "stale_derived_heartbeat"


def test_recovery_preserves_stale_derived_materialization_with_live_lease(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db, json_dump
    from app.services import data_sync
    from app.tasks import worker

    run = data_sync.create_sync_run(requested=["daily"])
    payload = {
        "status": "running",
        "total": 2,
        "completed": 1,
        "failed": 0,
        "heartbeatAt": "2000-01-01T00:00:00+00:00",
    }
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status='success',canonical_status='ready',finished_at=?,derived_status_json=? where id=?",
            ("2000-01-01T00:00:00+00:00", json_dump(payload), run["id"]),
        )

    monkeypatch.setattr(worker, "_materialization_lease_active", lambda run_id: True)
    queued = []
    monkeypatch.setattr(
        worker.materialize_sync_data_task,
        "apply_async",
        lambda **kwargs: queued.append(kwargs),
    )

    result = worker.recover_data_sync_task.run()

    assert result["recoveredDerived"] == []
    assert result["preservedDerived"] == [run["id"]]
    assert queued == []
    assert data_sync.sync_run(run["id"])["derivedStatus"]["status"] == "running"


def test_partial_data_sync_never_marks_outer_task_success(monkeypatch):
    from app.tasks import worker

    updates = []
    monkeypatch.setattr(worker, "get_task", lambda task_id: {"id": task_id, "status": "queued"})
    monkeypatch.setattr(worker, "update_task", lambda task_id, **values: updates.append(values))
    monkeypatch.setattr(worker, "append_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_record_task_metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker.data_sync, "run_sync", lambda run_id, task_id: {"status": "partial"})

    result = worker.sync_all_data_task.run("task-1", "run-1")

    assert result["status"] == "partial"
    assert updates[-1]["status"] == "failed"
    assert updates[-1]["error"] == "One or more datasets require retry."


def test_database_infrastructure_pause_marks_task_retryable_and_alerts(monkeypatch):
    from app.tasks import worker

    updates = []
    alerts = []
    monkeypatch.setattr(worker, "get_task", lambda task_id: {"id": task_id, "status": "queued"})
    monkeypatch.setattr(worker, "update_task", lambda task_id, **values: updates.append(values))
    monkeypatch.setattr(worker, "append_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_record_task_metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker.data_sync, "run_sync", lambda run_id, task_id: {"status": "paused"})
    monkeypatch.setattr(worker, "_emit_operational_alert", lambda event_type, **kwargs: alerts.append((event_type, kwargs)))

    result = worker.sync_all_data_task.run("task-1", "run-1")

    assert result["status"] == "paused"
    assert updates[-1]["status"] == "failed"
    assert "paused" in updates[-1]["error"]
    assert alerts[0][0] == "data_sync_paused"
    assert alerts[0][1]["details"]["retryable"] is True


def test_failed_data_sync_emits_critical_operational_alert(monkeypatch):
    from app.tasks import worker

    updates = []
    alerts = []
    monkeypatch.setattr(worker, "get_task", lambda task_id: {"id": task_id, "status": "queued"})
    monkeypatch.setattr(worker, "update_task", lambda task_id, **values: updates.append(values))
    monkeypatch.setattr(worker, "append_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_record_task_metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker.data_sync,
        "run_sync",
        lambda run_id, task_id: (_ for _ in ()).throw(RuntimeError("provider schema changed")),
    )
    monkeypatch.setattr(worker, "_emit_operational_alert", lambda event_type, **kwargs: alerts.append((event_type, kwargs)))

    with pytest.raises(RuntimeError, match="provider schema changed"):
        worker.sync_all_data_task.run("task-1", "run-1")

    assert updates[-1]["status"] == "failed"
    assert alerts[0][0] == "data_sync_failed"
    assert alerts[0][1]["severity"] == "critical"
    assert alerts[0][1]["related_id"] == "run-1"


def test_transient_provider_failures_are_retried(monkeypatch):
    from app.services import data_sync

    calls = []
    monkeypatch.setattr(data_sync.time, "sleep", lambda seconds: None)

    def operation():
        calls.append(True)
        if len(calls) < 3:
            raise RuntimeError("每分钟最多访问该接口500次")
        return "ok"

    assert data_sync._call_with_retry(operation) == "ok"
    assert len(calls) == 3


def test_recent_permission_checks_are_reused(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    data_sync.ensure_catalog()
    with db() as connection:
        connection.execute(
            """
            update provider_dataset_catalog
            set permission_status='available', last_checked_at=?
            where provider='tushare' and dataset_key='daily'
            """,
            (utc_now(),),
        )
    assert data_sync._permission_probe_keys({"daily"}) == set()


def test_checkpoint_progress_cannot_move_backwards(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    with db() as connection:
        connection.execute(
            """
            update data_sync_items
            set processed=705, inserted=399505, failed=6, checkpoint_json=?
            where run_id=? and dataset_key='daily'
            """,
            (json_dump({"index": 711, "symbol": "002087", "total": 5893}), run["id"]),
        )
    data_sync._item(
        run["id"],
        "daily",
        processed=202,
        inserted=100,
        failed=2,
        checkpoint={"index": 204, "symbol": "000602", "total": 5893},
    )
    item = data_sync.sync_run(run["id"])["items"][0]
    assert item["checkpoint"]["index"] == 711
    assert item["processed"] == 705
    assert item["inserted"] == 399505
    assert item["failed"] == 6


def test_sync_item_progress_updates_run_heartbeat(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"])
    data_sync._item(
        run["id"],
        "daily",
        processed=1,
        checkpoint={"index": 1, "symbol": "000001", "total": 2},
    )
    with db() as connection:
        heartbeat = connection.execute(
            "select heartbeat_at from data_sync_runs where id=?",
            (run["id"],),
        ).fetchone()
    assert heartbeat["heartbeat_at"]


def test_daily_reconciliation_keeps_run_heartbeat_alive(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(requested=["daily"], mode="full_rebuild")
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status='running',heartbeat_at=null where id=?",
            (run["id"],),
        )

    def slow_delete(**kwargs):
        time.sleep(0.25)
        return 0

    monkeypatch.setattr(data_sync.market_lake, "delete_snapshot_absences", slow_delete)
    data_sync._reconcile_daily_trade_date_batch(
        "2026-07-16",
        "2026-07-17",
        [{"symbol": "000001", "date": "2026-07-17"}],
        run_id=run["id"],
        heartbeat_interval_seconds=0.1,
    )

    with db() as connection:
        heartbeat = connection.execute(
            "select heartbeat_at from data_sync_runs where id=?",
            (run["id"],),
        ).fetchone()
    assert heartbeat["heartbeat_at"]


def test_sync_mode_records_initial_incremental_and_checkpoint_resume(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    first = data_sync.create_sync_run(requested=["daily"])
    assert first["mode"] == "initial_full"
    assert data_sync.request_cancel(first["id"])["status"] == "cancelled"
    resumed = data_sync.prepare_resume(first["id"])
    assert resumed["mode"] == "resume_checkpoint"
    assert resumed["summary"]["resumeBaseMode"] == "initial_full"
    assert data_sync.request_cancel(first["id"])["status"] == "cancelled"

    # The UI and auto mode remember a completed canonical build, rather than
    # treating an incidental preview/raw row as proof that the library exists.
    with db() as connection:
        connection.execute(
            """
            update data_sync_runs
            set status='success', canonical_status='ready', finished_at=?
            where id=?
            """,
            (utc_now(), first["id"]),
        )
    catalog = data_sync.catalog_payload()
    assert catalog["hasCompletedInitialSync"] is True
    assert catalog["recommendedMode"] == "incremental"
    incremental = data_sync.create_sync_run(requested=["daily"])
    assert incremental["mode"] == "incremental"
