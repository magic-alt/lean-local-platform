from __future__ import annotations

import pytest

import app.tasks.celery_app as celery_config
from app.repositories import backtest_repository
from app.services import tasks as task_service


@pytest.mark.parametrize(
    ("run_status", "run_error", "expected_error"),
    [
        ("success", None, None),
        ("failed", "engine failed", "engine failed"),
        ("cancelled", None, "Cancellation requested by user."),
    ],
)
def test_terminal_backtest_redelivery_reconciles_task_only_once(
    monkeypatch,
    run_status: str,
    run_error: str | None,
    expected_error: str | None,
):
    task_state = {
        "id": "task-1",
        "status": "running",
        "finished_at": None,
    }
    updates: list[dict[str, object]] = []
    logs: list[str] = []

    monkeypatch.setattr(
        backtest_repository,
        "get_backtest",
        lambda run_id: {
            "id": run_id,
            "status": run_status,
            "error": run_error,
            "finished_at": "2026-09-14T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(task_service, "get_task", lambda task_id: dict(task_state))

    def update_task(task_id: str, **changes):
        assert task_id == "task-1"
        task_state.update(changes)
        updates.append(dict(changes))
        return dict(task_state)

    monkeypatch.setattr(task_service, "update_task", update_task)
    monkeypatch.setattr(
        task_service,
        "append_log",
        lambda task_id, message: logs.append(message),
    )

    first = celery_config._reconcile_terminal_backtest_redelivery(
        ("task-1", "run-1"), {}
    )
    second = celery_config._reconcile_terminal_backtest_redelivery(
        ("task-1", "run-1"), {}
    )

    assert first == {"status": run_status, "run_id": "run-1", "replayed": True}
    assert second == first
    assert updates == [
        {
            "status": run_status,
            "error": expected_error,
            "finished_at": "2026-09-14T00:00:00+00:00",
        }
    ]
    assert len(logs) == 1
    assert "without re-execution" in logs[0]


def test_nonterminal_backtest_is_not_intercepted(monkeypatch):
    monkeypatch.setattr(
        backtest_repository,
        "get_backtest",
        lambda run_id: {"id": run_id, "status": "running"},
    )

    assert (
        celery_config._reconcile_terminal_backtest_redelivery(
            ("task-1", "run-1"), {}
        )
        is None
    )


def test_platform_task_short_circuits_terminal_backtest_before_runner(monkeypatch):
    replay = {"status": "success", "run_id": "run-1", "replayed": True}
    monkeypatch.setattr(
        celery_config,
        "_reconcile_terminal_backtest_redelivery",
        lambda args, kwargs: replay,
    )

    class BacktestTask(celery_config.PlatformTask):
        name = "lean_web.run_backtest"

        def run(self, *args, **kwargs):
            raise AssertionError("terminal broker redelivery must not invoke task.run")

    assert BacktestTask()("task-1", "run-1") == replay


def test_run_backtest_transport_policy_uses_late_ack_and_worker_loss_redelivery():
    annotation = celery_config.celery_app.conf.task_annotations["lean_web.run_backtest"]

    assert annotation["acks_late"] is True
    assert annotation["reject_on_worker_lost"] is True
