from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.errors import LeanWebError, NotFoundError
from ..services import projects as project_service
from ..services.strategies import list_templates
from ..services.strategy_admission import (
    admission_config,
    evaluate_admission,
    get_admission,
    register_baseline,
    validate_paper_stage,
)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyCreate(BaseModel):
    name: str
    language: str = "Python"
    algorithmClass: str | None = None
    templateKey: str | None = None
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    parameters: dict[str, Any] | None = None


class StrategyUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class BaselineRequest(BaseModel):
    runIds: list[str] = Field(min_length=1)
    regimes: dict[str, str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    profile: str = "institutional"
    sampleSet: str = "seed_v1"


class AdmissionRequest(BaseModel):
    runIds: list[str] = Field(min_length=1)
    regimes: dict[str, str]
    parameters: dict[str, Any] = Field(default_factory=dict)
    profile: str = "institutional"


class PaperValidationRequest(BaseModel):
    sessionId: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    profile: str = "institutional"
    minReportDays: int = Field(default=20, ge=1)


@router.get("/templates")
def templates():
    return list_templates()


@router.get("/admission/config")
def get_admission_config():
    return admission_config()


@router.post("/{strategy_id}/baselines")
def create_baseline(strategy_id: str, request: BaselineRequest):
    try:
        project_service.get_project(strategy_id)
        return register_baseline(
            strategy_id,
            run_ids=request.runIds,
            regimes=request.regimes,
            parameters=request.parameters,
            profile_name=request.profile,
            sample_set=request.sampleSet,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{strategy_id}/admissions")
def create_admission(strategy_id: str, request: AdmissionRequest):
    try:
        project_service.get_project(strategy_id)
        return evaluate_admission(
            strategy_id,
            run_ids=request.runIds,
            regimes=request.regimes,
            parameters=request.parameters,
            profile_name=request.profile,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{strategy_id}/paper-validations")
def create_paper_validation(strategy_id: str, request: PaperValidationRequest):
    try:
        project_service.get_project(strategy_id)
        return validate_paper_stage(
            strategy_id,
            session_id=request.sessionId,
            parameters=request.parameters,
            profile_name=request.profile,
            min_report_days=request.minReportDays,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{strategy_id}/admission")
def admission_detail(strategy_id: str, parametersSha256: str, profile: str = "institutional"):
    item = get_admission(strategy_id, parametersSha256, profile)
    if not item:
        raise HTTPException(status_code=404, detail="Strategy admission not found.")
    return item


@router.get("")
def list_strategies():
    return project_service.list_projects()


@router.post("")
def create_strategy(request: StrategyCreate):
    try:
        return project_service.create_project(
            request.name,
            request.language,
            request.algorithmClass,
            template_key=request.templateKey,
            asset_class=request.assetClass,
            market=request.market,
            venue=request.venue,
            resolution=request.resolution,
            data_type=request.dataType,
            parameters=request.parameters,
        )
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str):
    try:
        return project_service.get_project(strategy_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{strategy_id}")
def update_strategy(strategy_id: str, request: StrategyUpdate):
    try:
        return project_service.update_project(strategy_id, name=request.name, config_updates=request.config)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{strategy_id}")
@router.delete("/{strategy_id}/")
def delete_strategy(strategy_id: str):
    try:
        return {"deleted": True, "details": project_service.delete_project(strategy_id)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
