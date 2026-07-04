import uuid
from pathlib import Path
from typing import Any

from ..core.config import RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


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
