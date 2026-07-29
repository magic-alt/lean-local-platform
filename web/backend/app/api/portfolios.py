from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import paged_items
from ..services import portfolio_optimization


router = APIRouter(prefix="/api/portfolio-optimizations", tags=["portfolio-optimizations"])


class PortfolioOptimizationRequest(BaseModel):
    name: str = Field(default="Portfolio Optimization", min_length=1, max_length=255)
    runIds: list[str] = Field(min_length=2, max_length=5)
    objective: str = "sharpe"
    step: float = Field(default=0.1, gt=0, le=0.5)
    maxWeight: float = Field(default=1.0, gt=0, le=1.0)
    allowShort: bool = False


def _args(request: PortfolioOptimizationRequest) -> dict:
    return {
        "run_ids": request.runIds,
        "objective": request.objective,
        "step": request.step,
        "max_weight": request.maxWeight,
        "allow_short": request.allowShort,
    }


@router.get("/candidates")
def candidates(limit: int = 500):
    return {"items": portfolio_optimization.list_candidates(limit)}


@router.post("/preview")
def preview(request: PortfolioOptimizationRequest):
    try:
        return portfolio_optimization.preview_portfolio(**_args(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def runs(limit: int = 100, offset: int = 0, paged: bool = True):
    return paged_items(portfolio_optimization.list_runs(), limit=limit, offset=offset, paged=paged)


@router.post("")
def create(request: PortfolioOptimizationRequest):
    try:
        return portfolio_optimization.create_run(name=request.name, **_args(request))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}")
def detail(run_id: str):
    try:
        return portfolio_optimization.detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{run_id}/archive")
def archive(run_id: str):
    try:
        return portfolio_optimization.archive(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{run_id}")
def delete(run_id: str):
    try:
        return portfolio_optimization.delete(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
