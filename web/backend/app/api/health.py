from fastapi import APIRouter, Request

from ..services.broker import check_broker
from ..core.config import LEAN_EXECUTION_BACKEND, PARQUET_DIR
from ..services.dependencies import (
    check_alert_channel,
    check_database,
    check_execution_runtime,
    dependency_health,
)
from ..services.release_identity import runtime_release_identity

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    database = check_database()
    broker_ok = False
    try:
        broker_ok = bool(check_broker()["ok"])
    except Exception:
        broker_ok = False
    release = runtime_release_identity(request.app.openapi())
    notifications = check_alert_channel()
    execution = check_execution_runtime()
    healthy = bool(
        release["schema"]["aligned"]
        and database["ok"]
        and broker_ok
        and execution["ok"]
        and notifications["ok"]
    )
    return {
        "status": "ok" if healthy else "degraded",
        "database": {
            "engine": "postgresql",
            "status": "ready" if database["ok"] else "unavailable",
            "detail": database["detail"],
        },
        "broker": {"engine": "rabbitmq", "status": "ready" if broker_ok else "unavailable"},
        "execution": {
            "backend": LEAN_EXECUTION_BACKEND,
            "status": "ready" if execution["ok"] else "unavailable",
            "detail": execution["detail"],
        },
        "storage": {
            "marketData": "parquet",
            "queryEngine": "duckdb",
            "path": str(PARQUET_DIR),
        },
        "notifications": notifications["detail"],
        "release": release,
    }


@router.get("/health/dependencies")
def dependencies():
    return dependency_health()


@router.get("/health/database")
def database():
    return check_database()
