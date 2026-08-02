from __future__ import annotations

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    import app.db as db_module
    from app.main import app

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "p2.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "objects")
    db_module.init_db()
    return TestClient(app)


def test_primary_audit_list_endpoints_share_page_envelope(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for path in (
        "/api/data/sync-runs",
        "/api/data/parquet/datasets",
        "/api/data/quality/reports",
        "/api/workflows",
        "/api/verifications",
    ):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        assert set(response.json()) == {"items", "count", "limit", "offset"}, path


def test_primary_page_contract_is_visible_in_openapi():
    from app.main import app

    schema = app.openapi()
    for path in (
        "/api/data/sync-runs",
        "/api/data/parquet/datasets",
        "/api/data/quality/reports",
        "/api/workflows",
        "/api/verifications",
    ):
        response_schema = schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert response_schema["$ref"].endswith("/PageEnvelope"), path


def test_data_sync_pagination_reports_total(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import app.db as db_module

    with db_module.db() as connection:
        for index in range(3):
            connection.execute(
                "insert into data_sync_runs (id,provider,scope,status,mode,created_at) values (?, 'tushare', 'all', 'queued', 'auto', ?)",
                (f"run-{index}", f"2026-08-02T00:00:0{index}Z"),
            )
    payload = client.get("/api/data/sync-runs?limit=1&offset=1").json()
    assert payload["count"] == 3
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1
