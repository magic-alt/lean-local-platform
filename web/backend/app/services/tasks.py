import uuid
from pathlib import Path
from typing import Any

from ..core.config import RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.backtest_job import CANCELLED, is_terminal


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
        rows = connection.execute(
            """
            select id,celery_task_id,kind,status,title,project_id,related_id,parameters_json,
                   error,created_at,started_at,finished_at
            from tasks order by created_at desc
            """
        ).fetchall()
    items = rows_to_dicts(rows)
    for item in items:
        parameters = item.get("parameters") or {}
        item["parameters"] = {
            key: value for key, value in parameters.items()
            if not isinstance(value, (dict, list)) and len(str(value)) <= 512
        }
    return items


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
    return log_window(path, limit=limit)["logs"]


def log_window(
    path: Path,
    *,
    offset: int | None = None,
    cursor: str | None = None,
    limit: int = 65536,
) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 1_000_000))
    if not path.is_file():
        return {
            "logs": "",
            "offset": 0,
            "nextOffset": 0,
            "cursor": "0",
            "nextCursor": None,
            "limit": bounded_limit,
            "total": 0,
            "hasMore": False,
        }
    total = path.stat().st_size
    if cursor not in (None, ""):
        try:
            requested_offset = int(str(cursor))
        except ValueError as exc:
            raise ValueError("cursor must be a non-negative byte offset.") from exc
    elif offset is not None:
        requested_offset = int(offset)
    else:
        requested_offset = max(0, total - bounded_limit)
    if requested_offset < 0:
        raise ValueError("offset must be non-negative.")
    start = min(requested_offset, total)
    with path.open("rb") as file:
        file.seek(start)
        raw = file.read(bounded_limit)
    next_offset = start + len(raw)
    has_more = next_offset < total
    return {
        "logs": raw.decode("utf-8", errors="replace"),
        "offset": start,
        "nextOffset": next_offset,
        "cursor": str(start),
        "nextCursor": str(next_offset) if has_more else None,
        "limit": bounded_limit,
        "total": total,
        "hasMore": has_more,
    }


def task_log_window(
    task_id: str,
    *,
    offset: int | None = None,
    cursor: str | None = None,
    limit: int = 65536,
) -> dict[str, Any]:
    path = Path(get_task(task_id)["log_path"])
    return log_window(path, offset=offset, cursor=cursor, limit=limit)


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


def _cancel_research(task: dict[str, Any]) -> None:
    session_id = task.get("related_id")
    if not session_id:
        return
    with db() as connection:
        row = connection.execute("select container_id from research_workspaces where id = ?", (session_id,)).fetchone()
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
            "update research_workspaces set status = ?, finished_at = coalesce(finished_at, ?) where id = ?",
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


def _cancel_ashare_tech_report(task: dict[str, Any]) -> None:
    report_id = task.get("related_id")
    if not report_id:
        return
    with db() as connection:
        connection.execute(
            "update ashare_tech_reports set status = ?, error = coalesce(error, ?), finished_at = coalesce(finished_at, ?), updated_at = ? where id = ?",
            (CANCELLED, "Cancellation requested by user.", utc_now(), utc_now(), report_id),
        )


def _cancel_data_sync(task: dict[str, Any]) -> None:
    run_id = task.get("related_id")
    if not run_id:
        return
    now = utc_now()
    message = "Cancellation requested by user."
    with db() as connection:
        connection.execute(
            """
            update data_sync_runs
            set cancel_requested = 1,
                status = 'cancelled',
                error = coalesce(error, ?),
                finished_at = coalesce(finished_at, ?)
            where id = ? and status in ('queued', 'running', 'cancelling')
            """,
            (message, now, run_id),
        )
        connection.execute(
            """
            update data_sync_items
            set status = 'cancelled',
                error = coalesce(error, ?),
                finished_at = coalesce(finished_at, ?)
            where run_id = ? and status in ('queued', 'running', 'checking', 'cancelling')
            """,
            (message, now, run_id),
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
    if task.get("kind") == "research":
        _cancel_research(task)
    elif task.get("kind") == "report":
        _cancel_report(task)
    elif task.get("kind") == "ashare_tech_report":
        _cancel_ashare_tech_report(task)
    elif task.get("kind") == "data_sync":
        _cancel_data_sync(task)

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
        raise ValueError("Active tasks must be cancelled before deletion.")

    log_path = task.get("log_path")
    with db() as connection:
        connection.execute("delete from tasks where id = ?", (task_id,))
    if log_path:
        try:
            Path(str(log_path)).unlink(missing_ok=True)
        except OSError:
            pass
    return {"deleted": True, "id": task_id}
