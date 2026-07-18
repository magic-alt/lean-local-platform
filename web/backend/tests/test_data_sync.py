from types import SimpleNamespace


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

    assert counts == {"available": 1, "empty": 1, "denied": 1, "retryable": 1, "unknown": 0}
    with db() as connection:
        rows = connection.execute(
            "select dataset_key,permission_status from provider_dataset_catalog where dataset_key in ('stock_basic','daily','fund_basic','trade_cal')"
        ).fetchall()
    assert {row["dataset_key"]: row["permission_status"] for row in rows} == {
        "stock_basic": "available",
        "daily": "empty",
        "fund_basic": "denied",
        "trade_cal": "retryable",
    }


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
        stored = connection.execute("select count(*) as count,max(batch_id) as batch_id from provider_raw_records").fetchone()
    assert stored["count"] == 1
    assert stored["batch_id"] == "batch-3"


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


def test_generic_instrument_sync_uses_persisted_date_watermark(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump, utc_now
    from app.services import data_sync

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


def test_sync_mode_records_initial_incremental_and_checkpoint_resume(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, json_dump, utc_now
    from app.services import data_sync

    first = data_sync.create_sync_run(requested=["daily"])
    assert first["mode"] == "initial_full"
    assert data_sync.request_cancel(first["id"])["status"] == "cancelled"
    resumed = data_sync.prepare_resume(first["id"])
    assert resumed["mode"] == "resume_checkpoint"
    assert resumed["summary"]["resumeBaseMode"] == "initial_full"
    assert data_sync.request_cancel(first["id"])["status"] == "cancelled"

    with db() as connection:
        connection.execute(
            """
            insert into provider_raw_records
                (provider,dataset_key,record_key,business_date,instrument_code,payload_json,
                 content_sha256,batch_id,ingested_at)
            values ('tushare','daily','mode-test','2026-07-16','000001.SZ',?,
                    'hash','mode-test',?)
            """,
            (json_dump({"trade_date": "20260716"}), utc_now()),
        )
    incremental = data_sync.create_sync_run(requested=["daily"])
    assert incremental["mode"] == "incremental"
