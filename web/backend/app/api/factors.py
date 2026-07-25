from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..research import factors
from ..research.factor_pipeline import construct_factor_portfolio, factor_templates, process_factor_rows

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


class FactorPipelineRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    value: float


class FactorTransformRequest(BaseModel):
    records: list[FactorPipelineRecord] = Field(min_length=1)
    normalization: str = "winsor_zscore"
    winsorLower: float = 0.01
    winsorUpper: float = 0.99
    neutralizeGroups: list[str] = Field(default_factory=list)
    neutralizeExposures: list[str] = Field(default_factory=list)
    partitionBy: list[str] = Field(default_factory=lambda: ["tradeDate"])


class FactorPortfolioRecord(BaseModel):
    symbol: str
    score: float


class FactorPortfolioRequest(BaseModel):
    records: list[FactorPortfolioRecord] = Field(min_length=1)
    method: str = "equal_top"
    topN: int = Field(default=20, ge=1)
    bottomN: int = Field(default=20, ge=1)
    grossExposure: float = Field(default=1.0, gt=0)
    netExposure: float = 1.0
    maxWeight: float = Field(default=0.1, gt=0)


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


@router.get("/templates")
def templates():
    return factor_templates()


@router.post("/transform")
def transform(request: FactorTransformRequest):
    try:
        return process_factor_rows(
            [
                {**item.model_dump(), **(item.model_extra or {})}
                for item in request.records
            ],
            normalization=request.normalization,
            winsor_lower=request.winsorLower,
            winsor_upper=request.winsorUpper,
            neutralize_groups=request.neutralizeGroups,
            neutralize_exposures=request.neutralizeExposures,
            partition_by=request.partitionBy,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/portfolio")
def construct_portfolio(request: FactorPortfolioRequest):
    try:
        return construct_factor_portfolio(
            [item.model_dump() for item in request.records],
            method=request.method,
            top_n=request.topN,
            bottom_n=request.bottomN,
            gross_exposure=request.grossExposure,
            net_exposure=request.netExposure,
            max_weight=request.maxWeight,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
