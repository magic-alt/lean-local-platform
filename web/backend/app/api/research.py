from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..services import qlib_import_v2, qlib_promotion, research_runs

router = APIRouter(prefix="/api/research", tags=["research"])

_RETIRED_RESEARCH_DETAIL = (
    "Platform-owned research execution and notebook workspace routes are retired. "
    "Run research in qlib-platform and hand results back through Artifact Contract v2."
)


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


def _retired_research_route() -> None:
    """Keep retired HTTP surfaces fail-closed and stable behind the SPA mount."""
    raise HTTPException(status_code=404, detail=_RETIRED_RESEARCH_DETAIL)


@router.api_route(
    "/templates",
    methods=["GET"],
    include_in_schema=False,
)
def retired_templates():
    _retired_research_route()


@router.api_route(
    "/runs",
    methods=["GET", "POST"],
    include_in_schema=False,
)
def retired_runs_collection():
    _retired_research_route()


@router.api_route(
    "/runs/preview",
    methods=["POST"],
    include_in_schema=False,
)
def retired_runs_preview():
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}",
    methods=["GET", "DELETE"],
    include_in_schema=False,
)
def retired_run_detail(run_id: str):
    del run_id
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}/cancel",
    methods=["POST"],
    include_in_schema=False,
)
def retired_run_cancel(run_id: str):
    del run_id
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}/retry",
    methods=["POST"],
    include_in_schema=False,
)
def retired_run_retry(run_id: str):
    del run_id
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}/backtest-draft",
    methods=["GET"],
    include_in_schema=False,
)
def retired_run_backtest_draft(run_id: str):
    del run_id
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}/export.csv",
    methods=["GET"],
    include_in_schema=False,
)
def retired_run_export(run_id: str):
    del run_id
    _retired_research_route()


@router.api_route(
    "/runs/{run_id}/artifacts/{artifact_key}",
    methods=["GET"],
    include_in_schema=False,
)
def retired_run_artifact(run_id: str, artifact_key: str):
    del run_id, artifact_key
    _retired_research_route()


@router.api_route(
    "/workspaces",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def retired_workspaces_collection():
    _retired_research_route()


@router.api_route(
    "/workspaces/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def retired_workspace_path(path: str):
    del path
    _retired_research_route()
