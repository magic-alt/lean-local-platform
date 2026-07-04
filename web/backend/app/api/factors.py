from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..research import factors

router = APIRouter(prefix="/api/factors", tags=["factors"])


class FactorValueRecord(BaseModel):
    symbol: str
    tradeDate: str
    factorName: str
    value: float
    source: str | None = None


class FactorValueImport(BaseModel):
    source: str = "manual"
    records: list[FactorValueRecord] = Field(min_length=1)


class FactorMatrixRequest(BaseModel):
    universeCode: str = "ALL_A"
    startDate: str
    endDate: str
    factorNames: list[str] = Field(min_length=1)
    forwardDays: int = Field(default=1, ge=1)


class FactorEvaluateRequest(BaseModel):
    factorName: str
    universeCode: str = "ALL_A"
    startDate: str
    endDate: str
    forwardDays: int = Field(default=1, ge=1)
    quantiles: int = Field(default=5, ge=2, le=20)
    engine: str | None = None
    persist: bool = True


class FactorBatchEvaluateRequest(BaseModel):
    factorNames: list[str] = Field(min_length=1)
    universeCode: str = "ALL_A"
    startDate: str
    endDate: str
    forwardDays: int = Field(default=1, ge=1)
    quantiles: int = Field(default=5, ge=2, le=20)
    engine: str | None = None


def _record(item: FactorValueRecord) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "trade_date": item.tradeDate,
        "factor_name": item.factorName,
        "value": item.value,
        "source": item.source,
    }


@router.get("/engines")
def engines():
    return {"available": factors.available_engines(), "selected": factors.selected_engine()}


@router.post("/values")
def import_values(request: FactorValueImport):
    try:
        return factors.import_factor_values([_record(item) for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/matrix")
def matrix(request: FactorMatrixRequest):
    try:
        items = factors.factor_matrix(
            universe_code=request.universeCode,
            start_date=request.startDate,
            end_date=request.endDate,
            factor_names=request.factorNames,
            forward_days=request.forwardDays,
        )
        return {"count": len(items), "items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluate")
def evaluate(request: FactorEvaluateRequest):
    try:
        return factors.evaluate_factor(
            factor_name=request.factorName,
            universe_code=request.universeCode,
            start_date=request.startDate,
            end_date=request.endDate,
            forward_days=request.forwardDays,
            quantiles=request.quantiles,
            engine=request.engine,
            persist=request.persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/evaluate-batch")
def evaluate_batch(request: FactorBatchEvaluateRequest):
    try:
        return factors.batch_evaluate_factors(
            factor_names=request.factorNames,
            universe_code=request.universeCode,
            start_date=request.startDate,
            end_date=request.endDate,
            forward_days=request.forwardDays,
            quantiles=request.quantiles,
            engine=request.engine,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/evaluations")
def evaluations(limit: int = 50):
    try:
        items = factors.list_factor_evaluations(limit)
        return {"items": items, "count": len(items)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
