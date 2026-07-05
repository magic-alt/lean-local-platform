from fastapi.testclient import TestClient


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


def test_provider_availability_reports_missing_env_without_network(monkeypatch):
    from app.services.data import provider_availability

    monkeypatch.delenv("ALPHAVANTAGE_API_KEY", raising=False)

    result = provider_availability("alpha_vantage")

    assert result["networkChecked"] is False
    assert result["count"] == 1
    assert result["items"][0]["available"] is False
    assert result["items"][0]["reason"] == "missing_env:ALPHAVANTAGE_API_KEY"


def test_stored_objects_api_supports_namespace_pagination(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.db_object_store import put_bytes

    put_bytes("unit", "a.json", b"a")
    put_bytes("unit", "b.json", b"b")
    put_bytes("unit", "c.json", b"c")
    put_bytes("other", "d.json", b"d")

    response = TestClient(app).get("/api/object-store/_stored-objects", params={"namespace": "unit", "limit": 2, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert len(payload["items"]) == 2
    assert {item["namespace"] for item in payload["items"]} == {"unit"}


def test_reports_api_supports_paged_backtest_and_report_rows(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.db import json_dump
    from app.main import app

    with db_module.db() as connection:
        connection.execute(
            "insert into reports (id, run_id, status, created_at) values (?, ?, ?, ?)",
            ("report-1", "run-a", "success", "2026-07-05T00:00:00+00:00"),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id, symbol, asset_class, venue, resolution, data_type, parameters_json, status,
                 docker_image, results_dir, result_json_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "run-b",
                "600519",
                "equity",
                "china",
                "daily",
                "trade",
                json_dump({}),
                "completed",
                "lean:test",
                str(tmp_path / "run-b"),
                str(tmp_path / "run-b" / "result.json"),
                "2026-07-05T00:01:00+00:00",
            ),
        )

    response = TestClient(app).get("/api/reports", params={"paged": True, "limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1


def test_data_assets_are_retained_and_marked_superseded(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.data import record_data_asset

    first = record_data_asset(
        {
            "symbol": "600519",
            "source": "akshare",
            "rows": 1,
            "first_date": "2026-07-03",
            "last_date": "2026-07-03",
            "lean_file": "equity/china/daily/600519.zip",
            "asset_class": "equity",
            "venue": "china",
            "resolution": "daily",
            "data_type": "trade",
        }
    )
    second = record_data_asset(
        {
            "symbol": "600519",
            "source": "akshare",
            "rows": 5000,
            "first_date": "2005-01-04",
            "last_date": "2026-07-03",
            "lean_file": "equity/china/daily/600519.zip",
            "asset_class": "equity",
            "venue": "china",
            "resolution": "daily",
            "data_type": "trade",
        }
    )

    client = TestClient(app)
    all_assets = client.get("/api/data-assets", params={"paged": True}).json()
    active_assets = client.get("/api/data-assets", params={"includeSuperseded": False, "paged": True}).json()

    assert all_assets["count"] == 2
    old = next(item for item in all_assets["items"] if item["id"] == first["id"])
    new = next(item for item in all_assets["items"] if item["id"] == second["id"])
    assert old["status"] == "superseded"
    assert old["superseded_by"] == second["id"]
    assert new["status"] == "active"
    assert active_assets["count"] == 1
    assert active_assets["items"][0]["id"] == second["id"]
