from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.maintenance import clear_local_history

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


class ClearHistoryRequest(BaseModel):
    dryRun: bool = False
    force: bool = False


@router.post("/clear-history")
def clear_history(request: ClearHistoryRequest):
    result = clear_local_history(dry_run=request.dryRun, force=request.force)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result
