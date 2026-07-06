from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import pit_data

router = APIRouter(prefix="/api/pit", tags=["pit-data"])

INDEX_CODE_ALIASES = {
    "000300": "CSI300",
    "399300": "CSI300",
    "CSI300": "CSI300",
    "CSI_300": "CSI300",
    "CSI-300": "CSI300",
    "沪深300": "CSI300",
}


def _index_code(value: str) -> str:
    code = value.strip().upper()
    return INDEX_CODE_ALIASES.get(code, code)


class FinancialStatementRecord(BaseModel):
    symbol: str
    statementType: str = "metrics"
    reportDate: str
    announceDate: str
    effectiveDate: str | None = None
    fiscalPeriod: str | None = None
    currency: str = "CNY"
    fields: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None


class FinancialStatementImport(BaseModel):
    source: str = "manual"
    records: list[FinancialStatementRecord] = Field(min_length=1)


class FinancialFactorRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    asOfDate: str
    fields: list[str] | None = None


class IndexMemberRecord(BaseModel):
    universeCode: str
    symbol: str
    name: str | None = None
    startDate: str
    endDate: str | None = None
    announceDate: str | None = None
    effectiveDate: str | None = None
    listedDate: str | None = None
    industry: str | None = None
    weight: float | None = None
    source: str | None = None


class IndexMemberImport(BaseModel):
    source: str = "manual"
    records: list[IndexMemberRecord] = Field(min_length=1)


@router.post("/financials")
def import_financials(request: FinancialStatementImport):
    try:
        records = [
            {
                "symbol": item.symbol,
                "statement_type": item.statementType,
                "report_date": item.reportDate,
                "announce_date": item.announceDate,
                "effective_date": item.effectiveDate,
                "fiscal_period": item.fiscalPeriod,
                "currency": item.currency,
                "fields": item.fields,
                "source": item.source or request.source,
            }
            for item in request.records
        ]
        return pit_data.import_financial_statements(records, source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/financials/{symbol}/as-of/{as_of_date}")
def financials_as_of(symbol: str, as_of_date: str, statementType: str | None = None):
    try:
        return {
            "symbol": symbol,
            "asOfDate": as_of_date,
            "items": pit_data.financial_statements_as_of(symbol, as_of_date, statementType),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/financial-factors")
def financial_factors(request: FinancialFactorRequest):
    try:
        return {
            "asOfDate": request.asOfDate,
            "items": pit_data.financial_factors_as_of(request.symbols, request.asOfDate, request.fields),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/index-members")
def import_index_members(request: IndexMemberImport):
    try:
        records = [
            {
                "universe_code": _index_code(item.universeCode),
                "symbol": item.symbol,
                "name": item.name,
                "start_date": item.startDate,
                "end_date": item.endDate,
                "announce_date": item.announceDate,
                "effective_date": item.effectiveDate,
                "listed_date": item.listedDate,
                "industry": item.industry,
                "weight": item.weight,
                "source": item.source or request.source,
            }
            for item in request.records
        ]
        return pit_data.import_index_members(records, source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/index-members/{universe_code}/as-of/{as_of_date}")
def index_members_as_of(universe_code: str, as_of_date: str):
    try:
        normalized = _index_code(universe_code)
        return pit_data.index_members_as_of_payload(normalized, as_of_date, requested_universe=universe_code)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
