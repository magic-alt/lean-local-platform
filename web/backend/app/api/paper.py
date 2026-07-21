from typing import Any

from celery import chain
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..services import paper as paper_service
from ..core.errors import NotFoundError
from ..services.history_resources import delete_paper_session
from ..tasks.worker import (
    fail_paper_walkforward_task,
    finalize_paper_walkforward_task,
    mark_paper_walkforward_running_task,
    run_backtest_task,
)

router = APIRouter(prefix="/api/paper", tags=["paper"])


class PaperSessionCreate(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    projectId: str | None = None
    symbol: str | None = None
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
    sourceBacktestId: str | None = None
    startDate: str | None = None
    autoAdvance: bool = True
    mode: str | None = None


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
        payload = request.model_dump()
        requested_mode = str(request.mode or "").strip().lower()
        if requested_mode not in {"", "lean_walkforward", "signal_simulation"}:
            raise ValueError("Paper mode must be lean_walkforward or signal_simulation.")
        if requested_mode == "lean_walkforward" or request.sourceBacktestId or request.projectId:
            if not request.sourceBacktestId or not request.projectId:
                raise ValueError("LEAN Paper requires both a Project and a trusted Backtest.")
            payload["mode"] = "lean_walkforward"
        else:
            payload["mode"] = "signal_simulation"
        return paper_service.create_session(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates")
def candidates(projectId: str):
    return paper_service.trusted_backtest_candidates(projectId)


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
        "runs": paper_service.list_walkforward_runs(session_id),
    }


@router.delete("/{session_id}")
def delete(session_id: str):
    try:
        return delete_paper_session(session_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
        session = paper_service.get_session(session_id)
        if not session:
            raise KeyError("Paper session not found.")
        if session.get("mode") == "lean_walkforward":
            paper_run = paper_service.create_walkforward_run(session_id, request.tradeDate)
            workflow = chain(
                mark_paper_walkforward_running_task.si(paper_run["id"]),
                run_backtest_task.si(paper_run["task_id"], paper_run["backtest_run_id"]),
                finalize_paper_walkforward_task.si(paper_run["id"]),
            )
            workflow.apply_async(link_error=fail_paper_walkforward_task.s(paper_run["id"]))
            return paper_run
        return paper_service.match_daily_orders(session_id, request.tradeDate, auto_signal=request.autoSignal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper session not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/replay")
def replay(session_id: str, request: PaperReplayRequest):
    try:
        session = paper_service.get_session(session_id)
        if session and session.get("mode") == "lean_walkforward":
            if request.startDate != request.endDate:
                raise ValueError("LEAN Paper replay is sequential; queue one trading day at a time.")
            return run_day(session_id, PaperRunDayRequest(tradeDate=request.startDate, autoSignal=False))
        return paper_service.run_replay(session_id, request.startDate, request.endDate, auto_signal=request.autoSignal)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper session not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}/runs")
def walkforward_runs(session_id: str):
    if not paper_service.get_session(session_id):
        raise HTTPException(status_code=404, detail="Paper session not found.")
    return paper_service.list_walkforward_runs(session_id)
