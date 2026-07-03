from fastapi import APIRouter
from redis import Redis

from ..core.config import REDIS_URL

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    redis_ok = False
    try:
        redis_ok = bool(Redis.from_url(REDIS_URL, socket_connect_timeout=0.3).ping())
    except Exception:
        redis_ok = False
    return {"status": "ok", "redis": redis_ok}
