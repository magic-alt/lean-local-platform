from celery import Celery
from celery.schedules import crontab

from ..core.config import (
    ASHARE_TECH_REPORT_HOUR,
    ASHARE_TECH_REPORT_MINUTE,
    PAPER_WALKFORWARD_HOUR,
    PAPER_WALKFORWARD_MINUTE,
    REDIS_URL,
)


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
    timezone="Asia/Shanghai",
    enable_utc=True,
    beat_schedule={
        "ashare-tech-report-after-close": {
            "task": "lean_web.schedule_ashare_tech_report",
            "schedule": crontab(
                minute=ASHARE_TECH_REPORT_MINUTE,
                hour=ASHARE_TECH_REPORT_HOUR,
                day_of_week="1-5",
            ),
        },
        "lean-paper-walkforward-after-close": {
            "task": "lean_web.schedule_paper_walkforward",
            "schedule": crontab(
                minute=PAPER_WALKFORWARD_MINUTE,
                hour=PAPER_WALKFORWARD_HOUR,
                day_of_week="1-5",
            ),
        },
    },
)
