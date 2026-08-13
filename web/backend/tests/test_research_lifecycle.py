from pathlib import Path
import subprocess

import pytest


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.projects as projects_module
    import app.services.research_snapshots as snapshots_module
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
    monkeypatch.setattr(snapshots_module, "RESEARCH_DIR", tmp_path / "research")
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

    snapshot_id = "a" * 64
    snapshot_dir = tmp_path / "research" / "snapshots" / snapshot_id
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "manifest.json").write_text("{}", encoding="utf-8")
    created = client.post(
        "/api/research/workspaces",
        json={"projectId": project["id"], "snapshotId": snapshot_id},
    )
    assert created.status_code == 200
    session = created.json()
    assert session["status"] == "queued"
    assert session["port"] == 8891
    assert session["project_name"] == "Research Unit"
    assert (Path(session["workspace_path"]) / "main.py").exists()
    assert (Path(session["workspace_path"]) / ".lean-research-snapshot-id").read_text() == snapshot_id

    logs = client.get(f"/api/research/workspaces/{session['id']}/logs")
    assert logs.status_code == 200
    deleted = client.delete(f"/api/research/workspaces/{session['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["workspacePurged"] is False
    assert client.get(f"/api/research/workspaces/{session['id']}").status_code == 404


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
    run_command = calls[0]
    assert "127.0.0.1:8892:8888" in run_command
    assert "--cap-drop" in run_command
    assert "--network" in run_command
    assert "none" in run_command
    assert "no-new-privileges:true" in run_command
    assert "host.docker.internal:host-gateway" not in run_command
    assert all("/Lean/Launcher/bin/Debug/storage" not in value for value in run_command)


def test_research_run_uses_shared_data_scope_and_old_analysis_routes_are_absent(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.services import market_lake
    from app.main import app

    market_lake.upsert_rows(
        [{"symbol": "000001", "trade_date": "2026-01-05", "open": 10, "high": 11,
          "low": 9, "close": 10.5, "volume": 1000}],
        kind="bars", source="tushare",
    )
    client = TestClient(app)
    scope = {
        "asset": {"assetClass": "equity", "market": "china", "venue": "china", "resolution": "daily", "dataType": "trade"},
        "selection": {"type": "symbols", "values": ["000001.SZ"]},
        "time": {"startDate": "2026-01-01", "endDate": "2026-01-31", "asOfDate": "2026-01-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }

    resolved = client.post("/api/data/resolve", json=scope)
    assert resolved.status_code == 200
    preview = client.post("/api/research/runs/preview", json={"template": "data-quality", "scope": scope, "parameters": {}})
    assert preview.status_code == 200
    assert preview.json()["scopeHash"] == resolved.json()["scopeHash"]
    assert preview.json()["dataFingerprint"] == resolved.json()["dataFingerprint"]

    run = client.post("/api/research/runs", json={"template": "data-quality", "scope": scope, "parameters": {}})
    assert run.status_code == 200
    assert run.json()["status"] == "success"
    assert run.json()["result"]["dataFingerprint"] == resolved.json()["dataFingerprint"]

    snapshot = client.post("/api/research/workspaces/snapshots", json={"scope": scope})
    assert snapshot.status_code == 200
    snapshot_id = snapshot.json()["snapshotId"]
    snapshot_root = tmp_path / "research" / "snapshots" / snapshot_id
    assert (snapshot_root / "manifest.json").is_file()
    assert (snapshot_root / "bars.parquet").is_file()
    assert (snapshot_root / "lean_research.py").is_file()

    paths = app.openapi()["paths"]
    assert "/api/research" not in paths
    assert "/api/factors/evaluate" not in paths
    assert "/api/cbond/double-low" not in paths
    assert "/api/futures/continuous-contracts" not in paths


def test_research_runner_rejects_unpinned_image(monkeypatch, tmp_path):
    from app.lean_engine import research
    from app.lean_engine.errors import LeanPlatformError

    monkeypatch.setattr(research.shutil, "which", lambda name: "/usr/bin/docker")
    with pytest.raises(LeanPlatformError, match="research_image_not_allowed"):
        research.run_detached_research(
            "session-1",
            tmp_path,
            8892,
            lambda line: None,
            image="attacker/research:latest",
        )


def test_research_runner_delegates_container_start_to_restricted_runner(monkeypatch, tmp_path):
    from app.core.config import DEFAULT_RESEARCH_IMAGE
    from app.lean_engine import research

    captured = {}
    output = []

    def fake_remote(method, path, payload=None, **kwargs):
        captured.update(
            {
                "method": method,
                "path": path,
                "payload": payload,
                "timeout": kwargs.get("timeout"),
            }
        )
        return {
            "container_id": "lean-research-session-1",
            "url": "http://127.0.0.1:8892/?token=unit-token",
            "container_status": "running",
            "readiness_status": "ready",
            "output": ["created by restricted runner"],
        }

    monkeypatch.setattr(research, "_runner_url", lambda: "http://lean-runner:8010")
    monkeypatch.setattr(research, "_remote_request", fake_remote)

    result = research.run_detached_research(
        "session-1",
        tmp_path,
        8892,
        output.append,
        image=DEFAULT_RESEARCH_IMAGE,
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/research/start"
    assert captured["payload"]["sessionId"] == "session-1"
    assert captured["payload"]["projectDir"] == str(tmp_path)
    assert result["container_id"] == "lean-research-session-1"
    assert output == ["created by restricted runner"]


def test_research_container_lifecycle_uses_session_scoped_runner_routes(monkeypatch):
    from app.lean_engine import research

    calls = []

    def fake_remote(method, path, payload=None, **_kwargs):
        calls.append((method, path, payload))
        if path.endswith("/logs?tail=80"):
            return {"logs": "jupyter ready"}
        return {"status": "running", "running": True}

    monkeypatch.setattr(research, "_runner_url", lambda: "http://lean-runner:8010")
    monkeypatch.setattr(research, "_remote_request", fake_remote)

    container = "lean-research-session-1"
    assert research.container_state(container)["running"] is True
    assert research.container_logs(container, tail=80) == "jupyter ready"
    research.stop_container(container)
    research.remove_container(container)

    assert calls == [
        ("GET", "/v1/research/session-1", None),
        ("GET", "/v1/research/session-1/logs?tail=80", None),
        ("POST", "/v1/research/session-1/stop", None),
        ("DELETE", "/v1/research/session-1", None),
    ]


def test_compose_routes_api_research_operations_to_socket_owner():
    compose = (Path(__file__).parents[3] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert compose.count("/var/run/docker.sock:/var/run/docker.sock") == 1
    assert "LEAN_RUNNER_URL: http://lean-runner:8010" in compose
    assert "LEAN_HOST_PARQUET_DIR: ${LEAN_HOST_PARQUET_DIR:-${PWD}/data/output/parquet}" in compose
