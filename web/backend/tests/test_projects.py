import json
from pathlib import Path

from fastapi.testclient import TestClient


def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.projects as projects_module

    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    db_module.init_db()
    return db_module


def test_project_files_fallback_from_stale_host_path(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    project_id = "legacy-project"
    fallback = tmp_path / "projects" / project_id
    fallback.mkdir(parents=True)
    (fallback / "main.py").write_text("class LegacyAlgorithm: pass\n", encoding="utf-8")
    (fallback / "project.json").write_text(json.dumps({"mainFile": "main.py"}), encoding="utf-8")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into projects
                (id, name, language, algorithm_class, project_path, main_file, config_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "Legacy Project",
                "Python",
                "LegacyAlgorithm",
                "/Users/example/lean-platform/web/runtime/projects/legacy-project",
                "main.py",
                db_module.json_dump({"mainFile": "main.py"}),
                "2026-07-07T00:00:00+00:00",
                "2026-07-07T00:00:00+00:00",
            ),
        )

    client = TestClient(app)
    project = client.get(f"/api/projects/{project_id}")
    files = client.get(f"/api/projects/{project_id}/files")
    main_file = client.get(f"/api/projects/{project_id}/file", params={"path": "main.py"})

    assert project.status_code == 200
    assert project.json()["project_path"] == str(fallback)
    assert files.status_code == 200
    assert [item["path"] for item in files.json()] == ["main.py", "project.json"]
    assert main_file.status_code == 200
    assert main_file.json()["content"] == "class LegacyAlgorithm: pass\n"


def test_api_update_project_config(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={
            "name": "update-project",
            "language": "Python",
            "templateKey": "ema_cross",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "parameters": {"period": 20},
        },
    ).json()

    response = client.put(f"/api/projects/{created['id']}", json={"name": "update-project-v2", "config": {"symbol": "600460", "source": "tushare"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "update-project-v2"
    assert payload["config"]["symbol"] == "600460"
    assert payload["config"]["source"] == "tushare"
    assert payload["config"]["templateKey"] == "ema_cross"


def test_api_clone_project_with_files(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/projects",
        json={"name": "clone-source", "language": "Python", "templateKey": "ema_cross"},
    ).json()

    source_root = Path(created["project_path"])
    (source_root / "extra.txt").write_text("extra payload\n", encoding="utf-8")

    clone_response = client.post(
        f"/api/projects/{created['id']}/clone",
        json={"name": "clone-source-copy", "config": {"start": "2026-01-01", "symbol": "000001"}},
    )
    assert clone_response.status_code == 200
    cloned = clone_response.json()
    assert cloned["id"] != created["id"]
    assert cloned["name"] == "clone-source-copy"
    assert cloned["config"]["start"] == "2026-01-01"
    assert cloned["config"]["symbol"] == "000001"
    assert cloned["config"]["templateKey"] == "ema_cross"

    files = client.get(f"/api/projects/{cloned['id']}/files").json()
    file_names = {item["path"] for item in files}
    assert "main.py" in file_names
    assert "project.json" in file_names
    assert "extra.txt" in file_names
    assert (Path(cloned["project_path"]) / "project.json").read_text(encoding="utf-8").strip() != ""
