from fastapi import APIRouter, Header, HTTPException, Query

from .common import PageEnvelope
from ..services.integrated_workflow import (
    workflow_compare as integrated_workflow_compare,
    workflow_explain as integrated_workflow_explain,
    workflow_plan as integrated_workflow_plan,
    workflow_resume as integrated_workflow_resume,
    workflow_status as integrated_workflow_status,
)
from ..services.workflows import list_verifications, list_workflows, verification_detail, workflow_detail
from ..services.workflow_lineage import graph

router = APIRouter(prefix="/api", tags=["workflows"])


def _integrated_call(call):
    try:
        return call()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Integrated workflow not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/workflows", response_model=PageEnvelope)
def workflows(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
):
    return list_workflows(limit=limit, offset=offset, status=status)


@router.get("/workflows/{workflow_id}")
def workflow(workflow_id: str):
    try:
        return workflow_detail(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc


@router.get("/integrated-workflows/{import_id}/status")
def integrated_status(import_id: str):
    return _integrated_call(lambda: integrated_workflow_status(import_id))


@router.get("/integrated-workflows/{import_id}/plan")
def integrated_plan(import_id: str):
    return _integrated_call(lambda: integrated_workflow_plan(import_id))


@router.get("/integrated-workflows/{import_id}/explain")
def integrated_explain(import_id: str):
    return _integrated_call(lambda: integrated_workflow_explain(import_id))


@router.post("/integrated-workflows/{import_id}/resume")
def integrated_resume(
    import_id: str,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=255
    ),
):
    return _integrated_call(
        lambda: integrated_workflow_resume(import_id, idempotency_key=idempotency_key)
    )


@router.get("/integrated-workflows/compare")
def integrated_compare(
    left: str = Query(..., min_length=1),
    right: str = Query(..., min_length=1),
):
    return _integrated_call(lambda: integrated_workflow_compare(left, right))


@router.get("/verifications", response_model=PageEnvelope)
def verifications(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    return list_verifications(limit, offset)


@router.get("/verifications/{run_id}")
def verification(run_id: str):
    try:
        return verification_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Verification run not found.") from exc


@router.get("/lineage/{resource_type}/{resource_id}")
def lineage(resource_type: str, resource_id: str):
    return graph(resource_type, resource_id)
