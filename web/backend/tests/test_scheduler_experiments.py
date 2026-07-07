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


def test_cancel_task_revokes_optimization_and_child_backtests(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    import app.services.tasks as tasks_module
    import app.tasks.celery_app as celery_module
    from app.db import json_dump
    from app.services.tasks import cancel_task, create_task, task_logs, update_task

    monkeypatch.setattr(tasks_module, "RUNS_DIR", tmp_path / "runs")
    revoked = []
    stopped = []

    def fake_revoke(task_id, terminate=False, signal=None):
        revoked.append({"task_id": task_id, "terminate": terminate, "signal": signal})

    def fake_stop(container_name, output_callback=None):
        stopped.append(container_name)
        if output_callback:
            output_callback(f"docker stop {container_name}: stopped")

    monkeypatch.setattr(celery_module.celery_app.control, "revoke", fake_revoke)
    monkeypatch.setattr(tasks_module.DockerRunner, "stop_container", fake_stop)

    task = create_task(
        "optimization",
        "Optimize SPY",
        {"ticker": "SPY", "parameterGrid": {"fast": [5, 10]}},
        project_id="project-1",
        related_id="optimization-1",
        status="running",
    )
    update_task(task["id"], celery_task_id="celery-1")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into optimization_runs
                (id, task_id, project_id, status, parameters_json, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "optimization-1",
                task["id"],
                "project-1",
                "running",
                json_dump({"parameterGrid": {"fast": [5, 10]}}),
                str(tmp_path / "runs" / "optimization-1"),
                "2026-07-07T00:00:00+00:00",
            ),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, container_name, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "child-run-1",
                task["id"],
                "project-1",
                "SPY",
                "equity",
                "usa",
                "daily",
                "trade",
                json_dump({"ticker": "SPY"}),
                "running",
                "lean:test",
                "lean-child-run-1",
                str(tmp_path / "runs" / "child-run-1" / "results"),
                "2026-07-07T00:01:00+00:00",
            ),
        )

    result = cancel_task(task["id"])

    with db_module.db() as connection:
        optimization = connection.execute("select status, error from optimization_runs where id = ?", ("optimization-1",)).fetchone()
        child = connection.execute("select status, error from backtest_runs where id = ?", ("child-run-1",)).fetchone()

    assert result["status"] == "cancelled"
    assert revoked == [{"task_id": "celery-1", "terminate": True, "signal": "SIGTERM"}]
    assert stopped == ["lean-child-run-1"]
    assert optimization["status"] == "cancelled"
    assert child["status"] == "cancelled"
    assert "Cancellation requested by user." in task_logs(task["id"])
