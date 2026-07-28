from pathlib import Path

from fastapi.testclient import TestClient


def _init_temp_db(tmp_path, monkeypatch):
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


def test_paged_list_contract_retains_bounded_legacy_mode():
    from app.api.common import paged_items

    items = [{"id": index} for index in range(5)]
    assert paged_items(items, limit=2, offset=1) == [{"id": 1}, {"id": 2}]
    assert paged_items(items, limit=2, offset=1, paged=True) == {
        "items": [{"id": 1}, {"id": 2}],
        "count": 5,
        "limit": 2,
        "offset": 1,
    }


def test_task_logs_support_offset_and_cursor(tmp_path):
    from app.services.tasks import log_window

    path = tmp_path / "task.log"
    path.write_text("0123456789", encoding="utf-8")
    first = log_window(path, offset=2, limit=4)
    assert first == {
        "logs": "2345",
        "offset": 2,
        "nextOffset": 6,
        "cursor": "2",
        "nextCursor": "6",
        "limit": 4,
        "total": 10,
        "hasMore": True,
    }
    assert log_window(path, cursor=first["nextCursor"], limit=4)["logs"] == "6789"


def test_api_idempotency_replays_and_rejects_payload_drift(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    from app.main import app

    client = TestClient(app)
    headers = {"Idempotency-Key": "settings-unit-1"}
    first = client.put("/api/settings", json={"jobTimeoutSeconds": 60}, headers=headers)
    replay = client.put("/api/settings", json={"jobTimeoutSeconds": 60}, headers=headers)
    conflict = client.put("/api/settings", json={"jobTimeoutSeconds": 61}, headers=headers)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "IDEMPOTENCY_KEY_CONFLICT"
    assert conflict.json()["field"] == "Idempotency-Key"


def test_structured_http_error_lifts_field_and_retryable(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    from app.main import app

    response = TestClient(app).get("/api/tasks/missing/logs", params={"cursor": "bad"})
    assert response.status_code == 404

    from app.core.errors import error_payload

    payload = error_payload(
        "invalid cursor",
        error_code="BAD_REQUEST",
        category="validation",
        retryable=True,
        details={"field": "cursor", "retryable": False},
    )
    assert payload["retryable"] is True
    assert payload["field"] == "cursor"
    assert "retryable" not in payload["details"]


def test_trace_context_is_written_into_lean_config_and_manifest(tmp_path):
    from app.core.request_context import reset_request_context, set_request_context
    from app.runners.lean_runner import LeanRunner

    project = tmp_path / "project"
    project.mkdir()
    algorithm = project / "main.py"
    algorithm.write_text("class Main: pass\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    tokens = set_request_context("trace-p1", "workflow-p1")
    try:
        workspace = LeanRunner().prepare(
            "run-p1",
            {"ticker": "SPY"},
            run_dir,
            algorithm_path=algorithm,
            algorithm_class="Main",
            language="Python",
            project_dir=project,
        )
        config = workspace.config_path.read_text(encoding="utf-8")
        trace_context = (run_dir / "trace-context.json").read_text(encoding="utf-8")
        assert '"lean-platform-trace-id": "trace-p1"' in config
        assert '"traceId": "trace-p1"' in trace_context
    finally:
        reset_request_context(tokens)


def test_celery_headers_propagate_trace_context():
    from types import SimpleNamespace

    from app.core.request_context import (
        current_trace_id,
        current_workflow_id,
        reset_request_context,
        set_request_context,
    )
    from app.tasks import celery_app as celery_context

    tokens = set_request_context("trace-api", "workflow-api")
    headers = {}
    try:
        celery_context.attach_request_context(headers=headers)
    finally:
        reset_request_context(tokens)
    assert headers == {
        "x-trace-id": "trace-api",
        "x-workflow-id": "workflow-api",
    }

    task = SimpleNamespace(request=SimpleNamespace(headers=headers))
    celery_context.restore_request_context(task_id="task-p1", task=task)
    assert current_trace_id() == "trace-api"
    assert current_workflow_id() == "workflow-api"
    celery_context.clear_request_context(task_id="task-p1")
    assert current_trace_id() is None


def test_paper_risk_limits_reject_capacity_industry_and_drawdown(monkeypatch):
    from app.services import paper

    base = {
        "id": "paper-p1",
        "venue": "china",
        "initial_cash": 100000,
        "cash": 70000,
        "equity": 80000,
        "parameters": {},
    }
    monkeypatch.setattr(paper, "list_positions", lambda _session_id: [])
    monkeypatch.setattr(paper, "_security_industry", lambda _symbol, _market: "Food")

    capacity = {
        **base,
        "parameters": {"maxVolumeParticipation": 0.1},
    }
    assert paper._projected_risk_rejection(
        capacity,
        symbol="600519",
        incremental_quantity=200,
        price=10,
        bar={"volume": 1000},
    ) == "capacity_limit"

    industry = {
        **base,
        "parameters": {"maxIndustryWeight": 0.2},
    }
    assert paper._projected_risk_rejection(
        industry,
        symbol="600519",
        incremental_quantity=2000,
        price=10,
        bar={"volume": 100000},
    ) == "industry_concentration"

    circuit = {
        **base,
        "parameters": {"circuitBreakerDrawdown": 0.2},
    }
    assert paper._portfolio_constraint_rejection(
        circuit,
        {"symbol": "600519"},
        "buy",
        "2026-07-24",
        0,
    ) == "circuit_breaker"


def test_retired_paper_session_api_rejects_same_close_requests(tmp_path, monkeypatch):
    _init_temp_db(tmp_path, monkeypatch)
    from app.main import app

    response = TestClient(app).post(
        "/api/paper",
        json={
            "symbol": "600519",
            "market": "china",
            "executionPolicy": "same_close",
        },
    )
    assert response.status_code == 405


def test_every_migration_declares_rollback_policy():
    import json

    versions = Path(__file__).parents[1] / "app" / "migrations" / "versions"
    migrations = sorted(versions.glob("*.sql"))
    policy_path = versions.parent / "rollback_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))["revisions"]
    assert migrations
    assert set(policy) == {path.stem for path in migrations}
    assert all(item["mode"] in {"compensating", "irreversible"} for item in policy.values())
    assert all(str(item["action"]).strip() for item in policy.values())


def test_paper_accounts_use_shared_trading_calendar():
    source = (
        Path(__file__).parents[1] / "app" / "services" / "paper_accounts.py"
    ).read_text(encoding="utf-8")
    assert "legacy_paper._next_trade_date" not in source
    assert "from .trading_calendar import next_trade_date" in source


def test_compose_workers_hide_runtime_secrets_and_mount_workspace_read_only():
    compose = (Path(__file__).parents[3] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "LEAN_RUNNER_TOKEN_FILE: /run/secrets/lean_runner_token" in compose
    assert "LEAN_API_TOKEN_FILE: /run/secrets/lean_api_token" in compose
    assert "- .:/workspace:ro" in compose
    assert "/workspace/web/runtime/secrets:rw,noexec,nosuid,size=1m,mode=0700" in compose


def test_compose_beat_uses_a_writable_scheduler_file():
    compose = (Path(__file__).parents[3] / "docker-compose.yml").read_text(encoding="utf-8")

    assert "--schedule=/tmp/celerybeat-schedule" in compose
    assert "/tmp:rw,noexec,nosuid,size=64m" in compose


def test_restore_script_verifies_rows_and_checksums():
    restore = (Path(__file__).parents[3] / "scripts" / "restore_mysql.sh").read_text(
        encoding="utf-8"
    )
    assert "SELECT COUNT(*) FROM \\`${SOURCE_DATABASE}\\`.\\`${table_name}\\`" in restore
    assert "CHECKSUM TABLE \\`${SOURCE_DATABASE}\\`.\\`${table_name}\\`" in restore
    assert "verification_failures" in restore
