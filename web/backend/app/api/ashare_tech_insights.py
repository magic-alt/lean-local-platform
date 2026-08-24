from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..services import ashare_tech_insights as service
from ..services import ashare_tech_agents as agent_service
from ..services.tasks import create_task, update_task
from ..db import utc_now
from ..tasks.worker import generate_ashare_tech_report_task, refresh_ashare_tech_evaluations_task


router = APIRouter(prefix="/api/insights/ashare-tech", tags=["insights", "ashare-tech"])
legacy_router = APIRouter(prefix="/api/ashare-tech-insights", tags=["insights-legacy"])


class AshareTechReportRequest(BaseModel):
    requestedDate: date | None = None
    force: bool = False
    analysisMode: Literal["auto", "hybrid_multi_agent", "deterministic"] = "auto"
    provider: str | None = Field(None, max_length=32)
    model: str | None = Field(None, max_length=128)
    promptVersionId: str | None = Field(None, max_length=128)


class ModelDiagnosticRequest(BaseModel):
    provider: str | None = Field(None, max_length=32)
    model: str | None = Field(None, max_length=128)


class PromptTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=96)
    description: str = Field("", max_length=500)
    templateKey: str | None = Field(None, max_length=96)
    stagePrompts: dict[str, str]


class ProductionProfileRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=128)
    promptVersionId: str = Field(min_length=1, max_length=128)


class WatchlistItemCreate(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    groupKey: str
    ruleTags: list[str] = Field(default_factory=list)


class WatchlistItemUpdate(BaseModel):
    enabled: bool | None = None
    groupKey: str | None = None
    ruleTags: list[str] | None = None


@router.get("/capabilities")
def read_capabilities():
    return service.capabilities()


@router.get("/prompt-templates")
def prompt_templates():
    return agent_service.list_prompt_templates()


@router.get("/prompt-templates/{template_key}/versions")
def prompt_template_versions(template_key: str):
    return agent_service.list_prompt_templates(template_key)


@router.post("/prompt-templates", status_code=201)
def create_prompt_template(request: PromptTemplateRequest):
    try:
        return agent_service.save_prompt_version(
            name=request.name,
            description=request.description,
            template_key=request.templateKey,
            stage_prompts=request.stagePrompts,
        )
    except agent_service.AgentOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/prompt-templates/{template_key}/versions", status_code=201)
def create_prompt_template_version(template_key: str, request: PromptTemplateRequest):
    try:
        return agent_service.save_prompt_version(
            name=request.name,
            description=request.description,
            template_key=template_key,
            stage_prompts=request.stagePrompts,
        )
    except agent_service.AgentOutputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/production-profile")
def production_profile():
    return agent_service.get_production_profile()


@router.put("/production-profile")
def update_production_profile(request: ProductionProfileRequest):
    try:
        return agent_service.set_production_profile(
            request.provider, request.model, request.promptVersionId,
        )
    except (agent_service.AgentOutputError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/reports")
def list_reports(limit: int = 50, offset: int = 0):
    return service.list_reports(limit=limit, offset=offset)


@router.post("/reports", status_code=202)
def create_report(request: AshareTechReportRequest):
    try:
        requested_date = request.requestedDate.isoformat() if request.requestedDate else None
        report = service.create_report(
            requested_date,
            force=request.force,
            analysis_mode=request.analysisMode,
            provider=request.provider,
            model=request.model,
            prompt_version_id=request.promptVersionId,
        )
        if not request.force and report.get("status") == "success":
            return {"id": report["id"], "taskId": report.get("task_id"), "status": "success", "reused": True}
        if report.get("status") in {"queued", "running", "waiting_data"} and report.get("task_id") and not request.force:
            return {"id": report["id"], "taskId": report["task_id"], "status": report["status"], "reused": True}
        task = create_task(
            "ashare_tech_report", f"A股科技股日报 {report['requested_date']}",
            {
                "requestedDate": report["requested_date"],
                "force": request.force,
                "analysisMode": request.analysisMode,
                "provider": request.provider,
                "model": request.model,
                "promptVersionId": request.promptVersionId,
            },
            related_id=report["id"],
        )
        service.attach_task(report["id"], task["id"])
        try:
            dispatch_task(generate_ashare_tech_report_task.s(task["id"], report["id"]), task["id"])
        except HTTPException:
            service.fail_report(report["id"], "RabbitMQ/Celery unavailable; report was not dispatched.")
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


@router.post("/model-diagnostics")
def model_diagnostics(request: ModelDiagnosticRequest | None = None):
    return agent_service.model_diagnostics(
        provider=request.provider if request else None,
        model=request.model if request else None,
    )


@router.get("/reports/{report_id}/agent-runs")
def report_agent_runs(report_id: str):
    try:
        service.get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="A-share technology report not found.") from exc
    return {"items": agent_service.list_agent_runs(report_id)}


@router.get("/agent-runs/{run_id}")
def agent_run_detail(run_id: str):
    try:
        return agent_service.get_agent_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="A-share technology Agent run not found.") from exc


@router.get("/evaluations")
def prediction_evaluations(
    horizonDays: Literal[1, 5, 20] | None = None,
    symbol: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    promptVersion: str | None = None,
    limit: int = 500,
):
    return agent_service.list_evaluations(
        horizon_days=horizonDays,
        symbol=symbol,
        provider=provider,
        model=model,
        prompt_version=promptVersion,
        limit=limit,
    )


@router.get("/evaluations/summary")
def prediction_evaluation_summary(
    horizonDays: Literal[1, 5, 20] | None = None,
    provider: str | None = None,
    model: str | None = None,
    promptVersion: str | None = None,
):
    return agent_service.evaluation_summary(
        horizon_days=horizonDays,
        provider=provider,
        model=model,
        prompt_version=promptVersion,
    )


@router.post("/evaluations/refresh", status_code=202)
def refresh_prediction_evaluations():
    task = create_task(
        "ashare_tech_evaluation",
        "刷新A股科技日报预测评估",
        {},
        related_id="ashare-tech-evaluations",
    )
    try:
        dispatch_task(refresh_ashare_tech_evaluations_task.s(task["id"]), task["id"])
    except HTTPException:
        update_task(task["id"], status="failed", error="RabbitMQ/Celery unavailable.", finished_at=utc_now())
        raise
    return {"taskId": task["id"], "status": "queued"}


@router.delete("/reports/{report_id}")
def delete_report(report_id: str, force: bool = False):
    try:
        return service.delete_report(report_id, force=force)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="A-share technology report not found.") from exc
    except service.AshareTechReportDeleteConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
        return service.update_watchlist_item(
            code,
            enabled=request.enabled,
            group_key=request.groupKey,
            rule_tags=request.ruleTags,
        )
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


def _legacy_redirect(request: Request, path: str = "") -> RedirectResponse:
    suffix = f"/{path}" if path else ""
    query = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(
        url=f"/api/insights/ashare-tech{suffix}{query}",
        status_code=308,
        headers={"Deprecation": "true", "Sunset": "Sun, 26 Jan 2027 00:00:00 GMT"},
    )


legacy_router.add_api_route(
    "",
    _legacy_redirect,
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
legacy_router.add_api_route(
    "/{path:path}",
    _legacy_redirect,
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
