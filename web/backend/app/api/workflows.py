from fastapi import APIRouter, HTTPException, Query

from ..services.workflows import list_verifications, list_workflows, verification_detail, workflow_detail

router = APIRouter(prefix="/api", tags=["workflows"])


@router.get("/workflows")
def workflows(limit: int = Query(100, ge=1, le=500), status: str | None = None):
    return list_workflows(limit=limit, status=status)


@router.get("/workflows/{workflow_id}")
def workflow(workflow_id: str):
    try:
        return workflow_detail(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found.") from exc


@router.get("/verifications")
def verifications(limit: int = Query(100, ge=1, le=500)):
    return list_verifications(limit)


@router.get("/verifications/{run_id}")
def verification(run_id: str):
    try:
        return verification_detail(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Verification run not found.") from exc
