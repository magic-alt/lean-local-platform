from fastapi import APIRouter, HTTPException

from ..core.errors import LeanWebError
from ..lean import normalize_symbol, parse_date
from ..services.ashare_repository import (
    get_import_batch,
    is_tradeable,
    list_import_batches,
    trade_status_as_of,
    universe_as_of,
)

router = APIRouter(prefix="/api", tags=["ashare"])


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


@router.get("/ashare/universe/{universe_code}")
def ashare_universe(universe_code: str, date: str):
    as_of_date = _date(date)
    items = universe_as_of(universe_code.upper(), as_of_date)
    return {"universe": universe_code.upper(), "date": as_of_date, "items": items, "count": len(items)}


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
