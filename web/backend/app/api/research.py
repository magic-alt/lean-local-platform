from __future__ import annotations

import csv
import io
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .common import dispatch_task, paged_items
from ..core.config import RESEARCH_DIR
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..domain.data_scope import DataScope
from ..lean_engine.research import (
    container_logs,
    container_state,
    find_available_port,
    remove_container,
    stop_container,
)
from ..services import ml_research, research_analysis, research_runs
from ..services import research_snapshots
from ..services.projects import get_project
from ..services.tasks import create_task, task_logs
from ..tasks.worker import run_ml_research_task, start_research_task

router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRunRequest(BaseModel):
    template: str
    name: str | None = None
    scope: DataScope
    parameters: dict[str, Any] = Field(default_factory=dict)


class WorkspaceRequest(BaseModel):
    projectId: str
    port: int | None = Field(default=None, ge=1024, le=65535)
    snapshotId: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class SnapshotRequest(BaseModel):
    scope: DataScope


@router.get("/templates")
def templates():
    return {"items": research_analysis.TEMPLATES, "count": len(research_analysis.TEMPLATES)}


@router.post("/runs/preview")
def preview_run(request: ResearchRunRequest):
    try:
        return research_runs.preview(request.template, request.scope, request.parameters)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs")
def list_runs(limit: int = 100, offset: int = 0, paged: bool = True):
    items = research_runs.list_runs(limit, offset)
    return paged_items(items, limit=limit, offset=0, paged=paged)


@router.post("/runs")
def create_run(request: ResearchRunRequest):
    try:
        run = research_runs.create_run(
            template_key=request.template,
            name=request.name,
            scope=request.scope,
            parameters=request.parameters,
        )
        if request.template == "ml-cross-sectional-ranker":
            task = create_task("ml_research", run["name"], {"researchRunId": run["id"]}, related_id=run["id"])
            with db() as connection:
                connection.execute("update research_runs set task_id=? where id=?", (task["id"], run["id"]))
            dispatch_task(run_ml_research_task.s(task["id"], run["id"]), task["id"])
            return research_runs.get_run(run["id"])
        return run
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}")
def run_detail(run_id: str):
    try:
        return research_runs.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/runs/{run_id}")
def delete_run(run_id: str):
    try:
        research_runs.delete_run(run_id)
        return {"deleted": True, "id": run_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    try:
        return research_runs.cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str):
    try:
        run = research_runs.retry_run(run_id)
        if run.get("template_key") == "ml-cross-sectional-ranker":
            task = create_task("ml_research", run["name"], {"researchRunId": run["id"]}, related_id=run["id"])
            with db() as connection:
                connection.execute("update research_runs set task_id=? where id=?", (task["id"], run["id"]))
            dispatch_task(run_ml_research_task.s(task["id"], run["id"]), task["id"])
            return research_runs.get_run(run["id"])
        return run
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/backtest-draft")
def backtest_draft(run_id: str):
    try:
        return research_runs.backtest_draft(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs/{run_id}/export.csv")
def export_run(run_id: str):
    try:
        item = research_runs.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    result = item.get("result") or {}
    tables = result.get("tables") or []
    output = io.StringIO()
    writer = csv.writer(output)
    for table in tables:
        writer.writerow([table.get("name") or "result"])
        columns = table.get("columns") or []
        writer.writerow(columns)
        for row in table.get("rows") or []:
            writer.writerow([row.get(column) for column in columns])
        writer.writerow([])
    return Response(
        output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="research-{run_id}.csv"'},
    )


@router.get("/runs/{run_id}/artifacts/{artifact_key}")
def ml_artifact(run_id: str, artifact_key: str):
    try:
        path = ml_research.artifact_path(run_id, artifact_key)
        return FileResponse(path, filename=path.name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _workspace_path(workspace_id: str, project: dict[str, Any]) -> Path:
    root = RESEARCH_DIR / workspace_id
    target = root / "workspace"
    if not target.exists():
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(Path(project["project_path"]), target)
    return target


def _workspace_detail(workspace_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from research_workspaces where id=?", (workspace_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail="Notebook workspace not found.")
    if item.get("container_id") and item.get("status") in {"running", "starting", "success"}:
        state = container_state(str(item["container_id"]))
        if state.get("running"):
            item["status"], item["readiness_status"] = "running", "ready"
        elif state.get("status") == "missing":
            item["status"], item["readiness_status"] = "failed", "unavailable"
        item["container_status"] = state.get("status")
        item["last_checked_at"] = utc_now()
        with db() as connection:
            connection.execute(
                """
                update research_workspaces set status=?, readiness_status=?,
                    container_status=?, last_checked_at=? where id=?
                """,
                (item["status"], item.get("readiness_status"), item.get("container_status"), item["last_checked_at"], workspace_id),
            )
    return item


@router.get("/workspaces")
def list_workspaces(limit: int = 100, offset: int = 0, paged: bool = True):
    with db() as connection:
        rows = connection.execute("select * from research_workspaces order by created_at desc").fetchall()
    return paged_items(rows_to_dicts(rows), limit=limit, offset=offset, paged=paged)


@router.post("/workspaces/snapshots")
def create_workspace_snapshot(request: SnapshotRequest):
    try:
        return research_snapshots.create_snapshot(request.scope)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces")
def create_workspace(request: WorkspaceRequest):
    try:
        project = get_project(request.projectId)
        if not (RESEARCH_DIR / "snapshots" / request.snapshotId / "manifest.json").is_file():
            raise ValueError("Research snapshot not found.")
        workspace_id = str(uuid.uuid4())
        port = find_available_port(request.port)
        workspace = _workspace_path(workspace_id, project)
        task = create_task("research", "Start Notebook Workspace", {"port": port}, request.projectId, workspace_id)
        with db() as connection:
            connection.execute(
                """
                insert into research_workspaces
                    (id, task_id, project_id, status, port, log_path, created_at,
                     readiness_status, container_status, workspace_path, project_name, snapshot_id)
                values (?, ?, ?, 'queued', ?, ?, ?, 'pending', 'not_created', ?, ?, ?)
                """,
                (workspace_id, task["id"], request.projectId, port, task["log_path"], utc_now(), str(workspace), project.get("display_name") or project.get("name"), request.snapshotId),
            )
        dispatch_task(start_research_task.s(task["id"], workspace_id), task["id"])
        return _workspace_detail(workspace_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str):
    return _workspace_detail(workspace_id)


@router.get("/workspaces/{workspace_id}/logs")
def workspace_logs(workspace_id: str):
    item = _workspace_detail(workspace_id)
    worker = task_logs(item["task_id"]) if item.get("task_id") else ""
    docker = container_logs(str(item.get("container_id") or ""))
    return {"logs": "\n\n".join(part for part in (worker, docker) if part), "workspaceId": workspace_id}


@router.post("/workspaces/{workspace_id}/stop")
def stop_workspace(workspace_id: str):
    item = _workspace_detail(workspace_id)
    if item.get("container_id"):
        stop_container(str(item["container_id"]))
        remove_container(str(item["container_id"]))
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            update research_workspaces set status='stopped', readiness_status='stopped',
                container_status='removed', container_id=null, url=null,
                finished_at=?, last_checked_at=? where id=?
            """,
            (now, now, workspace_id),
        )
    return _workspace_detail(workspace_id)


@router.post("/workspaces/{workspace_id}/restart")
def restart_workspace(workspace_id: str):
    item = _workspace_detail(workspace_id)
    if item.get("status") in {"queued", "starting", "running"}:
        raise HTTPException(status_code=400, detail="Stop the active workspace before restarting it.")
    port = find_available_port(int(item["port"]))
    task = create_task("research", "Restart Notebook Workspace", {"port": port}, item["project_id"], workspace_id)
    with db() as connection:
        connection.execute(
            """
            update research_workspaces set task_id=?, status='queued', port=?,
                readiness_status='pending', container_status='not_created',
                error=null, started_at=null, finished_at=null where id=?
            """,
            (task["id"], port, workspace_id),
        )
    dispatch_task(start_research_task.s(task["id"], workspace_id), task["id"])
    return _workspace_detail(workspace_id)


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, purgeWorkspace: bool = False):
    item = _workspace_detail(workspace_id)
    if item.get("status") in {"queued", "starting", "running"}:
        stop_workspace(workspace_id)
    root = RESEARCH_DIR / workspace_id
    with db() as connection:
        connection.execute("delete from research_workspaces where id=?", (workspace_id,))
    if purgeWorkspace and root.exists():
        shutil.rmtree(root, ignore_errors=True)
    return {"deleted": True, "id": workspace_id, "workspacePurged": purgeWorkspace}
