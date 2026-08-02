from fastapi import APIRouter, HTTPException, Query

from .common import PageEnvelope
from ..services.workflows import list_verifications, list_workflows, verification_detail, workflow_detail
from ..services.workflow_lineage import graph

router = APIRouter(prefix="/api", tags=["workflows"])


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
