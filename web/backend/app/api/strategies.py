from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.errors import LeanWebError, NotFoundError
from ..services import projects as project_service
from ..services.strategies import list_templates

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


@router.get("/templates")
def templates():
    return list_templates()


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
def delete_strategy(strategy_id: str):
    try:
        return {"deleted": True, "details": project_service.delete_project(strategy_id)}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
