from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _init_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    return db_module


def _insert_stale_task(db_module, task_id: str, created_at: str):
    with db_module.db() as connection:
        connection.execute(
            """
            insert into tasks
                (id, celery_task_id, kind, status, title, project_id, related_id, parameters_json,
                 log_path, artifacts_json, error, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                None,
                "backtest",
                "queued",
                f"Task {task_id}",
                None,
                None,
                db_module.json_dump({"symbol": "000001"}),
                str(db_module.RUNS_DIR / f"{task_id}.log"),
                "[]",
                None,
                created_at,
            ),
        )


def _insert_stale_run(db_module, run_id: str, queued_at: str):
    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, container_name, work_dir, results_dir, log_path, created_at, queued_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                None,
                None,
                "000001",
                "equity",
                "usa",
                "daily",
                "trade",
                db_module.json_dump({"symbol": "000001"}),
                "queued",
                "quantconnect/lean:latest",
                None,
                str(db_module.RUNS_DIR / run_id),
                str(db_module.RUNS_DIR / run_id / "results"),
                str(db_module.RUNS_DIR / run_id / "run.log"),
                queued_at,
                queued_at,
            ),
        )


def test_cleanup_stale_queued_marks_old_records(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.services.maintenance import cleanup_stale_queued

    now = datetime.now(timezone.utc)
    stale = (now - timedelta(minutes=30)).isoformat()
    fresh = (now - timedelta(minutes=5)).isoformat()

    _insert_stale_task(db_module, "queued-task-old", stale)
    _insert_stale_task(db_module, "queued-task-fresh", fresh)
    _insert_stale_run(db_module, "queued-run-old", stale)
    _insert_stale_run(db_module, "queued-run-fresh", fresh)

    result = cleanup_stale_queued(max_queued_minutes=15)

    assert result["tasksMarked"] == 1
    assert result["backtestRunsMarked"] == 1

    with db_module.db() as connection:
        task_old = connection.execute("select status, error from tasks where id = ?", ("queued-task-old",)).fetchone()
        task_fresh = connection.execute("select status, error from tasks where id = ?", ("queued-task-fresh",)).fetchone()
        run_old = connection.execute("select status, error from backtest_runs where id = ?", ("queued-run-old",)).fetchone()
        run_fresh = connection.execute("select status, error from backtest_runs where id = ?", ("queued-run-fresh",)).fetchone()

    assert task_old["status"] == "failed"
    assert task_old["error"] is not None
    assert task_fresh["status"] == "queued"
    assert task_fresh["error"] is None
    assert run_old["status"] == "failed"
    assert run_old["error"] is not None
    assert run_fresh["status"] == "queued"


def test_cleanup_stale_queued_dry_run_does_not_mark(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.services.maintenance import cleanup_stale_queued

    stale = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()

    _insert_stale_task(db_module, "queued-task-dry", stale)
    _insert_stale_run(db_module, "queued-run-dry", stale)

    result = cleanup_stale_queued(max_queued_minutes=15, dry_run=True)

    assert result["tasksMarked"] == 1
    assert result["backtestRunsMarked"] == 1

    with db_module.db() as connection:
        task_row = connection.execute("select status from tasks where id = ?", ("queued-task-dry",)).fetchone()
        run_row = connection.execute("select status from backtest_runs where id = ?", ("queued-run-dry",)).fetchone()
    assert task_row["status"] == "queued"
    assert run_row["status"] == "queued"


def test_cleanup_stale_queued_route(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.main import app

    stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    _insert_stale_task(db_module, "queued-task-endpoint", stale)
    _insert_stale_run(db_module, "queued-run-endpoint", stale)

    response = TestClient(app).post("/api/maintenance/cleanup-queued", json={"maxQueuedMinutes": 15, "dryRun": False})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tasksMarked"] == 1
    assert payload["backtestRunsMarked"] == 1

    response_invalid = TestClient(app).post("/api/maintenance/cleanup-queued", json={"maxQueuedMinutes": 0})
    assert response_invalid.status_code == 400
