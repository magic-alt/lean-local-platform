from celery import Celery

from ..core.config import REDIS_URL


celery_app = Celery(
    "lean_web",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.worker"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
