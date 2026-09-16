from __future__ import annotations

import os

from .celery_app import celery_app
from ..services import paper_cycle_dispatch
from ..services import us_etf_paper_v2


# Loaded before app.tasks.worker so its task uses the guarded begin_cycle path.
paper_cycle_dispatch.install_worker_guard()


@celery_app.task(name="lean_web.recover_stale_paper_cycle_dispatches")
def recover_stale_paper_cycle_dispatches_task(
    stale_seconds: int | None = None,
) -> dict:
    configured = int(
        stale_seconds
        if stale_seconds is not None
        else os.environ.get("LEAN_PAPER_DISPATCH_STALE_SECONDS", "120")
    )

    def publish(cycle_id: str):
        return celery_app.send_task(
            "lean_web.run_paper_execution_cycle",
            args=[cycle_id],
            queue="default",
        )

    return paper_cycle_dispatch.recover_stale_queued_dispatches(
        publish,
        stale_seconds=max(0, configured),
    )


@celery_app.task(
    name="lean_web.finalize_us_etf_paper_walkforward",
    acks_late=True,
    reject_on_worker_lost=True,
)
def finalize_us_etf_paper_walkforward_task(paper_run_id: str) -> dict:
    """Finalize one U.S. ETF certification day on the canonical Paper-v2 ledger."""
    return us_etf_paper_v2.finalize_walkforward_run(paper_run_id)


@celery_app.task(
    name="lean_web.run_us_etf_paper_day",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_us_etf_paper_day_task(session_id: str, trade_date: str) -> dict:
    """Dispatch LEAN -> worker risk/matching/ledger -> reconciliation for one Paper day.

    The session is created separately from a trusted certified backtest.  This task
    creates at most one canonical paper_walkforward_runs row for the date and then
    chains the existing LEAN worker before the U.S. ETF-specific finalizer.  No
    broker/live transport is reachable from this path.
    """
    from celery import chain

    # Imported lazily to avoid the celery_app include-order cycle: this module is
    # intentionally loaded before app.tasks.worker.
    from .worker import mark_paper_walkforward_running_task, run_backtest_task

    paper_run = us_etf_paper_v2.create_walkforward_run(session_id, trade_date)
    if paper_run.get("status") == "success":
        return {
            "sessionId": session_id,
            "tradeDate": trade_date,
            "paperRunId": paper_run["id"],
            "status": "success",
            "replayed": True,
        }
    workflow = chain(
        mark_paper_walkforward_running_task.si(paper_run["id"]),
        run_backtest_task.si(paper_run["task_id"], paper_run["backtest_run_id"]),
        finalize_us_etf_paper_walkforward_task.si(paper_run["id"]),
    )
    result = workflow.apply_async()
    return {
        "sessionId": session_id,
        "tradeDate": trade_date,
        "paperRunId": paper_run["id"],
        "backtestRunId": paper_run["backtest_run_id"],
        "workflowTaskId": result.id,
        "status": "queued",
    }
