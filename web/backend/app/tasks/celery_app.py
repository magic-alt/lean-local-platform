import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import before_task_publish, task_postrun, task_prerun

from ..core.config import (
    ASHARE_TECH_REPORT_HOUR,
    ASHARE_TECH_REPORT_MINUTE,
    ASHARE_TECH_EVALUATION_HOUR,
    ASHARE_TECH_EVALUATION_MINUTE,
    DERIVED_MAINTENANCE_HOUR,
    DERIVED_MAINTENANCE_MINUTE,
    MYSQL_BACKUP_HOUR,
    MYSQL_BACKUP_MINUTE,
    PAPER_WALKFORWARD_HOUR,
    PAPER_WALKFORWARD_MINUTE,
    REDIS_URL,
)
from ..core.request_context import (
    current_trace_id,
    current_workflow_id,
    reset_request_context,
    set_request_context,
)


_task_context_tokens: dict[str, tuple] = {}


def _positive_env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


@before_task_publish.connect
def attach_request_context(headers=None, **_kwargs) -> None:
    if headers is None:
        return
    if trace_id := current_trace_id():
        headers["x-trace-id"] = trace_id
    if workflow_id := current_workflow_id():
        headers["x-workflow-id"] = workflow_id


@task_prerun.connect
def restore_request_context(task_id=None, task=None, **_kwargs) -> None:
    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    trace_id = headers.get("x-trace-id")
    workflow_id = headers.get("x-workflow-id") or trace_id
    if task_id and (trace_id or workflow_id):
        _task_context_tokens[str(task_id)] = set_request_context(trace_id, workflow_id)


@task_postrun.connect
def clear_request_context(task_id=None, **_kwargs) -> None:
    tokens = _task_context_tokens.pop(str(task_id), None)
    if tokens:
        reset_request_context(tokens)


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
        "lean_web.prepare_ml_data": {"queue": "data-bulk"},
        "lean_web.run_ml_research": {"queue": "ml"},
        "lean_web.run_research_analysis": {"queue": "default"},
        "lean_web.materialize_sync_data": {"queue": "data-demand"},
        "lean_web.maintain_derived_layers": {"queue": "data-demand"},
        "lean_web.recover_source_certifications": {"queue": "default"},
        "lean_web.redeliver_open_alerts": {"queue": "default"},
        "lean_web.recover_data_sync": {"queue": "default"},
        "lean_web.backup_mysql": {"queue": "default"},
        "lean_web.run_backtest": {"queue": "backtest"},
        "lean_web.start_research": {"queue": "backtest"},
        "lean_web.dispatch_experiment_batch": {"queue": "default"},
        "lean_web.run_research_batch_item": {"queue": "default"},
        "lean_web.reconcile_experiment_batches": {"queue": "default"},
        "lean_web.reconcile_domain_runs": {"queue": "default"},
        "lean_web.run_paper_execution_cycle": {"queue": "default"},
        "lean_web.finalize_paper_execution_cycle": {"queue": "default"},
        "lean_web.refresh_ashare_tech_evaluations": {"queue": "default"},
    },
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=_positive_env_int("LEAN_WORKER_MAX_TASKS_PER_CHILD", 50),
    worker_max_memory_per_child=_positive_env_int(
        "LEAN_WORKER_MAX_MEMORY_PER_CHILD_KB",
        1_572_864,
    ),
    # Bulk sync/materialization tasks can legitimately run for several hours.
    # Redis' one-hour default visibility timeout redelivers an unacknowledged
    # acks_late task while the original worker is still processing it.
    broker_transport_options={"visibility_timeout": 43_200},
    result_backend_transport_options={"visibility_timeout": 43_200},
    beat_schedule={
        "recover-orphaned-data-sync": {
            "task": "lean_web.recover_data_sync",
            "schedule": 60.0,
        },
        "backup-mysql-daily": {
            "task": "lean_web.backup_mysql",
            "schedule": crontab(
                minute=MYSQL_BACKUP_MINUTE,
                hour=MYSQL_BACKUP_HOUR,
            ),
        },
        "maintain-derived-layers-after-close": {
            "task": "lean_web.maintain_derived_layers",
            "schedule": crontab(
                minute=DERIVED_MAINTENANCE_MINUTE,
                hour=DERIVED_MAINTENANCE_HOUR,
                day_of_week="1-5",
            ),
        },
        "recover-source-certifications": {
            "task": "lean_web.recover_source_certifications",
            "schedule": 300.0,
        },
        "redeliver-open-alerts": {
            "task": "lean_web.redeliver_open_alerts",
            "schedule": 60.0,
        },
        "reconcile-experiment-batches": {
            "task": "lean_web.reconcile_experiment_batches",
            "schedule": 60.0,
        },
        "reconcile-domain-runs": {
            "task": "lean_web.reconcile_domain_runs",
            "schedule": 60.0,
        },
        "monitor-operational-resources": {
            "task": "lean_web.monitor_operational_resources",
            "schedule": 60.0,
        },
        "recover-paper-finalizations": {
            "task": "lean_web.recover_paper_finalizations",
            "schedule": 60.0,
        },
        "schedule-due-paper-deployments": {
            "task": "lean_web.schedule_due_paper_deployments",
            "schedule": 60.0,
        },
        "recover-orphaned-paper-cycles": {
            "task": "lean_web.recover_orphaned_paper_cycles",
            "schedule": 60.0,
        },
        "deliver-paper-cycle-notifications": {
            "task": "lean_web.deliver_paper_cycle_notifications",
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
        "ashare-tech-prediction-evaluation": {
            "task": "lean_web.refresh_ashare_tech_evaluations",
            "schedule": crontab(
                minute=ASHARE_TECH_EVALUATION_MINUTE,
                hour=ASHARE_TECH_EVALUATION_HOUR,
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
