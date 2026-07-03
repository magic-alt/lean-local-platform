from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import paper as paper_service

router = APIRouter(prefix="/api/paper", tags=["paper"])


class PaperSessionCreate(BaseModel):
    name: str | None = None
    projectId: str | None = None
    symbol: str
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    cash: float = Field(default=100000, gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class PaperStatusUpdate(BaseModel):
    status: str


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

