from fastapi import APIRouter

from ..observability.metrics import metrics_response

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def metrics():
    return metrics_response()
