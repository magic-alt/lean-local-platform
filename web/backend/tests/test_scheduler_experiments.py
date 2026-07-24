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


def test_scheduler_lease_reclaims_terminal_backtest_holder(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services.scheduler import acquire_scheduler_lease, active_scheduler_leases

    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id,task_id,name,symbol,asset_class,venue,resolution,data_type,parameters_json,
                 status,docker_image,container_name,work_dir,results_dir,log_path,created_at)
            values ('orphaned-run','orphaned-task','orphaned','600519','equity','china','daily',
                    'trade','{}','running','lean:test','lean-orphaned','/tmp/run','/tmp/results',
                    '/tmp/log',?)
            """,
            (db_module.utc_now(),),
        )

    first = acquire_scheduler_lease(
        resource="backtest", holder_id="orphaned-run", limit=1, ttl_seconds=7200
    )
    assert first is not None
    with db_module.db() as connection:
        connection.execute("update backtest_runs set status='failed' where id='orphaned-run'")

    replacement = acquire_scheduler_lease(
        resource="backtest", holder_id="replacement-run", limit=1, ttl_seconds=7200
    )
    assert replacement is not None
    assert [item["holder_id"] for item in active_scheduler_leases("backtest")] == ["replacement-run"]


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


def test_delete_task_removes_terminal_task_and_log(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    import app.services.tasks as tasks_module
    from app.services.tasks import create_task, delete_task, get_task

    monkeypatch.setattr(tasks_module, "RUNS_DIR", tmp_path / "runs")
    task = create_task("data_fetch", "Fetch data", {"symbols": ["000001"]}, status="success")
    log_path = tmp_path / "runs" / "task-logs" / f"{task['id']}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("done\n", encoding="utf-8")

    result = delete_task(task["id"])

    assert result == {"deleted": True, "id": task["id"]}
    assert not log_path.exists()
    with db_module.db() as connection:
        assert connection.execute("select count(*) as count from tasks where id = ?", (task["id"],)).fetchone()["count"] == 0
    try:
        get_task(task["id"])
    except KeyError:
        pass
    else:
        raise AssertionError("deleted task should not be loadable")


def test_paper_daily_job_is_unique_and_completion_marker_is_idempotent(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.services import paper_scheduler

    first = paper_scheduler.ensure_job("session-1", "2026-07-22")
    duplicate = paper_scheduler.ensure_job("session-1", "2026-07-22")
    assert duplicate["id"] == first["id"]

    ready = paper_scheduler.transition_job(
        first["id"],
        "READY",
        event_type="readiness_passed",
        expected_states={"SCHEDULED"},
    )
    running = paper_scheduler.transition_job(
        first["id"],
        "RUNNING",
        event_type="workflow_queued",
        expected_states={"READY"},
        paper_run_id="paper-run-1",
    )
    completed = paper_scheduler.transition_job(
        first["id"],
        "COMPLETED",
        event_type="paper_run_completed",
        expected_states={"RUNNING"},
    )
    replay = paper_scheduler.transition_job(
        first["id"],
        "COMPLETED",
        event_type="duplicate_completion",
        expected_states={"RUNNING", "COMPLETED"},
    )

    assert ready["state"] == "READY"
    assert running["attempt"] == 1
    assert completed["completion_marker"] == "session-1:2026-07-22:complete"
    assert replay["version"] == completed["version"]


def test_paper_daily_job_blocks_illegal_skip_over_running(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.services import paper_scheduler

    job = paper_scheduler.ensure_job("session-1", "2026-07-22")
    try:
        paper_scheduler.transition_job(
            job["id"],
            "COMPLETED",
            event_type="illegal_skip",
        )
    except ValueError as exc:
        assert "SCHEDULED -> COMPLETED" in str(exc)
    else:
        raise AssertionError("daily job must not complete without readiness and running")
