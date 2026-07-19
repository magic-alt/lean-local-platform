from dataclasses import replace
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


def test_on_demand_markets_are_excluded_from_full_sync(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import data_sync

    run = data_sync.create_sync_run()
    assert "hk_daily" not in {item["dataset_key"] for item in run["items"]}
    assert "us_daily" not in {item["dataset_key"] for item in run["items"]}
    assert "daily_basic" not in {item["dataset_key"] for item in run["items"]}
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


def test_daily_catalog_coverage_uses_normalized_table(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    data_sync.ensure_catalog()
    with db() as connection:
        connection.execute(
            """
            insert into ashare_daily_bars
                (symbol,trade_date,open,high,low,close,volume,adj_factor,adjust,source,batch_id,created_at)
            values ('000001','2026-07-17',10,11,9,10.5,1000,1,'raw','tushare','batch',?)
            """,
            (utc_now(),),
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
        factors = connection.execute(
            "select trade_date,adj_factor from adjustment_factors where symbol='000001' order by trade_date"
        ).fetchall()
    assert raw["count"] == 0
    assert [(row["trade_date"], row["adj_factor"]) for row in factors] == [
        ("2026-07-16", 123.4),
        ("2026-07-17", 123.5),
    ]


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
    from app.tasks.worker import _broker_contains_sync_run, sync_all_data_task

    routes = celery_app.conf.task_routes
    assert routes["lean_web.sync_all_data"]["queue"] == "data-bulk"
    assert routes["lean_web.recover_data_sync"]["queue"] == "default"
    assert routes["lean_web.fetch_data_batch"]["queue"] == "data-demand"
    assert routes["lean_web.run_backtest"]["queue"] == "backtest"
    assert routes["lean_web.optimize"]["queue"] == "backtest"
    assert sync_all_data_task.acks_late is True
    assert sync_all_data_task.reject_on_worker_lost is True

    class FakeRedis:
        def lrange(self, queue, start, end):
            return [b'{"headers":{"task":"lean_web.sync_all_data","argsrepr":"run-123"}}'] if queue == "data-bulk" else []

        def hvals(self, key):
            return []

    assert _broker_contains_sync_run(FakeRedis(), "run-123") is True
    assert _broker_contains_sync_run(FakeRedis(), "run-456") is False


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
