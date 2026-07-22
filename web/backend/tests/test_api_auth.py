from fastapi.testclient import TestClient


def test_api_auth_blocks_unauthenticated_business_endpoints(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "API_AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "API_TOKEN", "unit-secret")
    client = TestClient(main.app)

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/dependencies").status_code != 401
    blocked = client.get("/openapi.json")
    assert blocked.status_code == 401
    assert blocked.json()["error_code"] == "UNAUTHORIZED"
    allowed = client.get(
        "/openapi.json",
        headers={"Authorization": "Bearer unit-secret"},
    )
    assert allowed.status_code == 200


def test_api_auth_fails_closed_when_token_is_missing(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "API_AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "API_TOKEN", "")
    response = TestClient(main.app).get("/openapi.json")

    assert response.status_code == 503
    assert response.json()["error_code"] == "API_AUTH_NOT_CONFIGURED"


def test_built_frontend_receives_http_only_same_site_session(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "API_AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "API_TOKEN", "unit-secret")
    client = TestClient(main.app)

    response = client.get("/")
    if response.status_code == 404:
        # Source-only test environments do not necessarily contain a frontend build.
        return
    cookie = response.headers.get("set-cookie", "")
    assert "lean_local_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert client.get("/openapi.json").status_code == 200
