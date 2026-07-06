import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.research import stop_container
from ..services.projects import get_project
from ..services.tasks import create_task
from ..tasks.worker import start_research_task

router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRequest(BaseModel):
    projectId: str
    port: int = Field(default=8888, ge=1024, le=65535)


@router.get("")
def list_sessions():
    with db() as connection:
        rows = connection.execute("select * from research_sessions order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.post("")
def start_session(request: ResearchRequest):
    try:
        get_project(request.projectId)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_id = str(uuid.uuid4())
    task = create_task("research", "Start Research", {"port": request.port}, request.projectId, session_id)
    with db() as connection:
        connection.execute(
            """
            insert into research_sessions
                (id, task_id, project_id, status, port, log_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, task["id"], request.projectId, "queued", request.port, task["log_path"], utc_now()),
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
    return item


@router.post("/{session_id}/stop")
def stop_session(session_id: str):
    item = detail(session_id)
    if item.get("container_id"):
        stop_container(item["container_id"])
    with db() as connection:
        connection.execute(
            "update research_sessions set status = ?, finished_at = ? where id = ?",
            ("cancelled", utc_now(), session_id),
        )
    return detail(session_id)
