import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .common import dispatch_task
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..services.tasks import create_task
from ..tasks.worker import generate_report_task

router = APIRouter(prefix="/api/reports", tags=["reports"])


class ReportRequest(BaseModel):
    runId: str


@router.get("")
def list_reports():
    with db() as connection:
        rows = connection.execute("select * from reports order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.post("")
def create_report(request: ReportRequest):
    report_id = str(uuid.uuid4())
    task = create_task("report", f"Report {request.runId}", {"runId": request.runId}, None, report_id)
    with db() as connection:
        connection.execute(
            "insert into reports (id, task_id, run_id, status, created_at) values (?, ?, ?, ?, ?)",
            (report_id, task["id"], request.runId, "queued", utc_now()),
        )
    dispatch_task(generate_report_task.s(task["id"], report_id), task["id"])
    return detail(report_id)


@router.get("/{report_id}")
def detail(report_id: str):
    with db() as connection:
        row = connection.execute("select * from reports where id = ?", (report_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return item


@router.get("/{report_id}/file")
def report_file(report_id: str):
    item = detail(report_id)
    path = Path(item.get("report_path") or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(path)
