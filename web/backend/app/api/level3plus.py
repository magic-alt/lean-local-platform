from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.alerts import list_alert_events, update_alert_status
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


@router.get("/alert-events")
def alert_events(status: str | None = None, limit: int = 100):
    return {"items": list_alert_events(status=status, limit=limit), "limit": limit}


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
