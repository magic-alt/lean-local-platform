import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
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
from ..services.workflows import record_workflow_event
from ..tasks.worker import start_research_task

router = APIRouter(prefix="/api/research", tags=["research"])


class ResearchRequest(BaseModel):
    projectId: str
    port: int | None = Field(default=None, ge=1024, le=65535)


class ResearchCheckRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, max_length=100)
    startDate: str | None = None
    endDate: str | None = None


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


@router.post("/{session_id}/checks")
def run_checks(session_id: str, payload: ResearchCheckRequest, request: Request):
    item = detail(session_id)
    project = get_project(str(item["project_id"]))
    workspace = Path(str(item.get("workspace_path") or ""))
    main_file = workspace / str(project.get("main_file") or "main.py")
    requested_symbols = sorted({str(value).strip().upper() for value in payload.symbols if str(value).strip()})
    with db() as connection:
        recent = rows_to_dicts(
            connection.execute(
                """
                select symbol, asset_class, venue, resolution, data_type, parameters_json
                from backtest_runs where project_id = ?
                order by created_at desc limit 20
                """,
                (item["project_id"],),
            ).fetchall()
        )
    if requested_symbols:
        recent = [row for row in recent if str(row.get("symbol") or "").upper() in requested_symbols]
    checks: list[dict] = []
    checks.append({"name": "workspace_exists", "passed": workspace.is_dir(), "detail": str(workspace)})
    checks.append({"name": "strategy_main_exists", "passed": main_file.is_file(), "detail": str(main_file)})
    if main_file.is_file() and main_file.suffix == ".py":
        try:
            compile(main_file.read_text(encoding="utf-8"), str(main_file), "exec")
            checks.append({"name": "strategy_python_syntax", "passed": True})
        except Exception as exc:
            checks.append({"name": "strategy_python_syntax", "passed": False, "detail": str(exc)})
    for row in recent:
        parameters = row.get("parameters") or {}
        symbol = str(row.get("symbol") or "").upper()
        market = str(row.get("venue") or parameters.get("market") or "china").lower()
        start = payload.startDate or parameters.get("start")
        end = payload.endDate or parameters.get("end")
        source = parameters.get("source")
        source_clause = "and source = ?" if source else ""
        values = [symbol, str(row.get("asset_class") or "equity"), market, market]
        if start and end:
            date_clause = "and trade_date between ? and ?"
            values.extend([start, end])
        else:
            date_clause = ""
        if source:
            values.append(source)
        with db() as connection:
            coverage = connection.execute(
                f"""
                select count(distinct trade_date) as rows, min(trade_date) as first_date, max(trade_date) as last_date
                from market_daily_bars
                where symbol = ? and asset_class = ? and market = ? and venue = ?
                  {date_clause} {source_clause}
                """,
                values,
            ).fetchone()
        coverage_item = dict(coverage) if coverage else {}
        checks.append(
            {
                "name": f"market_data:{market}:{symbol}",
                "passed": int(coverage_item.get("rows") or 0) > 0,
                "detail": {**coverage_item, "start": start, "end": end, "source": source},
            }
        )
    if not recent:
        checks.append({"name": "project_backtest_scope", "passed": False, "detail": "No project backtest scope is available to verify."})
    passed = all(bool(check.get("passed")) for check in checks)
    now = utc_now()
    result = {
        "sessionId": session_id,
        "projectId": item["project_id"],
        "generatedAt": now,
        "passed": passed,
        "status": item.get("status"),
        "checks": checks,
    }
    evidence_dir = workspace / ".lean-platform"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "research-check-latest.json"
    evidence_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    result["evidencePath"] = str(evidence_path)
    trace_id = str(getattr(request.state, "trace_id", ""))
    workflow_id = str(getattr(request.state, "workflow_id", ""))
    record_workflow_event(
        workflow_id=workflow_id,
        trace_id=trace_id,
        stage="research",
        action="run_checks",
        status="success" if passed else "failed",
        resource_type="research_session",
        resource_id=session_id,
        error_code=None if passed else "research_check_failed",
        message="Research checks passed." if passed else "Research checks found blocking issues.",
        details={"evidencePath": str(evidence_path), "checks": checks},
    )
    return result


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
