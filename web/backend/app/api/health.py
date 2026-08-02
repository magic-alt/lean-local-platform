from fastapi import APIRouter, Request
from redis import Redis

from ..core.config import REDIS_URL
from ..services.dependencies import check_database, dependency_health
from ..services.release_identity import runtime_release_identity

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request):
    redis_ok = False
    try:
        redis_ok = bool(Redis.from_url(REDIS_URL, socket_connect_timeout=0.3).ping())
    except Exception:
        redis_ok = False
    release = runtime_release_identity(request.app.openapi())
    return {
        "status": "ok" if release["schema"]["aligned"] else "degraded",
        "redis": redis_ok,
        "release": release,
    }


@router.get("/health/dependencies")
def dependencies():
    return dependency_health()


@router.get("/health/database")
def database():
    return check_database()
