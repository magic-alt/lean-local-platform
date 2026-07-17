import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import RESEARCH_DIR
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.research import (
    container_logs,
    container_state,
    find_available_port,
    remove_container,
    stop_container,
)
from ..services.projects import get_project
from ..services.tasks import create_task, task_logs
from ..tasks.worker import start_research_task

router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRequest(BaseModel):
    projectId: str
    port: int | None = Field(default=None, ge=1024, le=65535)


def _workspace(session_id: str, project: dict) -> Path:
    root = RESEARCH_DIR / session_id
    target = root / "workspace"
    if target.exists():
        return target
    root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(project["project_path"]), target)
    return target


def _reconcile(item: dict) -> dict:
    container_id = item.get("container_id")
    if not container_id or item.get("status") not in {"running", "starting", "success"}:
        return item
    state = container_state(str(container_id))
    now = utc_now()
    status = item.get("status")
    readiness = item.get("readiness_status")
    error = item.get("error")
    finished = item.get("finished_at")
    if state.get("running"):
        status = "running"
        readiness = "ready"
        finished = None
    elif state.get("status") == "missing":
        status = "failed"
        readiness = "unavailable"
        error = error or "Research container is no longer present."
        finished = finished or now
    else:
        status = "failed"
        readiness = "unavailable"
        error = error or f"Research container exited with status {state.get('status')} and code {state.get('exitCode')}."
        finished = finished or now
    with db() as connection:
        connection.execute(
            """
            update research_sessions
            set status=?, readiness_status=?, container_status=?, error=?, last_checked_at=?, finished_at=?
            where id=?
            """,
            (status, readiness, state.get("status"), error, now, finished, item["id"]),
        )
    return {**item, "status": status, "readiness_status": readiness, "container_status": state.get("status"), "error": error, "last_checked_at": now, "finished_at": finished}


@router.get("")
def list_sessions():
    with db() as connection:
        rows = connection.execute("select * from research_sessions order by created_at desc").fetchall()
    return [_reconcile(item) for item in rows_to_dicts(rows)]


@router.post("")
def start_session(request: ResearchRequest):
    try:
        project = get_project(request.projectId)
        port = find_available_port(request.port)
        session_id = str(uuid.uuid4())
        workspace = _workspace(session_id, project)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = create_task("research", "Start Research", {"port": port}, request.projectId, session_id)
    with db() as connection:
        connection.execute(
            """
            insert into research_sessions
                (id, task_id, project_id, status, port, log_path, created_at,
                 readiness_status, container_status, workspace_path, project_name)
            values (?, ?, ?, 'queued', ?, ?, ?, 'pending', 'not_created', ?, ?)
            """,
            (session_id, task["id"], request.projectId, port, task["log_path"], utc_now(), str(workspace), project.get("display_name") or project.get("name")),
        )
    dispatch_task(start_research_task.s(task["id"], session_id), task["id"])
    return detail(session_id)


@router.get("/{session_id}")
def detail(session_id: str):
    with db() as connection:
        row = connection.execute("select * from research_sessions where id = ?", (session_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail="Research session not found.")
    return _reconcile(item)


@router.get("/{session_id}/logs")
def logs(session_id: str):
    item = detail(session_id)
    worker = task_logs(item["task_id"]) if item.get("task_id") else ""
    docker = container_logs(str(item.get("container_id") or ""))
    return {"logs": "\n\n".join(part for part in (worker, docker) if part), "sessionId": session_id}


@router.post("/{session_id}/stop")
def stop_session(session_id: str):
    item = detail(session_id)
    if item.get("container_id"):
        stop_container(str(item["container_id"]))
        remove_container(str(item["container_id"]))
    with db() as connection:
        connection.execute(
            """
            update research_sessions
            set status='stopped', readiness_status='stopped', container_status='removed',
                container_id=null, url=null, finished_at=?, last_checked_at=?
            where id=?
            """,
            (utc_now(), utc_now(), session_id),
        )
    return detail(session_id)


@router.post("/{session_id}/restart")
def restart_session(session_id: str):
    item = detail(session_id)
    if item.get("status") in {"queued", "starting", "running"}:
        raise HTTPException(status_code=400, detail="Stop the active Research session before restarting it.")
    try:
        port = find_available_port(int(item["port"]))
        task = create_task("research", "Restart Research", {"port": port}, item["project_id"], session_id)
        with db() as connection:
            connection.execute(
                """
                update research_sessions
                set task_id=?, status='queued', port=?, readiness_status='pending',
                    container_status='not_created', error=null, started_at=null, finished_at=null
                where id=?
                """,
                (task["id"], port, session_id),
            )
        dispatch_task(start_research_task.s(task["id"], session_id), task["id"])
        return detail(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{session_id}")
def delete_session(session_id: str, purgeWorkspace: bool = False):
    item = detail(session_id)
    if item.get("status") in {"queued", "starting", "running"}:
        stop_session(session_id)
    if item.get("container_id"):
        remove_container(str(item["container_id"]))
    workspace = Path(str(item.get("workspace_path") or ""))
    with db() as connection:
        connection.execute("delete from research_sessions where id=?", (session_id,))
    if purgeWorkspace and workspace.exists():
        root = RESEARCH_DIR / session_id
        try:
            workspace.resolve().relative_to(root.resolve())
            shutil.rmtree(root, ignore_errors=True)
        except ValueError:
            pass
    return {"deleted": True, "id": session_id, "workspacePurged": bool(purgeWorkspace)}
