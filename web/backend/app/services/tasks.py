import uuid
from pathlib import Path
from typing import Any

from ..core.config import RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.backtest_job import CANCELLED, is_terminal
from ..runners.docker_runner import DockerRunner


def create_task(
    kind: str,
    title: str,
    parameters: dict[str, Any],
    project_id: str | None = None,
    related_id: str | None = None,
    status: str = "queued",
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    log_path = RUNS_DIR / "task-logs" / f"{task_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into tasks
                (id, kind, status, title, project_id, related_id, parameters_json, log_path, artifacts_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, kind, status, title, project_id, related_id, json_dump(parameters), str(log_path), "[]", now),
        )
    return get_task(task_id)


def get_task(task_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from tasks where id = ?", (task_id,)).fetchone()
    task = row_to_dict(row)
    if task is None:
        raise KeyError("Task not found.")
    return task


def list_tasks() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from tasks order by created_at desc").fetchall()
    return rows_to_dicts(rows)


def update_task(task_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [json_dump(value) if key.endswith("_json") else value for key, value in fields.items()]
    values.append(task_id)
    with db() as connection:
        connection.execute(f"update tasks set {assignments} where id = ?", values)


def append_log(task_id: str, line: str) -> None:
    task = get_task(task_id)
    path = Path(task["log_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def task_logs(task_id: str, limit: int = 120000) -> str:
    path = Path(get_task(task_id)["log_path"])
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-limit:]


def _revoke_celery(task: dict[str, Any]) -> None:
    celery_task_id = task.get("celery_task_id")
    if not celery_task_id:
        return
    try:
        from ..tasks.celery_app import celery_app

        celery_app.control.revoke(celery_task_id, terminate=True, signal="SIGTERM")
        append_log(task["id"], f"Celery task {celery_task_id} revoke requested.")
    except Exception as exc:
        append_log(task["id"], f"Celery revoke failed: {exc}")


def _cancel_optimization(task: dict[str, Any]) -> None:
    optimization_id = task.get("related_id")
    now = utc_now()
    with db() as connection:
        if optimization_id:
            connection.execute(
                "update optimization_runs set status = ?, error = coalesce(error, ?), finished_at = coalesce(finished_at, ?) where id = ?",
                (CANCELLED, "Cancellation requested by user.", now, optimization_id),
            )
        rows = connection.execute("select id, status, container_name from backtest_runs where task_id = ?", (task["id"],)).fetchall()
    for row in rows_to_dicts(rows):
        if is_terminal(row.get("status")):
            continue
        container_name = row.get("container_name")
        if container_name:
            try:
                DockerRunner.stop_container(str(container_name), lambda line: append_log(task["id"], line))
            except Exception as exc:
                append_log(task["id"], f"Docker stop failed for {container_name}: {exc}")
        with db() as connection:
            connection.execute(
                """
                update backtest_runs
                set status = ?, error = ?, error_message = ?, finished_at = coalesce(finished_at, ?)
                where id = ?
                """,
                (CANCELLED, "Cancellation requested by user.", "Cancellation requested by user.", now, row["id"]),
            )


def _cancel_research(task: dict[str, Any]) -> None:
    session_id = task.get("related_id")
    if not session_id:
        return
    with db() as connection:
        row = connection.execute("select container_id from research_sessions where id = ?", (session_id,)).fetchone()
    session = row_to_dict(row)
    if session and session.get("container_id"):
        try:
            from ..lean_engine.research import stop_container

            stop_container(str(session["container_id"]))
            append_log(task["id"], f"Research container {session['container_id']} stop requested.")
        except Exception as exc:
            append_log(task["id"], f"Research container stop failed: {exc}")
    with db() as connection:
        connection.execute(
            "update research_sessions set status = ?, finished_at = coalesce(finished_at, ?) where id = ?",
            (CANCELLED, utc_now(), session_id),
        )


def _cancel_report(task: dict[str, Any]) -> None:
    report_id = task.get("related_id")
    if not report_id:
        return
    with db() as connection:
        connection.execute(
            "update reports set status = ?, error = coalesce(error, ?), finished_at = coalesce(finished_at, ?) where id = ?",
            (CANCELLED, "Cancellation requested by user.", utc_now(), report_id),
        )


def _cancel_insight(task: dict[str, Any]) -> None:
    report_id = task.get("related_id")
    if not report_id:
        return
    with db() as connection:
        connection.execute(
            "update insight_reports set status = ?, error = coalesce(error, ?), finished_at = coalesce(finished_at, ?) where id = ?",
            (CANCELLED, "Cancellation requested by user.", utc_now(), report_id),
        )


def _cancel_ashare_tech_report(task: dict[str, Any]) -> None:
    report_id = task.get("related_id")
    if not report_id:
        return
    with db() as connection:
        connection.execute(
            "update ashare_tech_reports set status = ?, error = coalesce(error, ?), finished_at = coalesce(finished_at, ?), updated_at = ? where id = ?",
            (CANCELLED, "Cancellation requested by user.", utc_now(), utc_now(), report_id),
        )


def cancel_task(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if is_terminal(task.get("status")):
        return task

    append_log(task_id, "Cancellation requested by user.")
    if task.get("kind") == "backtest" and task.get("related_id"):
        from .backtest_service import cancel_backtest

        cancel_backtest(str(task["related_id"]))
        return get_task(task_id)

    _revoke_celery(task)
    if task.get("kind") == "optimization":
        _cancel_optimization(task)
    elif task.get("kind") == "research":
        _cancel_research(task)
    elif task.get("kind") == "report":
        _cancel_report(task)
    elif task.get("kind") == "insight":
        _cancel_insight(task)
    elif task.get("kind") == "ashare_tech_report":
        _cancel_ashare_tech_report(task)

    update_task(
        task_id,
        status=CANCELLED,
        error="Cancellation requested by user.",
        finished_at=utc_now(),
    )
    return get_task(task_id)


def delete_task(task_id: str) -> dict[str, Any]:
    task = get_task(task_id)
    if not is_terminal(task.get("status")):
        task = cancel_task(task_id)

    log_path = task.get("log_path")
    with db() as connection:
        connection.execute("delete from tasks where id = ?", (task_id,))
    if log_path:
        try:
            Path(str(log_path)).unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": True, "id": task_id}
