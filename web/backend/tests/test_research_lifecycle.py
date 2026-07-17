from pathlib import Path
import subprocess


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.projects as projects_module
    import app.api.research as research_api

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(research_api, "RESEARCH_DIR", tmp_path / "research")
    db_module.init_db()


def test_research_api_allocates_port_copies_workspace_and_deletes_record(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.api import research as research_api
    from app.main import app
    from app.services.projects import create_project

    project = create_project("Research Unit", market="china")
    monkeypatch.setattr(research_api, "find_available_port", lambda preferred=None: preferred or 8891)
    monkeypatch.setattr(research_api, "dispatch_task", lambda *args, **kwargs: None)
    client = TestClient(app)

    created = client.post("/api/research", json={"projectId": project["id"]})
    assert created.status_code == 200
    session = created.json()
    assert session["status"] == "queued"
    assert session["port"] == 8891
    assert session["project_name"] == "Research Unit"
    assert (Path(session["workspace_path"]) / "main.py").exists()

    logs = client.get(f"/api/research/{session['id']}/logs")
    assert logs.status_code == 200
    deleted = client.delete(f"/api/research/{session['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["workspacePurged"] is False
    assert client.get(f"/api/research/{session['id']}").status_code == 404


def test_research_runner_waits_for_container_port_inside_container(monkeypatch, tmp_path):
    from app.lean_engine import research

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "inspect" in command:
            return subprocess.CompletedProcess(command, 0, "running|true|0\n", "")
        if "exec" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "container-123\n", "")

    monkeypatch.setattr(research.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(research.subprocess, "run", fake_run)
    monkeypatch.setattr(research.secrets, "token_urlsafe", lambda size: "unit-token")

    output = research.run_detached_research("session-1", tmp_path, 8892, lambda line: None)

    assert output["container_id"] == "container-123"
    assert output["readiness_status"] == "ready"
    assert output["url"] == "http://127.0.0.1:8892/?token=unit-token"
    assert any("exec" in command for command in calls)
