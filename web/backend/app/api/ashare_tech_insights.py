from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..services import ashare_tech_insights as service
from ..services.tasks import create_task
from ..tasks.worker import generate_ashare_tech_report_task


router = APIRouter(prefix="/api/ashare-tech-insights", tags=["insights", "ashare-tech"])
legacy_router = APIRouter(prefix="/api/insights/ashare-tech", tags=["insights", "ashare-tech-legacy"])


class AshareTechReportRequest(BaseModel):
    requestedDate: date | None = None
    force: bool = False


class WatchlistItemCreate(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    groupKey: str
    ruleTags: list[str] = Field(default_factory=list)


class WatchlistItemUpdate(BaseModel):
    enabled: bool | None = None
    ruleTags: list[str] | None = None


@router.get("/capabilities")
def read_capabilities():
    return service.capabilities()


@router.get("/reports")
def list_reports(limit: int = 50, offset: int = 0):
    return service.list_reports(limit=limit, offset=offset)


@router.post("/reports", status_code=202)
def create_report(request: AshareTechReportRequest):
    try:
        requested_date = request.requestedDate.isoformat() if request.requestedDate else None
        report = service.create_report(requested_date, force=request.force)
        if not request.force and report.get("status") == "success":
            return {"id": report["id"], "taskId": report.get("task_id"), "status": "success", "reused": True}
        if report.get("status") in {"queued", "running", "waiting_data"} and report.get("task_id") and not request.force:
            return {"id": report["id"], "taskId": report["task_id"], "status": report["status"], "reused": True}
        task = create_task(
            "ashare_tech_report", f"A股科技股日报 {report['requested_date']}",
            {"requestedDate": report["requested_date"], "force": request.force}, related_id=report["id"],
        )
        service.attach_task(report["id"], task["id"])
        try:
            dispatch_task(generate_ashare_tech_report_task.s(task["id"], report["id"]), task["id"])
        except HTTPException:
            service.fail_report(report["id"], "Redis/Celery unavailable; report was not dispatched.")
            raise
        return {"id": report["id"], "taskId": task["id"], "status": "queued", "reused": False}
    except service.AshareTechReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reports/{report_id}")
def report_detail(report_id: str):
    try:
        return service.get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="A-share technology report not found.") from exc


@router.get("/watchlist")
def read_watchlist():
    return service.get_watchlist()


@router.post("/watchlist/items", status_code=201)
def add_watchlist_item(request: WatchlistItemCreate):
    try:
        return service.add_watchlist_item(request.code, request.groupKey, request.ruleTags)
    except service.AshareTechReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/watchlist/items/{code}")
def update_watchlist_item(code: str, request: WatchlistItemUpdate):
    try:
        return service.update_watchlist_item(code, enabled=request.enabled, rule_tags=request.ruleTags)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Watchlist item not found.") from exc
    except service.AshareTechReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/watchlist/items/{code}")
def delete_watchlist_item(code: str):
    try:
        return service.delete_watchlist_item(code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Watchlist item not found.") from exc
    except service.AshareTechReportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/watchlist/reset")
def reset_watchlist():
    return service.reset_watchlist()


# Compatibility aliases for the first implementation. The frontend exclusively uses
# the canonical top-level prefix so it can never collide with /api/insights/{report_id}.
legacy_router.add_api_route("/capabilities", read_capabilities, methods=["GET"])
legacy_router.add_api_route("", list_reports, methods=["GET"])
legacy_router.add_api_route("", create_report, methods=["POST"], status_code=202)
legacy_router.add_api_route("/{report_id}", report_detail, methods=["GET"])
