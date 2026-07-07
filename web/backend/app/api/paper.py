from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..services import paper as paper_service

router = APIRouter(prefix="/api/paper", tags=["paper"])


class PaperSessionCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    projectId: str | None = None
    symbol: str
    symbols: list[str] | str | None = None
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    cash: float = Field(default=100000, gt=0)
    executionPolicy: str | None = None
    allowSameDayClose: bool = False
    benchmarkSymbol: str | None = None
    maxPositions: int | None = Field(default=None, ge=0)
    maxPositionWeight: float | None = Field(default=None, ge=0, le=1)
    minCash: float | None = Field(default=None, ge=0)
    blacklist: list[str] | str | None = None
    watchlist: list[str] | str | None = None
    observeOnlySymbols: list[str] | str | None = None
    allowStBuy: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)


class PaperStatusUpdate(BaseModel):
    status: str


class PaperSignalCreate(BaseModel):
    tradeDate: str
    side: str
    symbol: str | None = None
    targetPercent: float | None = None
    strength: float | None = None
    reason: str | None = None
    source: str = "manual"


class PaperRunDayRequest(BaseModel):
    tradeDate: str
    autoSignal: bool = True


class PaperReplayRequest(BaseModel):
    startDate: str
    endDate: str
    autoSignal: bool = True


@router.get("")
def list_sessions():
    return paper_service.list_sessions()


@router.post("")
def create_session(request: PaperSessionCreate):
    try:
        return paper_service.create_session(request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/status")
def update_status(session_id: str, request: PaperStatusUpdate):
    try:
        session = paper_service.update_session_status(session_id, request.status)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not session:
        raise HTTPException(status_code=404, detail="Paper session not found.")
    return session


@router.get("/{session_id}")
def detail(session_id: str):
    session = paper_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Paper session not found.")
    return {
        **session,
        "signals": paper_service.list_signals(session_id),
        "orders": paper_service.list_orders(session_id),
        "positions": paper_service.list_positions(session_id),
        "snapshots": paper_service.list_snapshots(session_id),
    }


@router.get("/{session_id}/signals")
def signals(session_id: str):
    return paper_service.list_signals(session_id)


@router.post("/{session_id}/signals")
def create_signal(session_id: str, request: PaperSignalCreate):
    try:
        return paper_service.create_signal(
            session_id,
            trade_date=request.tradeDate,
            side=request.side,
            symbol=request.symbol,
            target_percent=request.targetPercent,
            strength=request.strength,
            reason=request.reason,
            source=request.source,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper session not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/orders")
def orders(session_id: str):
    return paper_service.list_orders(session_id)


@router.get("/{session_id}/positions")
def positions(session_id: str):
    return paper_service.list_positions(session_id)


@router.get("/{session_id}/snapshots")
def snapshots(session_id: str):
    return paper_service.list_snapshots(session_id)


@router.get("/{session_id}/reports")
def reports(session_id: str, light: bool = False, limit: int = 500, offset: int = 0, paged: bool = False):
    items = paper_service.list_daily_reports(session_id)
    if light:
        items = [
            {
                "id": item.get("id"),
                "sessionId": item.get("session_id") or item.get("sessionId"),
                "tradeDate": item.get("tradeDate") or item.get("trade_date"),
                "executionPolicy": item.get("executionPolicy"),
                "nav": item.get("nav") or item.get("NAV"),
                "benchmarkSymbol": item.get("benchmarkSymbol"),
                "benchmarkReturn": item.get("benchmarkReturn"),
                "qaGateStatus": item.get("qaGateStatus"),
                "warnings": item.get("warnings") or [],
                "rejectReasons": item.get("rejectReasons") or [],
                "hasFingerprint": bool(item.get("fingerprint")),
                "createdAt": item.get("created_at") or item.get("createdAt"),
            }
            for item in items
        ]
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    sliced = items[bounded_offset : bounded_offset + bounded_limit]
    if paged or light:
        return {"items": sliced, "count": len(items), "limit": bounded_limit, "offset": bounded_offset}
    return sliced


@router.get("/{session_id}/reports/{trade_date}")
def report(session_id: str, trade_date: str):
    item = paper_service.get_daily_report(session_id, trade_date)
    if not item:
        raise HTTPException(status_code=404, detail="Paper daily report not found.")
    return item


@router.post("/{session_id}/run-day")
def run_day(session_id: str, request: PaperRunDayRequest):
    try:
        return paper_service.match_daily_orders(session_id, request.tradeDate, auto_signal=request.autoSignal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper session not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/replay")
def replay(session_id: str, request: PaperReplayRequest):
    try:
        return paper_service.run_replay(session_id, request.startDate, request.endDate, auto_signal=request.autoSignal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper session not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
