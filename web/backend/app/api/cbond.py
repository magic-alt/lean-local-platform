from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import cbond

router = APIRouter(prefix="/api/cbond", tags=["convertible-bonds"])


class CBondTermRecord(BaseModel):
    bondCode: str
    bondName: str | None = None
    stockSymbol: str
    listedDate: str | None = None
    delistedDate: str | None = None
    maturityDate: str | None = None
    rating: str | None = None
    conversionPrice: float | None = None
    issueSize: float | None = None
    remainingSize: float | None = None
    terms: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None


class CBondTermImport(BaseModel):
    source: str = "manual"
    records: list[CBondTermRecord] = Field(min_length=1)


class CBondDailyRecord(BaseModel):
    bondCode: str
    tradeDate: str
    close: float
    stockClose: float | None = None
    conversionPrice: float | None = None
    conversionValue: float | None = None
    premiumRate: float | None = None
    remainingSize: float | None = None
    doubleLow: float | None = None
    source: str | None = None


class CBondDailyImport(BaseModel):
    source: str = "manual"
    records: list[CBondDailyRecord] = Field(min_length=1)


class CBondCallEventRecord(BaseModel):
    id: str | None = None
    bondCode: str
    announceDate: str
    triggerDate: str | None = None
    status: str = "announced"
    callPrice: float | None = None
    lastTradeDate: str | None = None
    source: str | None = None


class CBondCallEventImport(BaseModel):
    source: str = "manual"
    records: list[CBondCallEventRecord] = Field(min_length=1)


def _dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()


@router.post("/terms")
def import_terms(request: CBondTermImport):
    try:
        return cbond.import_cbond_terms([_dump(item) for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/daily")
def import_daily(request: CBondDailyImport):
    try:
        return cbond.import_cbond_daily([_dump(item) for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/call-events")
def import_call_events(request: CBondCallEventImport):
    try:
        return cbond.import_call_events([_dump(item) for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/double-low")
def double_low(date: str, maxDoubleLow: float = 130.0, excludeCallRisk: bool = True, limit: int = 100):
    try:
        return cbond.double_low_pool(
            as_of_date=date,
            max_double_low=maxDoubleLow,
            exclude_call_risk=excludeCallRisk,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/call-risk")
def call_risk(date: str):
    try:
        return cbond.call_risk_monitor(date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
