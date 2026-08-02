from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from .common import paged_items
from ..core.errors import LeanWebError, NotFoundError
from ..services import experiment_batches
from ..services import data_gateway, research_runs
from ..services.history_resources import delete_experiment_batch
from ..services.workflow_lineage import record_edge
from ..tasks.worker import dispatch_experiment_batch_task


router = APIRouter(prefix="/api/experiment-batches", tags=["experiment-batches"])


class ExperimentBatchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")


class ExperimentBatchCompareRequest(BaseModel):
    batchIds: list[str] = Field(min_length=2, max_length=10)
    metric: str = "sharpe"
    xParameter: str | None = None
    yParameter: str | None = None


def _payload(request: ExperimentBatchRequest) -> dict[str, Any]:
    payload = request.model_dump()
    payload.update(request.model_extra or {})
    if str(payload.get("kind") or "").lower() == "research":
        raise LeanWebError("research_batches_retired: use /api/research/runs")
    if str(payload.get("kind") or "").lower() == "optimization":
        raise LeanWebError("optimization_batches_moved: use /api/optimizations")
    source_research_id = str(payload.get("sourceResearchRunId") or "").strip()
    if source_research_id:
        if str(payload.get("kind") or "backtest") != "backtest":
            raise LeanWebError("Research handoff is only valid for backtest batches.")
        if not payload.get("dataScope"):
            raise LeanWebError("Research handoff requires dataScope.")
        source = research_runs.get_run(source_research_id)
        if source["status"] != "success":
            raise LeanWebError("Only successful research can seed a backtest batch.")
        resolved = data_gateway.resolve(payload["dataScope"])
        if data_gateway.scope_hash(source["scope"]) != resolved["scopeHash"]:
            raise LeanWebError("The batch dataScope does not match the source research run.")
        if source.get("data_fingerprint") and source["data_fingerprint"] != resolved["dataFingerprint"]:
            raise LeanWebError("Research data has changed; rerun research before creating the batch.")
        payload["scopeHash"] = resolved["scopeHash"]
        payload["dataFingerprint"] = resolved["dataFingerprint"]
        payload["parameters"] = {
            **dict(payload.get("parameters") or {}),
            "dataScope": resolved["scope"],
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": resolved["dataFingerprint"],
            "sourceResearchRunId": source_research_id,
        }
    return payload


@router.post("/preview")
def preview(request: ExperimentBatchRequest):
    try:
        return experiment_batches.preview(_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def batches(limit: int = 100, offset: int = 0, paged: bool = True):
    return paged_items(experiment_batches.list_batches(), limit=limit, offset=offset, paged=paged)


@router.post("/compare")
def compare(request: ExperimentBatchCompareRequest):
    try:
        return experiment_batches.compare_batches(
            request.batchIds,
            metric=request.metric,
            x_parameter=request.xParameter,
            y_parameter=request.yParameter,
        )
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def create(request: ExperimentBatchRequest):
    try:
        payload = _payload(request)
        batch = experiment_batches.create_batch(payload)
        if payload.get("sourceResearchRunId"):
            record_edge(
                parent_type="research_run",
                parent_id=str(payload["sourceResearchRunId"]),
                child_type="experiment_batch",
                child_id=batch["id"],
                relation="validated_by",
                contract=payload.get("dataScope"),
                details={
                    "scopeHash": payload.get("scopeHash"),
                    "dataFingerprint": payload.get("dataFingerprint"),
                },
            )
        dispatch_experiment_batch_task.apply_async(args=[batch["id"]], queue="default")
        return experiment_batches.detail(batch["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{batch_id}")
def detail(batch_id: str):
    try:
        return experiment_batches.detail(batch_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{batch_id}/walk-forward-certificate")
def walk_forward_certificate(batch_id: str):
    try:
        return experiment_batches.walk_forward_certificate(batch_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{batch_id}")
def delete(batch_id: str):
    try:
        return delete_experiment_batch(batch_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{batch_id}/cancel")
def cancel(batch_id: str):
    try:
        return experiment_batches.cancel(batch_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{batch_id}/retry-failed")
def retry_failed(batch_id: str):
    try:
        batch = experiment_batches.retry_failed(batch_id)
        dispatch_experiment_batch_task.apply_async(args=[batch_id], queue="default")
        return batch
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{batch_id}/restart")
def restart_cancelled(batch_id: str):
    try:
        batch = experiment_batches.restart_cancelled(batch_id)
        dispatch_experiment_batch_task.apply_async(args=[batch_id], queue="default")
        return batch
    except (LeanWebError, NotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{batch_id}/export.csv")
def export(batch_id: str):
    try:
        body = experiment_batches.export_csv(batch_id)
        return Response(body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="batch-{batch_id}.csv"'})
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
