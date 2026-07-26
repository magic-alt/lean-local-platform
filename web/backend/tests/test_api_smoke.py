from fastapi.testclient import TestClient


def test_backtest_create_requires_project_id(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    db_module.init_db()

    payload = {
        "symbol": "SPY",
        "start": "2024-01-01",
        "end": "2024-01-31",
        "cash": 100000,
    }
    response = TestClient(app).post("/api/backtests", json=payload)

    assert response.status_code == 422
    assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_backtest_create_rejects_unknown_project(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    db_module.init_db()

    payload = {
        "symbol": "SPY",
        "start": "2024-01-01",
        "end": "2024-01-31",
        "cash": 100000,
        "projectId": "missing-project",
    }
    response = TestClient(app).post("/api/backtests", json=payload)

    assert response.status_code == 404
    assert response.json()["error_code"] == "NOT_FOUND"


def test_backtests_empty_list_with_temp_db(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()

    client = TestClient(app)
    response = client.get("/api/backtests")

    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0, "limit": 100, "offset": 0}


def test_api_errors_include_structured_code(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()

    response = TestClient(app).get("/api/tasks/missing-task")

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"] == "Task not found."
    assert payload["message"] == "Task not found."
    assert payload["error_code"] == "NOT_FOUND"
    assert payload["category"] == "not_found"
    assert payload["retryable"] is False
    assert payload["trace_id"] == response.headers["X-Trace-ID"]
    assert payload["workflow_id"] == response.headers["X-Workflow-ID"]

    workflow = TestClient(app).get(f"/api/workflows/{payload['workflow_id']}")
    assert workflow.status_code == 200
    assert workflow.json()["events"][0]["error_code"] == "HTTP_404"


def test_data_provider_failures_preserve_attempt_evidence(tmp_path, monkeypatch):
    import app.api.data as data_api
    import app.db as db_module
    from app.main import app
    from app.services.data_provider_manager import ProviderExhaustedError

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    db_module.init_db()
    monkeypatch.setattr(
        data_api,
        "fetch_and_import_symbol",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ProviderExhaustedError(
                [{"source": "tushare", "status": "failed", "rows": 0, "error": "访问频率超限"}]
            )
        ),
    )

    response = TestClient(app).post(
        "/api/data/fetch",
        json={"symbol": "00700", "market": "hongkong", "provider": "tushare"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["error_code"] == "PROVIDER_EXHAUSTED"
    assert payload["category"] == "data_provider"
    assert payload["retryable"] is True
    assert payload["details"]["attempts"][0]["error"] == "访问频率超限"


def test_api_delete_task_accepts_trailing_slash(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app
    from app.services.tasks import create_task

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    client = TestClient(app)
    task = create_task("data_fetch", "Trailing slash delete", {"symbols": ["000001"]}, status="success")
    response = client.delete(f"/api/tasks/{task['id']}/")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": task["id"]}


def test_api_delete_task_accepts_no_trailing_slash(tmp_path, monkeypatch):
    import app.db as db_module
    from app.main import app
    from app.services.tasks import create_task

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    client = TestClient(app)
    task = create_task("data_fetch", "No trailing slash delete", {"symbols": ["000001"]}, status="success")
    response = client.delete(f"/api/tasks/{task['id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": task["id"]}
