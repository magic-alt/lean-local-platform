from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/research/templates"),
        ("GET", "/api/research/runs"),
        ("POST", "/api/research/runs"),
        ("POST", "/api/research/runs/preview"),
        ("GET", "/api/research/runs/example-run"),
        ("DELETE", "/api/research/runs/example-run"),
        ("POST", "/api/research/runs/example-run/cancel"),
        ("POST", "/api/research/runs/example-run/retry"),
        ("GET", "/api/research/runs/example-run/backtest-draft"),
        ("GET", "/api/research/runs/example-run/export.csv"),
        ("GET", "/api/research/runs/example-run/artifacts/report"),
        ("GET", "/api/research/workspaces"),
        ("POST", "/api/research/workspaces"),
        ("POST", "/api/research/workspaces/snapshots"),
        ("GET", "/api/research/workspaces/example-workspace"),
        ("POST", "/api/research/workspaces/example-workspace/restart"),
        ("DELETE", "/api/research/workspaces/example-workspace"),
    ],
)
def test_retired_research_execution_routes_are_stable_404(method: str, path: str):
    response = TestClient(app).request(method, path, json={} if method in {"POST", "PUT", "PATCH"} else None)

    assert response.status_code == 404
    assert "qlib-platform" in response.json()["detail"]


def test_artifact_contract_import_route_remains_active():
    response = TestClient(app).post(
        "/api/research/imports/qlib",
        json={"schemaVersion": "invalid", "importType": "invalid"},
    )

    assert response.status_code == 409
    assert "Artifact Contract v2" in response.json()["detail"]
