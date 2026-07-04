from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..db import db, json_dump, utc_now
from ..domain.backtest_job import CANCELLED, CREATED, FAILED, is_terminal
from ..lean import LeanPlatformError, new_run_id, validate_backtest_parameters
from ..repositories.backtest_repository import get_backtest, list_backtests, update_backtest
from ..runners.docker_runner import DockerRunner
from .projects import get_project
from .tasks import append_log, create_task, get_task, update_task


def create_backtest_job(request_data: dict[str, Any]) -> dict[str, Any]:
    template_parameters = dict(request_data.get("parameters") or {})
    if request_data.get("fast") is not None:
        template_parameters["fast"] = request_data["fast"]
    if request_data.get("slow") is not None:
        template_parameters["slow"] = request_data["slow"]
    for key, value in request_data.get("extra", {}).items():
        if key not in template_parameters:
            template_parameters[key] = value

    parameters = validate_backtest_parameters(
        {
            "ticker": request_data["symbol"],
            "assetClass": request_data.get("assetClass", "equity"),
            "market": request_data.get("market", "usa"),
            "venue": request_data.get("venue"),
            "resolution": request_data.get("resolution", "daily"),
            "dataType": request_data.get("dataType", "trade"),
            "start": request_data["start"],
            "end": request_data["end"],
            "cash": request_data.get("cash", 100000),
            **template_parameters,
        }
    )
    project_id = request_data.get("projectId")
    if project_id:
        project = get_project(project_id)
        if project["language"] != "Python":
            raise LeanPlatformError("CSharp project execution is not enabled in this local web version yet.")

    docker_image = request_data.get("dockerImage") or DEFAULT_DOCKER_IMAGE
    parameters["dockerImage"] = docker_image
    run_id = new_run_id(parameters["ticker"], parameters["start"], parameters["end"])
    task = create_task("backtest", f"Backtest {parameters['ticker']}", parameters, project_id, run_id, status=CREATED)
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    name = request_data.get("name") or f"{parameters['ticker']} {parameters['start']} -> {parameters['end']}"
    with db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, name, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, container_name, work_dir, results_dir, log_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task["id"],
                project_id,
                name,
                parameters["ticker"],
                parameters.get("assetClass", "equity"),
                parameters.get("venue") or parameters.get("market"),
                parameters.get("resolution", "daily"),
                parameters.get("dataType", "trade"),
                json_dump(parameters),
                CREATED,
                docker_image,
                f"lean-{run_id}"[:60],
                str(run_dir),
                str(results_dir),
                task["log_path"],
                now,
            ),
        )
    return get_backtest(run_id) or {}


def mark_backtest_queued(job_id: str) -> None:
    now = utc_now()
    update_backtest(job_id, status="queued", queued_at=now)


def fail_backtest_queue(job_id: str, error: str) -> None:
    now = utc_now()
    update_backtest(job_id, status=FAILED, error=error, error_message=error, finished_at=now)


def cancel_backtest(job_id: str) -> dict[str, Any]:
    run = get_backtest(job_id)
    if not run:
        raise KeyError("Backtest run not found.")
    if is_terminal(run.get("status")):
        return run
    if run.get("task_id"):
        try:
            task = get_task(run["task_id"])
            celery_task_id = task.get("celery_task_id")
            append_log(run["task_id"], "Cancellation requested by user.")
            if celery_task_id:
                from ..tasks.celery_app import celery_app

                celery_app.control.revoke(celery_task_id, terminate=True)
            update_task(run["task_id"], status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
        except Exception:
            pass
    if run.get("container_name"):
        try:
            DockerRunner.stop_container(str(run["container_name"]))
        except Exception:
            pass
    now = utc_now()
    update_backtest(
        job_id,
        status=CANCELLED,
        error="Cancellation requested by user.",
        error_message="Cancellation requested by user.",
        finished_at=now,
    )
    return get_backtest(job_id) or run


def backtest_status(job_id: str) -> dict[str, Any]:
    run = get_backtest(job_id)
    if not run:
        raise KeyError("Backtest run not found.")
    return {
        "job_id": run["id"],
        "status": run["status"],
        "created_at": run.get("created_at"),
        "queued_at": run.get("queued_at"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "duration_seconds": run.get("duration_seconds"),
        "error": run.get("error_message") or run.get("error"),
    }


def query_backtests(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list_backtests(filters)
