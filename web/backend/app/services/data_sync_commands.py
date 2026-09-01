from __future__ import annotations

from typing import Any

from kombu.exceptions import KombuError

from ..tasks.worker import prepare_ml_data_task, sync_all_data_task
from . import data_sync
from .tasks import create_task, update_task


def _dispatch(signature: Any, task_id: str) -> None:
    try:
        result = signature.apply_async()
    except (KombuError, OSError, ConnectionError):
        update_task(task_id, status="failed", error="RabbitMQ/Celery unavailable")
        raise
    update_task(task_id, celery_task_id=result.id, status="queued")


def create_run(
    *,
    datasets: list[str] | None,
    mode: str,
    scope: dict[str, Any] | None,
) -> dict[str, Any]:
    """Create and dispatch one data-sync command as a single orchestration boundary."""
    run = data_sync.create_sync_run(requested=datasets, mode=mode, request_scope=scope)
    task = create_task(
        "data_sync",
        "Update all TuShare data",
        {"runId": run["id"], "datasets": datasets or []},
        related_id=run["id"],
    )
    data_sync.bind_task(run["id"], task["id"])
    signature = (
        prepare_ml_data_task.s(task["id"], run["id"])
        if mode == "universe_backfill"
        else sync_all_data_task.s(task["id"], run["id"])
    )
    try:
        _dispatch(signature, task["id"])
    except Exception as exc:
        # Run creation and broker publication are one user-visible command. If
        # RabbitMQ rejects publication, leaving the run queued forever makes
        # the Data-page update button permanently disabled.
        data_sync.mark_run_failed(run["id"], f"Task dispatch failed: {exc}")
        raise
    return data_sync.sync_run(run["id"]) or run


def cancel_run(run_id: str) -> dict[str, Any]:
    return data_sync.request_cancel(run_id)


def resume_run(run_id: str) -> dict[str, Any]:
    run = data_sync.prepare_resume(run_id)
    task = create_task("data_sync", "Resume TuShare data update", {"runId": run_id}, related_id=run_id)
    data_sync.bind_task(run_id, task["id"])
    _dispatch(sync_all_data_task.s(task["id"], run_id), task["id"])
    return data_sync.sync_run(run_id) or run
