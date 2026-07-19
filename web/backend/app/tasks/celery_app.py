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
    task_default_queue="default",
    task_routes={
        "lean_web.fetch_data_batch": {"queue": "data-demand"},
        "lean_web.download_on_demand_dataset": {"queue": "data-demand"},
        "lean_web.sync_all_data": {"queue": "data-bulk"},
        "lean_web.materialize_sync_data": {"queue": "data-demand"},
        "lean_web.recover_data_sync": {"queue": "default"},
        "lean_web.run_backtest": {"queue": "backtest"},
        "lean_web.optimize": {"queue": "backtest"},
    },
    worker_prefetch_multiplier=1,
    beat_schedule={
        "recover-orphaned-data-sync": {
            "task": "lean_web.recover_data_sync",
            "schedule": 60.0,
        },
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
