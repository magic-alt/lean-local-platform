from __future__ import annotations

from urllib.error import URLError

import pytest


def _init_db():
    import app.db as db_module

    db_module.init_db()
    return db_module


def test_alert_webhook_delivery_is_persisted_and_cooled_down(monkeypatch):
    db_module = _init_db()
    from app.services import alerts

    monkeypatch.setenv("LEAN_ALERT_WEBHOOK_URL", "https://alerts.example.test/notify?token=secret")
    monkeypatch.setenv("LEAN_ALERT_MIN_SEVERITY", "warning")
    monkeypatch.setenv("LEAN_ALERT_COOLDOWN_SECONDS", "900")
    sent = []

    def fake_send(url, alert, *, timeout_seconds, bearer_token):
        sent.append((url, alert["id"], timeout_seconds, bearer_token))
        return 202

    monkeypatch.setattr(alerts, "_send_webhook", fake_send)
    first = alerts.emit_alert(
        "paper_schedule_failed",
        severity="warning",
        source="unit",
        related_id="paper-1",
        details={"error": "data waiting"},
        dedupe_key="paper_schedule_failed:paper-1",
    )
    second = alerts.emit_alert(
        "paper_schedule_failed",
        severity="warning",
        source="unit",
        related_id="paper-1",
        details={"error": "data waiting"},
        dedupe_key="paper_schedule_failed:paper-1",
    )

    assert first["delivery"]["status"] == "success"
    assert second["delivery"]["status"] == "cooldown"
    assert len(sent) == 1
    items = alerts.list_alert_events(status="open")
    assert items[0]["count"] == 2
    assert items[0]["deliveries"][0]["status"] == "success"
    assert items[0]["deliveries"][0]["attempt_count"] == 1
    assert items[0]["deliveries"][0]["metadata"]["endpoint"] == "https://alerts.example.test/notify"
    with db_module.db() as connection:
        serialized = connection.execute("select metadata_json from alert_deliveries").fetchone()["metadata_json"]
    assert "secret" not in serialized


def test_outbox_not_delivered_without_channel(monkeypatch):
    _init_db()
    from app.db import db
    from app.services import paper_accounts

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("LEAN_ALERT_ESCALATION_WEBHOOK_URL", raising=False)
    account = paper_accounts.create_account(
        {"name": "Outbox Account", "initialCash": "1000000", "benchmarkSymbol": "000300"}
    )
    with db() as connection:
        paper_accounts._enqueue_notification(
            connection,
            account["id"],
            None,
            None,
            "cycle_failed",
            {"reason": "test"},
        )

    result = paper_accounts.deliver_notifications()
    assert result["delivered"] == []
    assert len(result["failed"]) == 1
    with db() as connection:
        row = connection.execute("select status,last_error from paper_notification_outbox").fetchone()
    assert row["status"] == "failed"
    assert row["last_error"] == "no_channel_configured"


def test_outbox_requires_external_2xx_acknowledgement(monkeypatch):
    _init_db()
    from app.db import db
    from app.services import alerts, paper_accounts

    monkeypatch.setenv("LEAN_ALERT_WEBHOOK_URL", "https://alerts.example.test/notify")
    monkeypatch.setenv("LEAN_ALERT_MIN_SEVERITY", "critical")
    account = paper_accounts.create_account(
        {"name": "Outbox Ack Account", "initialCash": "1000000", "benchmarkSymbol": "000300"}
    )
    with db() as connection:
        paper_accounts._enqueue_notification(
            connection,
            account["id"],
            None,
            None,
            "data_not_ready",
            {"reason": "test"},
        )
    monkeypatch.setattr(alerts, "_send_webhook", lambda *args, **kwargs: 202)

    result = paper_accounts.deliver_notifications()

    assert result["delivered"] == []
    assert len(result["failed"]) == 1
    with db() as connection:
        row = connection.execute("select status,last_error from paper_notification_outbox").fetchone()
    assert row["status"] == "retrying"
    assert "below_threshold" in row["last_error"]


def test_repeated_warning_escalates_and_failed_delivery_is_recorded(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.setenv("LEAN_ALERT_WEBHOOK_URL", "https://alerts.example.test/notify?token=secret-value")
    monkeypatch.setenv("LEAN_ALERT_MIN_SEVERITY", "critical")
    monkeypatch.setenv("LEAN_ALERT_ESCALATE_AFTER", "3")

    def failed_send(url, *args, **kwargs):
        raise URLError(f"endpoint unavailable: {url}")

    monkeypatch.setattr(alerts, "_send_webhook", failed_send)
    first = alerts.emit_alert("paper_schedule_failed", severity="warning", dedupe_key="paper:repeat")
    second = alerts.emit_alert("paper_schedule_failed", severity="warning", dedupe_key="paper:repeat")
    third = alerts.emit_alert("paper_schedule_failed", severity="warning", dedupe_key="paper:repeat")

    assert first["delivery"]["status"] == "below_threshold"
    assert second["delivery"]["status"] == "below_threshold"
    assert third["severity"] == "critical"
    assert third["delivery"]["status"] == "failed"
    assert third["delivery"]["attempt_count"] == 1
    assert "endpoint unavailable" in third["delivery"]["last_error"]
    assert "secret-value" not in third["delivery"]["last_error"]


def test_critical_alert_uses_independent_escalation_channel(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv(
        "LEAN_ALERT_ESCALATION_WEBHOOK_URL",
        "https://on-call.example.test/escalate?secret=hidden",
    )
    monkeypatch.setenv("LEAN_ALERT_ESCALATION_AFTER", "1")
    sent = []

    def fake_send(url, alert, *, timeout_seconds, bearer_token):
        sent.append((url, alert["status"], alert["severity"]))
        return 202

    monkeypatch.setattr(alerts, "_send_webhook", fake_send)
    item = alerts.emit_alert(
        "worker_down",
        severity="critical",
        dedupe_key="worker:escalation",
    )

    assert item["delivery"]["status"] == "disabled"
    assert item["delivery"]["escalation"]["status"] == "success"
    assert sent == [
        (
            "https://on-call.example.test/escalate?secret=hidden",
            "open",
            "critical",
        )
    ]
    deliveries = alerts.list_alert_events(status="open")[0]["deliveries"]
    assert deliveries[0]["channel"] == "escalation_webhook"
    assert "hidden" not in str(deliveries[0]["metadata"])


def test_open_alerts_are_backfilled_after_channel_configuration(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    opened = alerts.emit_alert(
        "worker_down",
        severity="critical",
        dedupe_key="worker:backfill",
    )
    assert opened["delivery"]["status"] == "disabled"
    monkeypatch.setenv("LEAN_ALERT_WEBHOOK_URL", "https://alerts.example.test/notify")
    monkeypatch.setattr(alerts, "_send_webhook", lambda *args, **kwargs: 204)

    result = alerts.redeliver_open_alerts()

    assert result["attempted"] == [opened["id"]]
    assert result["delivered"] == [opened["id"]]
    assert alerts.list_alert_events(status="open")[0]["deliveries"][0]["status"] == "success"


def test_resolution_bypasses_cooldown_and_notifies_operator(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.setenv("LEAN_ALERT_WEBHOOK_URL", "https://alerts.example.test/notify")
    monkeypatch.setenv("LEAN_ALERT_MIN_SEVERITY", "warning")
    sent_statuses = []

    def fake_send(url, alert, *, timeout_seconds, bearer_token):
        sent_statuses.append(alert["status"])
        return 200

    monkeypatch.setattr(alerts, "_send_webhook", fake_send)
    opened = alerts.emit_alert(
        "resource_disk_pressure",
        severity="warning",
        dedupe_key="resource_pressure:disk",
    )
    resolved = alerts.resolve_open_alert("resource_pressure:disk", actor="unit")

    assert opened["delivery"]["status"] == "success"
    assert resolved["status"] == "resolved"
    assert resolved["delivery"]["status"] == "success"
    assert sent_statuses == ["open", "resolved"]


def test_resolved_alert_can_reopen_without_primary_key_collision(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    first = alerts.emit_alert("worker_down", severity="critical", dedupe_key="worker:default")
    resolved = alerts.update_alert_status(first["id"], "resolved", actor="unit")
    reopened = alerts.emit_alert("worker_down", severity="critical", dedupe_key="worker:default")

    assert resolved["status"] == "resolved"
    assert reopened["id"] == first["id"]
    assert reopened["status"] == "open"
    assert reopened["count"] == 2
    assert reopened["resolved_at"] is None


def test_acknowledged_resource_alert_stays_acknowledged_until_recovery(monkeypatch):
    _init_db()
    from app.services import alerts

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    first = alerts.emit_alert(
        "resource_memory_pressure",
        severity="warning",
        dedupe_key="resource_pressure:memory",
    )
    acknowledged = alerts.update_alert_status(first["id"], "acknowledged", actor="unit")
    repeated = alerts.emit_alert(
        "resource_memory_pressure",
        severity="warning",
        dedupe_key="resource_pressure:memory",
    )
    resolved = alerts.resolve_open_alert("resource_pressure:memory", actor="monitor")

    assert acknowledged["status"] == "acknowledged"
    assert repeated["status"] == "acknowledged"
    assert repeated["count"] == 2
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "monitor"


def test_resource_pressure_monitor_alerts_escalates_and_resolves(monkeypatch):
    _init_db()
    from app.services import alerts, resource_pressure

    monkeypatch.delenv("LEAN_ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("LEAN_ALERT_ESCALATE_AFTER", "2")
    monkeypatch.setenv("LEAN_RESOURCE_DISK_WARNING", "70")
    monkeypatch.setenv("LEAN_RESOURCE_DISK_CRITICAL", "90")
    pressured = {
        "disk": {"usedPercent": 80.0, "mounts": []},
        "memory": {"usedPercent": 50.0},
        "cpu": {"usedPercent": 10.0},
        "queue": {"maxDepth": 0},
    }

    first = resource_pressure.monitor_operational_resources(pressured)
    second = resource_pressure.monitor_operational_resources(pressured)
    healthy = resource_pressure.monitor_operational_resources(
        {
            "disk": {"usedPercent": 20.0, "mounts": []},
            "memory": {"usedPercent": 50.0},
            "cpu": {"usedPercent": 10.0},
            "queue": {"maxDepth": 0},
        }
    )

    assert first["changes"][0]["severity"] == "warning"
    assert second["changes"][0]["severity"] == "critical"
    assert healthy["changes"] == [
        {
            "kind": "disk",
            "action": "resolved",
            "alertId": first["changes"][0]["alertId"],
        }
    ]
    assert alerts.list_alert_events(status="open") == []
    assert alerts.list_alert_events(status="resolved")[0]["event_type"] == "resource_disk_pressure"


def test_paper_walkforward_failure_emits_critical_alert(monkeypatch):
    from app.tasks import worker

    captured = []
    monkeypatch.setattr(
        worker.paper_service,
        "fail_walkforward_run",
        lambda paper_run_id, error: {
            "id": paper_run_id,
            "session_id": "paper-session",
            "trade_date": "2026-07-22",
        },
    )
    monkeypatch.setattr(worker.paper_scheduler, "job_for_date", lambda session_id, trade_date: None)
    monkeypatch.setattr(worker, "emit_alert", lambda event_type, **kwargs: captured.append((event_type, kwargs)))

    result = worker.fail_paper_walkforward_task(None, RuntimeError("LEAN exited 1"), None, "paper-run")

    assert result["id"] == "paper-run"
    assert captured[0][0] == "paper_walkforward_failed"
    assert captured[0][1]["severity"] == "critical"
    assert captured[0][1]["details"]["sessionId"] == "paper-session"


def test_paper_scheduler_failure_records_warning_and_operational_alert(monkeypatch):
    from app.tasks import worker

    warnings = []
    captured = []
    monkeypatch.setattr(
        worker.paper_service,
        "list_sessions",
        lambda: [
            {
                "id": "paper-session",
                "mode": "lean_walkforward",
                "status": "running",
                "auto_advance": True,
                "start_date": "2026-07-01",
                "last_processed_date": None,
            }
        ],
    )
    monkeypatch.setattr(worker.paper_scheduler, "recover_orphaned_jobs", lambda: [])
    monkeypatch.setattr(
        worker.paper_scheduler,
        "ensure_job",
        lambda session_id, trade_date: {
            "id": "daily-job",
            "state": "SCHEDULED",
            "attempt": 0,
            "max_attempts": 3,
        },
    )
    monkeypatch.setattr(
        worker.paper_scheduler,
        "transition_job",
        lambda job_id, state, **kwargs: {
            "id": job_id,
            "state": state,
            "attempt": 0,
            "max_attempts": 3,
        },
    )
    monkeypatch.setattr(worker.paper_service, "list_walkforward_runs", lambda session_id: [])
    monkeypatch.setattr(
        worker.paper_service,
        "create_walkforward_run",
        lambda session_id, trade_date: (_ for _ in ()).throw(ValueError("certified data not ready")),
    )
    monkeypatch.setattr(
        worker.paper_service,
        "record_session_warning",
        lambda session_id, code, message: warnings.append((session_id, code, message)),
    )
    monkeypatch.setattr(worker, "_emit_operational_alert", lambda event_type, **kwargs: captured.append((event_type, kwargs)))
    monkeypatch.setattr(
        worker.schedule_paper_walkforward_task,
        "retry",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("retry requested")),
    )

    with pytest.raises(RuntimeError, match="retry requested"):
        worker.schedule_paper_walkforward_task.run()

    assert warnings[0][1] == "paper_schedule_waiting"
    assert captured[0][0] == "paper_schedule_failed"
    assert captured[0][1]["severity"] == "warning"
    assert captured[0][1]["dedupe_key"] == "paper_schedule_failed:paper-session"


def test_paper_scheduler_advances_from_last_processed_date_with_market_calendar(monkeypatch):
    from app.tasks import worker

    captured_dates = []
    monkeypatch.setattr(
        worker.paper_service,
        "list_sessions",
        lambda: [
            {
                "id": "paper-session",
                "mode": "lean_walkforward_v2",
                "status": "running",
                "auto_advance": True,
                "venue": "china",
                "start_date": "2026-07-01",
                "last_processed_date": "2026-07-22",
            }
        ],
    )
    monkeypatch.setattr(worker.paper_scheduler, "recover_orphaned_jobs", lambda: [])
    monkeypatch.setattr(
        worker,
        "next_trade_date",
        lambda market, trade_date: (
            captured_dates.append((market, trade_date)) or "2099-01-01"
        ),
    )

    result = worker.schedule_paper_walkforward_task.run()

    assert result == {"scheduled": [], "recovered": []}
    assert captured_dates == [("china", "2026-07-22")]
