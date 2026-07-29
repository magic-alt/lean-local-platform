from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .common import paged_items
from ..core.config import DEFAULT_DOCKER_IMAGE
from ..core.errors import LeanWebError, NotFoundError
from ..db import db, utc_now
from ..domain.data_scope import DataScope
from ..repositories.backtest_repository import get_backtest
from ..services import data_gateway, experiment_batches
from ..services.history_resources import delete_experiment_batch
from ..services.workflow_lineage import record_edge
from ..tasks.worker import dispatch_experiment_batch_task


router = APIRouter(prefix="/api/optimizations", tags=["optimization"])


class OptimizationExecution(BaseModel):
    cash: float = Field(default=100000, gt=0)
    benchmarkSymbol: str | None = None
    feeModel: str | None = None
    slippageModel: str | None = None
    dockerImage: str = DEFAULT_DOCKER_IMAGE


class WalkForwardConfig(BaseModel):
    trainYears: int = Field(default=3, ge=1, le=20)
    testYears: int = Field(default=1, ge=1, le=10)
    stepYears: int = Field(default=1, ge=1, le=10)
    validationMonths: int | None = Field(default=None, ge=1, le=60)


class OptimizationRequest(BaseModel):
    name: str = Field(default="Optimization", min_length=1, max_length=255)
    mode: Literal[
        "single_symbol_grid",
        "universe_robust",
        "walk_forward",
        "multi_strategy",
    ] = "single_symbol_grid"
    projectIds: list[str] = Field(min_length=1, max_length=10)
    dataScope: DataScope
    execution: OptimizationExecution = Field(default_factory=OptimizationExecution)
    fixedParametersByProject: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parameterGrids: dict[str, dict[str, Any]] = Field(default_factory=dict)
    objective: Literal["sharpe", "return", "drawdown"] = "sharpe"
    minCoverage: float = Field(default=0.8, ge=0.5, le=1)
    maxCandidates: int = Field(default=200, ge=1, le=1000)
    walkForward: WalkForwardConfig | None = None
    sourceBacktestRunId: str | None = None


class OptimizationCompareRequest(BaseModel):
    optimizationIds: list[str] = Field(min_length=2, max_length=10)
    metric: Literal["sharpe", "return", "drawdown", "trades"] = "sharpe"
    xParameter: str | None = None
    yParameter: str | None = None


def _ensure_optimization(batch: dict[str, Any]) -> dict[str, Any]:
    if str(batch.get("kind") or "") != "optimization":
        raise NotFoundError("Optimization run not found.")
    return batch


def _config(request: OptimizationRequest) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = data_gateway.resolve(request.dataScope)
    scope = resolved["scope"]
    selection = scope["selection"]
    selection_type = str(selection["type"])
    values = [str(value).strip().upper() for value in selection.get("values") or [] if str(value).strip()]
    if selection_type == "all":
        raise LeanWebError("Optimization requires explicit symbols/products or a point-in-time universe.")
    if not values:
        raise LeanWebError("Optimization data scope has no selected symbols or universe.")
    if request.mode == "single_symbol_grid" and (
        selection_type not in {"symbols", "products"} or len(values) != 1
    ):
        raise LeanWebError("single_symbol_grid requires exactly one explicit symbol or product.")
    if request.mode == "universe_robust" and selection_type not in {"universe", "symbols"}:
        raise LeanWebError("universe_robust requires a point-in-time universe or an explicit symbol list.")
    if request.mode == "multi_strategy" and len(request.projectIds) < 2:
        raise LeanWebError("multi_strategy requires at least two projects.")
    asset = scope["asset"]
    time = scope["time"]
    execution = request.execution.model_dump(exclude_none=True)
    config: dict[str, Any] = {
        "kind": "optimization",
        "name": request.name,
        "mode": request.mode,
        "projectIds": list(dict.fromkeys(request.projectIds)),
        "assetClass": asset["assetClass"],
        "market": asset["market"],
        "venue": asset.get("venue") or asset["market"],
        "resolution": asset["resolution"],
        "dataType": asset["dataType"],
        "start": time.get("startDate"),
        "end": time.get("endDate"),
        "asOfDate": time.get("asOfDate"),
        "source": resolved["source"],
        "providerSource": scope["provider"]["source"],
        "allowResearchSource": scope["provider"]["allowResearchSource"],
        "parameters": {"adjust": scope["price"]["adjust"]},
        "fixedParametersByProject": request.fixedParametersByProject,
        "parameterGrids": request.parameterGrids,
        "objective": request.objective,
        "minCoverage": request.minCoverage,
        "maxCandidates": request.maxCandidates,
        "dataScope": scope,
        "scopeHash": resolved["scopeHash"],
        "dataFingerprint": resolved["dataFingerprint"],
        "datasetVersion": resolved["dataFingerprint"],
        "universeVersion": resolved["scopeHash"],
        "adjustmentContract": scope["price"]["adjust"],
        "featurePipelineVersion": "strategy-native-v1",
        **execution,
    }
    if selection_type == "universe":
        if len(values) != 1:
            raise LeanWebError("Universe optimization requires one universe code.")
        config["universeCode"] = values[0]
    else:
        config["symbols"] = values
    if request.walkForward:
        config.update(request.walkForward.model_dump(exclude_none=True))
    return config, resolved


@router.post("/preview")
def preview(request: OptimizationRequest):
    try:
        config, resolved = _config(request)
        report = experiment_batches.preview(config)
        return {**report, "scopeHash": resolved["scopeHash"], "dataFingerprint": resolved["dataFingerprint"]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_optimizations(limit: int = 100, offset: int = 0, paged: bool = True):
    with db() as connection:
        rows = connection.execute(
            """
            select * from experiment_batches
            where kind='optimization' and archived_at is null
            order by created_at desc
            """
        ).fetchall()
    from ..db import rows_to_dicts

    return paged_items(rows_to_dicts(rows), limit=limit, offset=offset, paged=paged)


@router.post("")
def create_optimization(request: OptimizationRequest):
    try:
        config, resolved = _config(request)
        source = None
        if request.sourceBacktestRunId:
            source = get_backtest(request.sourceBacktestRunId)
            if source is None:
                raise NotFoundError("Source backtest run not found.")
            if source.get("status") != "success":
                raise LeanWebError("Only a successful backtest can seed an optimization.")
            if str(source.get("project_id") or "") not in request.projectIds:
                raise LeanWebError("The source backtest project must be included in projectIds.")
            source_parameters = source.get("parameters") or {}
            source_fingerprint = source_parameters.get("dataFingerprint")
            if source_fingerprint and source_fingerprint != resolved["dataFingerprint"]:
                raise LeanWebError("Optimization data scope does not match the source backtest fingerprint.")
        batch = experiment_batches.create_batch(config)
        with db() as connection:
            connection.execute(
                """
                update experiment_batches
                set objective_metric=?,source_backtest_run_id=?,scope_hash=?,data_fingerprint=?
                where id=?
                """,
                (
                    request.objective,
                    request.sourceBacktestRunId,
                    resolved["scopeHash"],
                    resolved["dataFingerprint"],
                    batch["id"],
                ),
            )
        if source:
            record_edge(
                parent_type="backtest_run",
                parent_id=source["id"],
                child_type="optimization",
                child_id=batch["id"],
                relation="seeded",
                contract=resolved["scope"],
                details={"scopeHash": resolved["scopeHash"], "dataFingerprint": resolved["dataFingerprint"]},
            )
        dispatch_experiment_batch_task.apply_async(args=[batch["id"]], queue="default")
        return _ensure_optimization(experiment_batches.detail(batch["id"]))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/compare")
def compare(request: OptimizationCompareRequest):
    try:
        for optimization_id in request.optimizationIds:
            _ensure_optimization(experiment_batches.detail(optimization_id))
        return experiment_batches.compare_batches(
            request.optimizationIds,
            metric=request.metric,
            x_parameter=request.xParameter,
            y_parameter=request.yParameter,
        )
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{optimization_id}")
def detail(optimization_id: str):
    try:
        return _ensure_optimization(experiment_batches.detail(optimization_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{optimization_id}/cancel")
def cancel(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        return experiment_batches.cancel(optimization_id)
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{optimization_id}/retry-failed")
def retry_failed(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        result = experiment_batches.retry_failed(optimization_id)
        dispatch_experiment_batch_task.apply_async(args=[optimization_id], queue="default")
        return result
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{optimization_id}/restart")
def restart(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        result = experiment_batches.restart_cancelled(optimization_id)
        dispatch_experiment_batch_task.apply_async(args=[optimization_id], queue="default")
        return result
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{optimization_id}/archive")
def archive(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        with db() as connection:
            connection.execute(
                "update experiment_batches set archived_at=? where id=?",
                (utc_now(), optimization_id),
            )
        return {"archived": True, "id": optimization_id}
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{optimization_id}")
def delete(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        return delete_experiment_batch(optimization_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{optimization_id}/export.csv")
def export(optimization_id: str):
    try:
        _ensure_optimization(experiment_batches.detail(optimization_id))
        body = experiment_batches.export_csv(optimization_id)
        return Response(
            body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="optimization-{optimization_id}.csv"'},
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
