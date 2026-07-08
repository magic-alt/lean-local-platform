from typing import Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import pit_data
from ..services.tushare_adapter import TushareAdapter

router = APIRouter(prefix="/api/pit", tags=["pit-data"])

INDEX_CODE_ALIASES = {
    "000300": "CSI300",
    "399300": "CSI300",
    "CSI300": "CSI300",
    "CSI_300": "CSI300",
    "CSI-300": "CSI300",
    "沪深300": "CSI300",
    "000905": "CSI500",
    "CSI500": "CSI500",
    "CSI_500": "CSI500",
    "CSI-500": "CSI500",
    "中证500": "CSI500",
    "000852": "CSI1000",
    "CSI1000": "CSI1000",
    "CSI_1000": "CSI1000",
    "CSI-1000": "CSI1000",
    "中证1000": "CSI1000",
    "000016": "SSE50",
    "SSE50": "SSE50",
    "上证50": "SSE50",
    "000688": "STAR50",
    "STAR50": "STAR50",
    "STAR_50": "STAR50",
    "科创50": "STAR50",
}

TUSHARE_INDEX_CODES = {
    "CSI300": "000300.SH",
    "CSI500": "000905.SH",
    "CSI1000": "000852.SH",
    "SSE50": "000016.SH",
    "STAR50": "000688.SH",
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


@router.get("/index-members/{universe_code}/as-of/{as_of_date}/tushare")
def index_members_tushare_as_of(universe_code: str, as_of_date: str, lookbackDays: int = 45):
    try:
        normalized = _index_code(universe_code)
        tushare_code = TUSHARE_INDEX_CODES.get(normalized, universe_code)
        end_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        start_date = end_date - timedelta(days=max(1, min(365, lookbackDays)))
        rows = TushareAdapter().index_weight_rows(tushare_code, start_date.isoformat(), end_date.isoformat())
        eligible = [row for row in rows if row["trade_date"] <= as_of_date]
        if not eligible:
            payload = pit_data.index_members_as_of_payload(normalized, as_of_date, requested_universe=universe_code)
            payload.update({"source": "tushare:index_weight", "fetchedDate": None, "imported": {"count": 0}})
            return payload
        latest_date = max(row["trade_date"] for row in eligible)
        records = [
            {
                "universe_code": normalized,
                "symbol": row["symbol"],
                "name": None,
                "start_date": latest_date,
                "end_date": None,
                "announce_date": latest_date,
                "effective_date": latest_date,
                "listed_date": None,
                "industry": None,
                "weight": row.get("weight"),
                "source": "tushare:index_weight",
            }
            for row in eligible
            if row["trade_date"] == latest_date
        ]
        imported = pit_data.import_index_members(records, source="tushare:index_weight")
        payload = pit_data.index_members_as_of_payload(normalized, as_of_date, requested_universe=universe_code)
        payload.update({"source": "tushare:index_weight", "fetchedDate": latest_date, "imported": imported})
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
