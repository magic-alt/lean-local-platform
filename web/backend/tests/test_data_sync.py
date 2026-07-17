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
