from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


def _init() -> None:
    from app.db import init_db

    init_db()


def _account(name: str) -> dict:
    from app.services.paper_accounts import create_account

    return create_account(
        {
            "name": name,
            "initialCash": "1000000",
            "benchmarkSymbol": "000300",
            "riskConfig": {"maxPositions": 10, "maxPositionWeight": "0.2"},
        }
    )


def _deployment(account_id: str, tmp_path: Path, monkeypatch) -> dict:
    from app.services import paper_accounts

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "main.py").write_text("class Algorithm: pass", encoding="utf-8")
    monkeypatch.setattr(
        paper_accounts,
        "_candidate",
        lambda *_args: {
            "candidate": {
                "id": "trusted-backtest",
                "name": "Frozen Strategy",
                "symbol": "600519",
                "strategyVersionId": "strategy-v1",
                "parameterHash": "parameter-hash",
            },
            "run": {
                "id": "trusted-backtest",
                "symbol": "600519",
                "parameters": {},
                "fingerprint": {},
            },
            "parameters": {
                "ticker": "600519",
                "start": "2024-01-01",
                "end": "2024-01-31",
                "cash": 1000000,
                "strategySnapshotDir": str(snapshot),
                "strategySnapshotHash": "strategy-sha",
                "dataType": "trade",
            },
            "fingerprint": {"datasetCertification": {"id": "dataset-v1", "isCertified": True}},
            "certification": {"id": "dataset-v1", "isCertified": True},
            "versions": {"experiment": {"id": "experiment-v1"}},
            "snapshotDir": str(snapshot),
        },
    )
    return paper_accounts.create_deployment(
        account_id,
        {
            "name": "Frozen Strategy",
            "projectId": "project-1",
            "sourceBacktestId": "trusted-backtest",
            "signalMode": "paper_execute",
            "isPrimary": True,
        },
    )


def _queued_cycle(tmp_path: Path, monkeypatch) -> dict:
    from app.services import paper_accounts

    account = _account("dispatch recovery")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2026-09-14")
    return paper_accounts.transition_cycle(
        cycle["id"],
        "queued",
        event_type="test_queued",
        expected={"scheduled"},
    )


def test_duplicate_broker_delivery_claims_cycle_once(tmp_path, monkeypatch):
    _init()
    from app.db import db
    from app.services import paper_cycle_dispatch

    cycle = _queued_cycle(tmp_path, monkeypatch)
    calls: list[str] = []

    def begin(cycle_id: str) -> dict:
        calls.append(cycle_id)
        return {
            "id": cycle_id,
            "status": "running",
            "paperRun": {"id": "paper-run-1", "task_id": "task-1", "backtest_run_id": "backtest-1"},
        }

    first = paper_cycle_dispatch.guarded_begin_cycle(cycle["id"], begin=begin)
    duplicate = paper_cycle_dispatch.guarded_begin_cycle(cycle["id"], begin=begin)

    assert first["workerClaimed"] is True
    assert duplicate["duplicateDelivery"] is True
    assert duplicate["idempotent"] is True
    assert duplicate["status"] == "skipped"
    assert duplicate["actualStatus"] == "running"
    assert calls == [cycle["id"]]
    with db() as connection:
        row = connection.execute(
            "select status,attempt from paper_execution_cycles where id=?",
            (cycle["id"],),
        ).fetchone()
        events = connection.execute(
            "select event_type from paper_execution_cycle_events where cycle_id=? order by sequence",
            (cycle["id"],),
        ).fetchall()
    assert row["status"] == "running"
    assert int(row["attempt"]) == 1
    assert [item["event_type"] for item in events].count("worker_dispatch_claimed") == 1


def test_publish_failure_keeps_queued_intent_recoverable(tmp_path, monkeypatch):
    _init()
    from app.db import db
    from app.services import paper_cycle_dispatch

    cycle = _queued_cycle(tmp_path, monkeypatch)
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with db() as connection:
        connection.execute(
            "update paper_execution_cycles set updated_at=? where id=?",
            (stale, cycle["id"]),
        )

    def fail_publish(_cycle_id: str):
        raise RuntimeError("rabbitmq unavailable")

    failed = paper_cycle_dispatch.recover_stale_queued_dispatches(
        fail_publish,
        stale_seconds=0,
    )
    assert failed == {"published": [], "failed": [cycle["id"]]}
    with db() as connection:
        row = connection.execute(
            "select status from paper_execution_cycles where id=?",
            (cycle["id"],),
        ).fetchone()
    assert row["status"] == "queued"

    published_ids: list[str] = []
    recovered = paper_cycle_dispatch.recover_stale_queued_dispatches(
        published_ids.append,
        stale_seconds=0,
    )
    assert recovered == {"published": [cycle["id"]], "failed": []}
    assert published_ids == [cycle["id"]]
    with db() as connection:
        row = connection.execute(
            "select status from paper_execution_cycles where id=?",
            (cycle["id"],),
        ).fetchone()
        events = connection.execute(
            "select event_type from paper_execution_cycle_events where cycle_id=? order by sequence",
            (cycle["id"],),
        ).fetchall()
    assert row["status"] == "queued"
    event_types = [item["event_type"] for item in events]
    assert "dispatch_recovery_publish_failed" in event_types
    assert "dispatch_recovery_published" in event_types


def test_celery_has_periodic_dispatch_recovery_gate():
    from app.tasks.celery_app import celery_app

    assert celery_app.conf.task_routes["lean_web.recover_stale_paper_cycle_dispatches"]["queue"] == "default"
    schedule = celery_app.conf.beat_schedule["recover-stale-paper-cycle-dispatches"]
    assert schedule["task"] == "lean_web.recover_stale_paper_cycle_dispatches"
