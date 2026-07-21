from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.config import QUEUED_TASK_TIMEOUT_MINUTES
from ..services.maintenance import clear_local_history, cleanup_stale_queued

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class ClearHistoryRequest(BaseModel):
    dryRun: bool = False
    force: bool = False
    confirmation: str | None = None


@router.post("/clear-history")
def clear_history(request: ClearHistoryRequest):
    result = clear_local_history(dry_run=request.dryRun, force=request.force, confirmation=request.confirmation)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result


class CleanupQueuedRequest(BaseModel):
    maxQueuedMinutes: int = QUEUED_TASK_TIMEOUT_MINUTES
    dryRun: bool = False


@router.post("/cleanup-queued")
def cleanup_queued(request: CleanupQueuedRequest):
    try:
        result = cleanup_stale_queued(
            max_queued_minutes=request.maxQueuedMinutes,
            dry_run=request.dryRun,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result
