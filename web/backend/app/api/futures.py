from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..core.errors import NotFoundError
from ..services import futures

router = APIRouter(prefix="/api/futures", tags=["futures"])


class FuturesContractRecord(BaseModel):
    contractCode: str
    product: str | None = None
    exchange: str = "DCE"
    name: str | None = None
    multiplier: float | None = None
    marginRate: float | None = None
    tickSize: float | None = None
    deliveryMonth: str | None = None
    listedDate: str | None = None
    lastTradeDate: str | None = None
    source: str | None = None


class FuturesContractImport(BaseModel):
    source: str = "manual"
    records: list[FuturesContractRecord] = Field(min_length=1)


class FuturesDailyRecord(BaseModel):
    contractCode: str
    tradeDate: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    openInterest: float | None = None
    source: str | None = None


class FuturesDailyImport(BaseModel):
    source: str = "manual"
    records: list[FuturesDailyRecord] = Field(min_length=1)


class FuturesMainRuleRequest(BaseModel):
    product: str
    exchange: str = "DCE"
    ruleType: str = "open_interest"
    rollDaysBeforeExpiry: int = Field(default=0, ge=0)
    minOpenInterestDays: int = Field(default=1, ge=1)
    source: str = "manual"


class FuturesMainMappingRequest(BaseModel):
    product: str
    startDate: str
    endDate: str
    exchange: str | None = None
    source: str = "derived"


class FuturesFeeScheduleRequest(BaseModel):
    product: str
    exchange: str
    openRate: float = Field(default=0, ge=0)
    closeRate: float = Field(default=0, ge=0)
    closeTodayRate: float = Field(default=0, ge=0)
    perContract: float = Field(default=0, ge=0)
    slippageTicks: float = Field(default=0, ge=0)
    currency: str = "CNY"
    version: str
    source: str = "manual"


class FuturesContinuousRequest(BaseModel):
    product: str
    exchange: str
    startDate: str
    endDate: str
    adjustment: str = "backward_ratio"
    contracts: float = 1.0
    strictMetadata: bool = True


class TqSdkImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    startDate: str
    endDate: str
    durationSeconds: int = Field(default=86400, gt=0)
    tqAccount: str | None = None
    tqPassword: str | None = None


@router.post("/contracts")
def import_contracts(request: FuturesContractImport):
    try:
        return futures.import_contracts([item.model_dump() for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/daily")
def import_daily(request: FuturesDailyImport):
    try:
        return futures.import_daily_bars([item.model_dump() for item in request.records], source=request.source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/main-rules")
def set_main_rule(request: FuturesMainRuleRequest):
    try:
        return futures.set_main_rule(
            product=request.product,
            exchange=request.exchange,
            rule_type=request.ruleType,
            roll_days_before_expiry=request.rollDaysBeforeExpiry,
            min_open_interest_days=request.minOpenInterestDays,
            source=request.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/fee-schedules")
def set_fee_schedule(request: FuturesFeeScheduleRequest):
    try:
        return futures.set_fee_schedule(
            product=request.product,
            exchange=request.exchange,
            open_rate=request.openRate,
            close_rate=request.closeRate,
            close_today_rate=request.closeTodayRate,
            per_contract=request.perContract,
            slippage_ticks=request.slippageTicks,
            currency=request.currency,
            version=request.version,
            source=request.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fee-schedules/{exchange}/{product}")
def fee_schedule(exchange: str, product: str):
    try:
        item = futures.fee_schedule(product, exchange)
        if not item:
            raise HTTPException(status_code=404, detail="Futures fee schedule not found.")
        return item
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/continuous-contracts")
def build_continuous_contract(request: FuturesContinuousRequest):
    try:
        return futures.build_continuous_contract(
            product=request.product,
            exchange=request.exchange,
            start_date=request.startDate,
            end_date=request.endDate,
            adjustment=request.adjustment,
            contracts=request.contracts,
            strict_metadata=request.strictMetadata,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/continuous-contracts/{build_id}")
def continuous_contract(build_id: str):
    try:
        return futures.continuous_contract(build_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/main/{product}")
def main_contract(product: str, date: str, exchange: str | None = None):
    try:
        item = futures.main_contract(product, date, exchange)
        if not item:
            raise HTTPException(status_code=404, detail="Main contract not found.")
        return item
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agri-main")
def agri_main(date: str, products: str | None = None):
    try:
        product_list = [item.strip().upper() for item in products.split(",") if item.strip()] if products else None
        return futures.agri_main_monitor(date, product_list)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/main-mapping")
def refresh_main_mapping(request: FuturesMainMappingRequest):
    try:
        return futures.refresh_main_mapping(
            product=request.product,
            start_date=request.startDate,
            end_date=request.endDate,
            exchange=request.exchange,
            source=request.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tqsdk/import")
def import_tqsdk(request: TqSdkImportRequest):
    try:
        return futures.import_tqsdk_klines(
            symbols=request.symbols,
            start_date=request.startDate,
            end_date=request.endDate,
            duration_seconds=request.durationSeconds,
            tq_account=request.tqAccount,
            tq_password=request.tqPassword,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
