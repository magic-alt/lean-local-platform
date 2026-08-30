from __future__ import annotations


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..services import qlib_import_v2, qlib_promotion, research_runs

router = APIRouter(prefix="/api/research", tags=["research"])


class QlibImportRequest(BaseModel):
    schemaVersion: str
    importType: str
    name: str | None = None
    model_config = ConfigDict(extra="allow")


class QlibLeanValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    leanBacktestRunId: str = Field(min_length=1, max_length=64)


@router.post("/imports/qlib")
def import_qlib_run(request: QlibImportRequest):
    try:
        payload = request.model_dump(exclude_none=True)
        if (
            payload.get("schemaVersion") != qlib_import_v2.SCHEMA_VERSION
            or payload.get("importType") != qlib_import_v2.IMPORT_TYPE
        ):
            raise ValueError(
                "Only Artifact Contract v2 is supported: schemaVersion=2.0, importType=QLIB_RESEARCH_BUNDLE"
            )
        return research_runs.import_qlib_run(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/runs/{run_id}/lean-validation")
def record_qlib_lean_validation(run_id: str, request: QlibLeanValidationRequest):
    try:
        return qlib_promotion.record_lean_validation(
            run_id, lean_backtest_run_id=request.leanBacktestRunId
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
