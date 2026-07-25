from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ..core.errors import LeanWebError, NotFoundError
from ..services import experiment_batches
from ..services.history_resources import delete_experiment_batch
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
    return payload


@router.post("/preview")
def preview(request: ExperimentBatchRequest):
    try:
        return experiment_batches.preview(_payload(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def batches():
    return experiment_batches.list_batches()


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
        batch = experiment_batches.create_batch(_payload(request))
        dispatch_experiment_batch_task.apply_async(args=[batch["id"]], queue="default")
        return experiment_batches.detail(batch["id"])
    except LeanWebError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{batch_id}")
def detail(batch_id: str):
    try:
        return experiment_batches.detail(batch_id)
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
