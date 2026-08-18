from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _init(tmp_path, monkeypatch):
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


def test_csv_upload_filename_is_a_safe_basename():
    from app.api.data import _safe_upload_name

    assert _safe_upload_name(r"..\..\private/evil?.csv") == "evil_.csv"
    with pytest.raises(Exception, match="filename is invalid"):
        _safe_upload_name("../../")


def test_run_ids_have_entropy_even_with_the_same_timestamp(monkeypatch):
    import app.lean_engine.ids as ids

    monkeypatch.setattr(ids.time, "strftime", lambda _format: "20260814120000")
    values = {ids.new_run_id("600519", "2024-01-01", "2024-12-31") for _ in range(50)}
    assert len(values) == 50
    assert all(value.startswith("600519-20240101-20241231-20260814120000-") for value in values)


def test_partial_security_refresh_cannot_clear_delisting(tmp_path, monkeypatch):
    db_module = _init(tmp_path, monkeypatch)
    from app.services.ashare_repository import upsert_security

    upsert_security(
        symbol="600001", name="delisted", listed_date="2000-01-01",
        delisted_date="2024-01-02", status="delisted",
    )
    upsert_security(
        symbol="600001", name="partial", listed_date="2000-01-01",
        delisted_date=None, status="listed",
    )
    with db_module.db() as connection:
        row = connection.execute("select delisted_date,status from securities where symbol='600001'").fetchone()
    assert dict(row) == {"delisted_date": "2024-01-02", "status": "delisted"}


def test_reconciler_marks_ownerless_backtest_and_releases_lease(tmp_path, monkeypatch):
    db_module = _init(tmp_path, monkeypatch)
    from app.services.run_reconciler import reconcile_backtest_runs
    from app.services.scheduler import acquire_scheduler_lease

    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id,task_id,name,symbol,asset_class,venue,resolution,data_type,parameters_json,
                 status,docker_image,container_name,work_dir,results_dir,log_path,created_at,started_at)
            values ('orphaned-backtest','missing-task','orphaned','600519','equity','china','daily',
                    'trade','{}','running','lean:test','lean-orphaned','/tmp/run','/tmp/results',
                    '/tmp/log',?,?)
            """,
            (stale, stale),
        )
    assert acquire_scheduler_lease(
        resource="backtest", holder_id="orphaned-backtest", limit=1, ttl_seconds=600
    )
    result = reconcile_backtest_runs(stale_seconds=60)
    assert result["reconciled"] == [
        {"runId": "orphaned-backtest", "status": "failed", "reason": "owner_task_missing"}
    ]
    with db_module.db() as connection:
        run = connection.execute("select status from backtest_runs where id='orphaned-backtest'").fetchone()
        lease_count = connection.execute("select count(*) as count from scheduler_leases").fetchone()
    assert run["status"] == "failed"
    assert lease_count["count"] == 0


def test_pit_pipeline_rejects_current_constituent_backfill(monkeypatch):
    from app.core.errors import LeanWebError
    from app.services import csi300_data_pipeline as pipeline

    monkeypatch.setattr(pipeline, "universe_as_of", lambda *_args: [])
    with pytest.raises(LeanWebError, match="cannot be materialized"):
        pipeline._materialize_membership_if_empty(["600001"], "2024-01-01", dry_run=False, batch_id="b", warnings=[])
