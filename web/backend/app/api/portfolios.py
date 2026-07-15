from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.portfolio_optimization import optimize_portfolio


router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


class PortfolioOptimizationRequest(BaseModel):
    runIds: list[str] = Field(min_length=2, max_length=5)
    objective: str = "sharpe"
    step: float = Field(default=0.1, gt=0, le=0.5)
    maxWeight: float = Field(default=1.0, gt=0, le=1.0)
    allowShort: bool = False


@router.post("/optimize")
def optimize(request: PortfolioOptimizationRequest):
    try:
        return optimize_portfolio(
            request.runIds,
            objective=request.objective,
            step=request.step,
            max_weight=request.maxWeight,
            allow_short=request.allowShort,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
