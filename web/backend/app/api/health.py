from fastapi import APIRouter, Request

from ..services.broker import check_broker
from ..core.config import LEAN_EXECUTION_BACKEND, PARQUET_DIR
from ..services.certification_status import authorization_status, certification_status
from ..services.dependencies import (
    check_alert_channel,
    check_database,
    check_execution_runtime,
    dependency_health,
)
from ..services.release_identity import runtime_release_identity

router = APIRouter(prefix="/api", tags=["health"])


def _readiness(request: Request) -> dict:
    database = check_database()
    broker_ok = False
    try:
        broker_ok = bool(check_broker()["ok"])
    except Exception:
        broker_ok = False
    release = runtime_release_identity(request.app.openapi())
    notifications = check_alert_channel()
    execution = check_execution_runtime()
    checks = {
        "schemaAligned": bool(release["schema"]["aligned"]),
        "databaseReady": bool(database["ok"]),
        "brokerReady": broker_ok,
        "executionReady": bool(execution["ok"]),
        "notificationsReady": bool(notifications["ok"]),
    }
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "release": release,
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
        "notifications": notifications["detail"],
    }


@router.get("/health")
def health(request: Request):
    readiness = _readiness(request)
    return {
        "status": "ok" if readiness["ready"] else "degraded",
        "database": readiness["database"],
        "broker": readiness["broker"],
        "execution": readiness["execution"],
        "storage": {
            "marketData": "parquet",
            "queryEngine": "duckdb",
            "path": str(PARQUET_DIR),
        },
        "notifications": readiness["notifications"],
        "release": readiness["release"],
    }


# These are deployment/certification probes rather than public business APIs.
# Their stable semantics are documented in docs/post-migration-certification.md;
# keep them out of the generated business API index and its compatibility surface.
@router.get("/health/readiness", include_in_schema=False)
def readiness(request: Request):
    return _readiness(request)


@router.get("/health/certification", include_in_schema=False)
def certification(request: Request):
    release = runtime_release_identity(request.app.openapi())
    return certification_status(release)


@router.get("/health/authorization", include_in_schema=False)
def authorization():
    return authorization_status()


@router.get("/health/dependencies")
def dependencies():
    return dependency_health()


@router.get("/health/database")
def database():
    return check_database()
