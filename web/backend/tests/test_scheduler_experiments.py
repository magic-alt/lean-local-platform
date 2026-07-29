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


def test_legacy_optimization_task_route_and_table_are_removed(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    import app.tasks.celery_app as celery_module
    routes = celery_module.celery_app.conf.task_routes
    assert "lean_web.optimize" not in routes
    with db_module.db() as connection:
        names = {
            row["name"]
            for row in connection.execute("select name from sqlite_master where type='table'").fetchall()
        }
    assert "optimization_runs" not in names
    assert "experiment_batches" in names


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
