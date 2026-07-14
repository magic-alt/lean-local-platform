from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..services import insights as insight_service
from ..services.tasks import create_task
from ..tasks.worker import generate_insight_task


router = APIRouter(prefix="/api/insights", tags=["insights"])


class InsightRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    assetClass: Literal["equity", "crypto", "crypto_future", "future"] = "equity"
    market: str | None = Field(None, max_length=32)
    venue: str | None = Field(None, max_length=32)
    resolution: Literal["daily"] = "daily"
    dataType: str = "trade"
    asOfDate: date | None = None
    lookbackBars: int = Field(120, ge=60, le=500)
    backtestRunId: str | None = Field(None, max_length=64)


class PaperHandoffRequest(BaseModel):
    sessionId: str = Field(min_length=1)
    targetPercent: float | None = Field(None, gt=0, le=1)


@router.get("/capabilities")
def read_capabilities():
    return insight_service.capabilities()


@router.get("")
def list_insights(
    assetClass: str | None = None,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    return insight_service.list_reports(
        asset_class=assetClass,
        symbol=symbol,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=202)
def create_insight(request: InsightRequest):
    try:
        parameters = request.model_dump(mode="json")
        report = insight_service.create_report(parameters)
        task = create_task(
            "insight",
            f"Insight {report['asset_class']}/{report['symbol']}",
            parameters,
            related_id=report["id"],
        )
        insight_service.attach_task(report["id"], task["id"])
        try:
            dispatch_task(generate_insight_task.s(task["id"], report["id"]), task["id"])
        except HTTPException:
            insight_service.fail_report(report["id"], "Redis/Celery unavailable; insight was not dispatched.")
            raise
        return {"id": report["id"], "taskId": task["id"], "status": "queued"}
    except insight_service.InsightConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except insight_service.InsightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{report_id}")
def insight_detail(report_id: str):
    try:
        return insight_service.get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Insight report not found.") from exc


@router.post("/{report_id}/paper-signals")
def handoff_to_paper(report_id: str, request: PaperHandoffRequest):
    try:
        return insight_service.handoff_to_paper(report_id, request.sessionId, request.targetPercent)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except insight_service.InsightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
