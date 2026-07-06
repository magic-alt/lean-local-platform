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


def test_scheduler_lease_enforces_max_concurrent_slots(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.scheduler import acquire_scheduler_lease, active_scheduler_leases, release_scheduler_lease

    first = acquire_scheduler_lease(
        resource="backtest",
        holder_id="run-1",
        limit=1,
        ttl_seconds=600,
        metadata={"task_id": "task-1"},
    )
    second = acquire_scheduler_lease(
        resource="backtest",
        holder_id="run-2",
        limit=1,
        ttl_seconds=600,
        metadata={"task_id": "task-2"},
    )

    assert first is not None
    assert first["slot_index"] == 0
    assert second is None
    assert [item["holder_id"] for item in active_scheduler_leases("backtest")] == ["run-1"]

    release_scheduler_lease(first["id"])
    third = acquire_scheduler_lease(
        resource="backtest",
        holder_id="run-2",
        limit=1,
        ttl_seconds=600,
        metadata={"task_id": "task-2"},
    )

    assert third is not None
    assert third["slot_index"] == 0
