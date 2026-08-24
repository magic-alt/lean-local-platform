from pathlib import Path
import subprocess

import pytest


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.research_snapshots as snapshots_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(snapshots_module, "RESEARCH_DIR", tmp_path / "research")
    db_module.init_db()


def test_research_execution_interfaces_are_not_exposed(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    assert client.get("/api/research/runs").status_code == 404
    assert client.post("/api/research/runs").status_code == 404
    assert client.post("/api/research/runs/preview").status_code == 404
    assert client.get("/api/research/runs/legacy-api-run").status_code == 404
    assert client.post("/api/research/runs/legacy-api-run/retry").status_code == 404
    assert client.delete("/api/research/runs/legacy-api-run").status_code == 404
    assert client.post("/api/research/runs/legacy-api-run/cancel").status_code == 404
    assert client.post("/api/research/runs/legacy-api-run/backtest").status_code == 404

    assert client.get("/api/research/workspaces").status_code == 404
    assert client.post("/api/research/workspaces", json={"projectId": "project", "snapshotId": "a"*64}).status_code == 404
    assert client.get("/api/research/workspaces/abc").status_code == 404
    assert client.get("/api/research/workspaces/abc/logs").status_code == 404
    assert client.post("/api/research/workspaces/abc/stop").status_code == 404
    assert client.post("/api/research/workspaces/abc/restart").status_code == 404
    assert client.delete("/api/research/workspaces/abc").status_code == 404
    assert client.post("/api/research/workspaces/snapshots", json={"scope": {}}).status_code == 404

    paths = app.openapi()["paths"]
    assert "/api/research/templates" not in paths
    assert "/api/research/runs/{run_id}" not in paths
    assert "/api/research/workspaces/{workspace_id}" not in paths
    assert "/api/research/imports/qlib" in paths
    assert "/api/research/runs/{run_id}/lean-validation" in paths


def test_research_imports_contract_only_accepts_v2_payload():
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app).post(
        "/api/research/imports/qlib",
        json={"schemaVersion": "1.0", "importType": "LEGACY_RESEARCH_BUNDLE", "externalRunId": "legacy", "runKind": "walk_forward"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Only Artifact Contract v2 is supported: schemaVersion=2.0, importType=QLIB_RESEARCH_BUNDLE"
    )


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
