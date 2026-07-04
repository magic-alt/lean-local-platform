from fastapi import APIRouter
from redis import Redis

from ..core.config import REDIS_URL
from ..services.dependencies import dependency_health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    redis_ok = False
    try:
        redis_ok = bool(Redis.from_url(REDIS_URL, socket_connect_timeout=0.3).ping())
    except Exception:
        redis_ok = False
    return {"status": "ok", "redis": redis_ok}


@router.get("/health/dependencies")
def dependencies():
    return dependency_health()
