from fastapi.testclient import TestClient


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
    assert response.json() == []


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
