import os
from typing import Any

from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import before_task_publish, task_postrun, task_prerun
from kombu import Exchange, Queue

from ..core.config import (
    ASHARE_TECH_REPORT_HOUR,
    ASHARE_TECH_REPORT_MINUTE,
    ASHARE_TECH_EVALUATION_HOUR,
    ASHARE_TECH_EVALUATION_MINUTE,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    DERIVED_MAINTENANCE_HOUR,
    DERIVED_MAINTENANCE_MINUTE,
    POSTGRES_BACKUP_HOUR,
    POSTGRES_BACKUP_MINUTE,
    PAPER_WALKFORWARD_HOUR,
    PAPER_WALKFORWARD_MINUTE,
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


def _task_argument(args: tuple[Any, ...], kwargs: dict[str, Any], index: int, name: str) -> str:
    value = args[index] if len(args) > index else kwargs.get(name)
    return str(value or "").strip()


def _reconcile_terminal_backtest_redelivery(
    args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any] | None:
    """Turn broker redelivery of an already-terminal backtest into an idempotent replay.

    The backtest row is the durable execution fact. If the worker committed a terminal
    run and then died before RabbitMQ observed the task acknowledgement, a replacement
    worker must not acquire another scheduler lease or execute LEAN again. The task row
    is reconciled only when the previous worker died before persisting its terminal task
    state; an already-reconciled replay performs no database/log/metric side effect.
    """

    task_id = _task_argument(args, kwargs, 0, "task_id")
    run_id = _task_argument(args, kwargs, 1, "run_id")
    if not task_id or not run_id:
        return None

    from ..domain.backtest_job import CANCELLED, normalize_status
    from ..repositories.backtest_repository import get_backtest
    from ..services.tasks import append_log, get_task, update_task

    existing_run = get_backtest(run_id)
    if not existing_run:
        return None
    try:
        status = normalize_status(str(existing_run.get("status") or ""))
    except ValueError:
        return None
    if status not in {"success", "failed", CANCELLED}:
        return None

    existing_task = get_task(task_id)
    task_status = str((existing_task or {}).get("status") or "").strip().lower()
    finished_at = existing_run.get("finished_at")
    error = existing_run.get("error") or existing_run.get("error_message")
    if status == CANCELLED and not error:
        error = "Cancellation requested by user."

    if task_status != status or not (existing_task or {}).get("finished_at"):
        append_log(
            task_id,
            f"Backtest {run_id} is already terminal ({status}); reconciling broker redelivery without re-execution.",
        )
        update_task(
            task_id,
            status=status,
            error=error,
            finished_at=finished_at,
        )

    return {"status": status, "run_id": run_id, "replayed": True}


class PlatformTask(Task):
    """Celery task base that preserves database truth across broker redelivery."""

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self.name == "lean_web.run_backtest":
            replay = _reconcile_terminal_backtest_redelivery(args, kwargs)
            if replay is not None:
                return replay
        return super().__call__(*args, **kwargs)


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
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["app.tasks.paper_cycle_dispatch", "app.tasks.worker"],
    task_cls=PlatformTask,
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_default_queue="default",
    task_queues=tuple(
        Queue(
            name,
            Exchange(name, type="direct", durable=True),
            routing_key=name,
            durable=True,
            queue_arguments={"x-queue-type": "classic"},
        )
        for name in ("default", "data-bulk", "data-lineage", "data-demand", "backtest", "ml")
    ),
    task_default_delivery_mode="persistent",
    task_routes={
        "lean_web.fetch_data_batch": {"queue": "data-demand"},
        "lean_web.download_on_demand_dataset": {"queue": "data-demand"},
        "lean_web.sync_all_data": {"queue": "data-bulk"},
        "lean_web.persist_tushare_lineage": {"queue": "data-lineage"},
        "lean_web.recover_tushare_lineage": {"queue": "default"},
        "lean_web.prepare_ml_data": {"queue": "data-bulk"},
        "lean_web.run_ml_research": {"queue": "ml"},
        "lean_web.run_research_analysis": {"queue": "default"},
        "lean_web.materialize_sync_data": {"queue": "data-demand"},
        "lean_web.maintain_derived_layers": {"queue": "data-demand"},
        "lean_web.recover_source_certifications": {"queue": "default"},
        "lean_web.redeliver_open_alerts": {"queue": "default"},
        "lean_web.recover_data_sync": {"queue": "default"},
        "lean_web.backup_postgres": {"queue": "default"},
        "lean_web.run_backtest": {"queue": "backtest"},
        "lean_web.start_research": {"queue": "backtest"},
        "lean_web.dispatch_experiment_batch": {"queue": "default"},
        "lean_web.run_research_batch_item": {"queue": "default"},
        "lean_web.reconcile_experiment_batches": {"queue": "default"},
        "lean_web.reconcile_domain_runs": {"queue": "default"},
        "lean_web.run_paper_execution_cycle": {"queue": "default"},
        "lean_web.finalize_paper_execution_cycle": {"queue": "default"},
        "lean_web.recover_stale_paper_cycle_dispatches": {"queue": "default"},
        "lean_web.refresh_ashare_tech_evaluations": {"queue": "default"},
    },
    task_annotations={
        "lean_web.run_backtest": {
            "acks_late": True,
            "reject_on_worker_lost": True,
        }
    },
    worker_prefetch_multiplier=1,
    control_queue_durable=True,
    event_queue_exclusive=True,
    broker_heartbeat=30,
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=_positive_env_int("LEAN_WORKER_MAX_TASKS_PER_CHILD", 50),
    worker_max_memory_per_child=_positive_env_int(
        "LEAN_WORKER_MAX_MEMORY_PER_CHILD_KB",
        1_572_864,
    ),
    broker_transport_options={"confirm_publish": True},
    result_expires=86_400,
    beat_schedule={
        "recover-orphaned-data-sync": {
            "task": "lean_web.recover_data_sync",
            "schedule": 60.0,
        },
        "recover-tushare-lineage": {
            "task": "lean_web.recover_tushare_lineage",
            "schedule": 30.0,
        },
        "backup-postgres-daily": {
            "task": "lean_web.backup_postgres",
            "schedule": crontab(
                minute=POSTGRES_BACKUP_MINUTE,
                hour=POSTGRES_BACKUP_HOUR,
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
        "recover-stale-paper-cycle-dispatches": {
            "task": "lean_web.recover_stale_paper_cycle_dispatches",
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
