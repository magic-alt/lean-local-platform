from fastapi import HTTPException
from kombu.exceptions import KombuError

from ..tasks.celery_app import celery_app
from ..services.tasks import update_task


def http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def dispatch_task(signature, task_id: str) -> str:
    try:
        async_result = signature.apply_async()
    except (KombuError, OSError, ConnectionError) as exc:
        update_task(task_id, status="failed", error=f"Redis/Celery unavailable: {exc}")
        raise HTTPException(status_code=503, detail="Redis/Celery unavailable. Start redis-server and the Celery worker.") from exc
    update_task(task_id, celery_task_id=async_result.id, status="queued")
    return async_result.id
