from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import pit_data
from ..core.errors import LeanWebError
from ..lean_engine.symbols import normalize_symbol, parse_date
from ..services.ashare_repository import (
    adjustment_factors,
    corporate_actions,
    get_import_batch,
    import_adjustment_factors,
    import_security_master,
    import_trade_status,
    is_tradeable,
    list_import_batches,
    reference_data_coverage,
    trade_status_as_of,
    upsert_corporate_actions,
)
from ..services.tushare_adapter import import_tushare_stock_basic, import_tushare_trade_calendar

router = APIRouter(prefix="/api", tags=["ashare"])


class SecurityMasterRecord(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    listedDate: str
    delistedDate: str | None = None
    status: str = "listed"
    isSt: bool = False
    industry: str | None = None
    concepts: list[str] = Field(default_factory=list)
    source: str | None = None


class SecurityMasterImport(BaseModel):
    source: str = "manual"
    universeCode: str = "ALL_A"
    records: list[SecurityMasterRecord] = Field(min_length=1)


class TradeStatusRecord(BaseModel):
    symbol: str
    tradeDate: str
    isSuspended: bool = False
    limitUp: float | None = None
    limitDown: float | None = None
    isLimitUp: bool = False
    isLimitDown: bool = False
    isOneWordLimitUp: bool = False
    isOneWordLimitDown: bool = False
    canBuy: bool | None = None
    canSell: bool | None = None
    isSt: bool = False


class TradeStatusImport(BaseModel):
    source: str = "manual"
    records: list[TradeStatusRecord] = Field(min_length=1)


class AdjustmentFactorRecord(BaseModel):
    symbol: str
    tradeDate: str
    adjFactor: float


class AdjustmentFactorImport(BaseModel):
    source: str = "manual"
    records: list[AdjustmentFactorRecord] = Field(min_length=1)


class CorporateActionRecord(BaseModel):
    symbol: str
    exDate: str
    actionType: str = "dividend"
    cashDividend: float | None = None
    stockDividend: float | None = None
    splitRatio: float | None = None
    allotmentRatio: float | None = None
    allotmentPrice: float | None = None
    source: str | None = None


class CorporateActionImport(BaseModel):
    source: str = "manual"
    records: list[CorporateActionRecord] = Field(min_length=1)


class TushareStockBasicImport(BaseModel):
    listStatuses: list[str] = Field(default_factory=lambda: ["L", "D", "P"])
    universeCode: str = "ALL_A"


class TushareTradeCalendarImport(BaseModel):
    startDate: str
    endDate: str
    exchange: str = "SSE"


def _date(value: str) -> str:
    try:
        return parse_date(value).isoformat()
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/data/batches")
def import_batches():
    return {"items": list_import_batches()}


@router.get("/data/batches/{batch_id}")
def import_batch(batch_id: str):
    batch = get_import_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Data import batch not found.")
    return batch


@router.get("/data/qa/{batch_id}")
def import_batch_qa(batch_id: str):
    batch = get_import_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Data import batch not found.")
    return {
        "batchId": batch_id,
        "status": batch.get("status"),
        "error": batch.get("error"),
        "qaReport": batch.get("qa_report") or {},
    }


@router.post("/ashare/securities/import")
def import_securities(request: SecurityMasterImport):
    try:
        records = [
            {
                "symbol": item.symbol,
                "name": item.name,
                "exchange": item.exchange,
                "listed_date": item.listedDate,
                "delisted_date": item.delistedDate,
                "status": item.status,
                "is_st": item.isSt,
                "industry": item.industry,
                "concepts": item.concepts,
                "source": item.source or request.source,
            }
            for item in request.records
        ]
        return import_security_master(records, source=request.source, universe_code=request.universeCode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ashare/tushare/securities/import")
def import_tushare_securities(request: TushareStockBasicImport):
    try:
        return import_tushare_stock_basic(list_statuses=request.listStatuses, universe_code=request.universeCode)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ashare/tushare/trade-calendar/import")
def import_tushare_calendar(request: TushareTradeCalendarImport):
    try:
        return import_tushare_trade_calendar(
            start_date=request.startDate,
            end_date=request.endDate,
            exchange=request.exchange,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ashare/trade-status/import")
def import_status(request: TradeStatusImport):
    try:
        return import_trade_status([item.model_dump() for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ashare/adjustment-factors/import")
def import_adjustments(request: AdjustmentFactorImport):
    try:
        return import_adjustment_factors([item.model_dump() for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ashare/adjustment-factors/{symbol}")
def ashare_adjustments(symbol: str, start: str | None = None, end: str | None = None):
    try:
        ticker = normalize_symbol(symbol, "china")
        return {"symbol": ticker, "items": adjustment_factors(ticker, start, end)}
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/ashare/corporate-actions/import")
def import_actions(request: CorporateActionImport):
    try:
        return upsert_corporate_actions([item.model_dump() for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ashare/corporate-actions/{symbol}")
def ashare_actions(symbol: str, start: str | None = None, end: str | None = None):
    try:
        ticker = normalize_symbol(symbol, "china")
        return {"symbol": ticker, "items": corporate_actions(ticker, start, end)}
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ashare/reference-data/coverage")
def ashare_reference_data_coverage(indexCode: str = "CSI300"):
    return reference_data_coverage(indexCode)


@router.get("/ashare/universe/{universe_code}")
def ashare_universe(universe_code: str, date: str):
    as_of_date = _date(date)
    payload = pit_data.index_members_as_of_payload(universe_code.upper(), as_of_date, requested_universe=universe_code)
    return {**payload, "date": as_of_date}


@router.get("/ashare/universe/{universe_code}/tradable")
def ashare_tradable_universe(universe_code: str, date: str, minListedDays: int = 0, excludeSt: bool = True):
    as_of_date = _date(date)
    payload = pit_data.index_members_as_of_payload(
        universe_code.upper(),
        as_of_date,
        requested_universe=universe_code,
        tradable=True,
        min_listed_days=minListedDays,
        exclude_st=excludeSt,
    )
    return {**payload, "date": as_of_date}


@router.get("/ashare/securities/{symbol}/status")
def ashare_security_status(symbol: str, date: str):
    try:
        ticker = normalize_symbol(symbol, "china")
        trade_date = _date(date)
        status = trade_status_as_of([ticker], trade_date).get(ticker)
        can_buy, buy_reason = is_tradeable(ticker, trade_date, "buy")
        can_sell, sell_reason = is_tradeable(ticker, trade_date, "sell")
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "symbol": ticker,
        "date": trade_date,
        "status": status,
        "canBuy": can_buy,
        "buyReason": buy_reason,
        "canSell": can_sell,
        "sellReason": sell_reason,
    }
