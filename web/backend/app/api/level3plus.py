from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .common import PageEnvelope
from ..services.alerts import (
    count_alert_events,
    list_alert_events,
    notification_delivery_health,
    requeue_dead_letter_deliveries,
    update_alert_status,
)
from ..services.resource_pressure import (
    collect_resource_snapshot,
    summarize_resource_capacity,
)
from ..services.pipeline_tracking import get_pipeline_run, list_pipeline_runs
from ..services.universe_certification import get_certified_universe


router = APIRouter(prefix="/api", tags=["level3plus"])


@router.get("/universes/{universe_code}")
def certified_universe(universe_code: str):
    payload = get_certified_universe(universe_code)
    if not payload.get("certification"):
        raise HTTPException(status_code=404, detail="universe_not_found")
    return payload


@router.get("/universes/{universe_code}/coverage")
def certified_universe_coverage(universe_code: str):
    payload = get_certified_universe(universe_code)
    certification = payload.get("certification")
    if not certification:
        raise HTTPException(status_code=404, detail="universe_not_found")
    return certification.get("coverage") or {}


@router.get("/pipeline-runs")
def pipeline_runs(limit: int = 100):
    return {"items": list_pipeline_runs(limit), "limit": limit}


@router.get("/pipeline-runs/{run_id}")
def pipeline_run(run_id: str):
    payload = get_pipeline_run(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail="pipeline_run_not_found")
    return payload


@router.get("/alert-events", response_model=PageEnvelope)
def alert_events(status: str | None = None, limit: int = 20, offset: int = 0):
    bounded_limit = max(1, min(int(limit), 100))
    bounded_offset = max(0, int(offset))
    return {
        "items": list_alert_events(
            status=status,
            limit=bounded_limit,
            offset=bounded_offset,
        ),
        "count": count_alert_events(status=status),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


@router.post("/alert-events/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str):
    payload = update_alert_status(alert_id, "acknowledged")
    if not payload:
        raise HTTPException(status_code=404, detail="alert_not_found")
    return payload


@router.post("/alert-events/{alert_id}/resolve")
def resolve_alert(alert_id: str):
    payload = update_alert_status(alert_id, "resolved")
    if not payload:
        raise HTTPException(status_code=404, detail="alert_not_found")
    return payload


@router.get("/alert-deliveries/health")
def alert_delivery_health():
    return notification_delivery_health()


@router.post("/alert-deliveries/requeue-dead-letter")
def requeue_alert_dead_letters():
    return requeue_dead_letter_deliveries()


@router.get("/operational/resources")
def operational_resources():
    snapshot = collect_resource_snapshot()
    return summarize_resource_capacity(snapshot)
