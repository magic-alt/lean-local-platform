from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts, utc_now


ACTIVE_RESEARCH = {"queued", "running"}
TERMINAL_TASK = {"success", "failed", "cancelled"}
ACTIVE_BACKTEST = {"created", "queued", "running"}


def reconcile_research_runs(*, stale_seconds: int = 300) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(60, int(stale_seconds)))).isoformat()
    reconciled: list[dict[str, str]] = []
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select run.* from research_runs run
                where run.status in ('queued','running')
                  and coalesce(run.owner_heartbeat_at,run.started_at,run.created_at)<?
                order by run.created_at
                """,
                (cutoff,),
            ).fetchall()
        )
        for run in rows:
            task = None
            if run.get("task_id"):
                task = row_to_dict(
                    connection.execute("select * from tasks where id=?", (run["task_id"],)).fetchone()
                )
            reason: str | None = None
            terminal_status = "failed"
            if task is None:
                reason = "owner_task_missing"
            elif str(task.get("status") or "") in TERMINAL_TASK:
                task_status = str(task["status"])
                terminal_status = "cancelled" if task_status == "cancelled" else "failed"
                reason = f"owner_task_{task_status}_domain_active"
            if not reason:
                continue
            now = utc_now()
            message = f"Reconciled active Research run: {reason}."
            connection.execute(
                """
                update research_runs
                set status=?,recovery_reason=?,error=coalesce(error,?),finished_at=coalesce(finished_at,?)
                where id=? and status in ('queued','running')
                """,
                (terminal_status, reason, message, now, run["id"]),
            )
            connection.execute(
                """
                update research_run_items
                set status=?,error=coalesce(error,?),finished_at=coalesce(finished_at,?)
                where run_id=? and status in ('queued','running')
                """,
                (terminal_status, message, now, run["id"]),
            )
            reconciled.append({"runId": str(run["id"]), "status": terminal_status, "reason": reason})
    return {"reconciled": reconciled, "count": len(reconciled), "staleSeconds": max(60, int(stale_seconds))}


def quarantine_orphaned_paper_records() -> dict[str, Any]:
    now = utc_now()
    jobs: list[str] = []
    reconciliations: list[str] = []
    with db() as connection:
        orphan_jobs = connection.execute(
            """
            select job.id,job.state from paper_daily_jobs job
            left join paper_sessions session on session.id=job.session_id
            where session.id is null and job.quarantined_at is null
            """
        ).fetchall()
        for row in orphan_jobs:
            state = "MANUAL_INTERVENTION_REQUIRED" if row["state"] == "READY" else row["state"]
            connection.execute(
                """
                update paper_daily_jobs
                set state=?,quarantined_at=?,quarantine_reason='parent_session_missing',
                    last_error=coalesce(last_error,'Quarantined because the parent Paper session is missing.'),
                    updated_at=?
                where id=?
                """,
                (state, now, now, row["id"]),
            )
            jobs.append(str(row["id"]))
        orphan_reconciliations = connection.execute(
            """
            select record.id from paper_reconciliation_records record
            left join paper_sessions session on session.id=record.session_id
            where session.id is null and record.quarantined_at is null
            """
        ).fetchall()
        for row in orphan_reconciliations:
            connection.execute(
                """
                update paper_reconciliation_records
                set quarantined_at=?,quarantine_reason='parent_session_missing'
                where id=?
                """,
                (now, row["id"]),
            )
            reconciliations.append(str(row["id"]))
    return {
        "paperJobs": jobs,
        "paperReconciliations": reconciliations,
        "count": len(jobs) + len(reconciliations),
    }


def reconcile_backtest_runs(*, stale_seconds: int = 300) -> dict[str, Any]:
    """Converge orphaned or over-budget backtests to a durable terminal state.

    Backtests run synchronously in a worker, so a worker loss otherwise leaves
    both the control-plane row and its scheduler lease active indefinitely.
    The timeout comes from the immutable run parameters rather than the beat
    cadence, preventing a valid long-running backtest from being reclaimed.
    """
    now_dt = datetime.now(timezone.utc)
    now = utc_now()
    reconciled: list[dict[str, str]] = []
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select * from backtest_runs
                where status in ('created','queued','running')
                order by created_at
                """
            ).fetchall()
        )
        for run in rows:
            task = None
            if run.get("task_id"):
                task = row_to_dict(
                    connection.execute("select * from tasks where id=?", (run["task_id"],)).fetchone()
                )
            reason: str | None = None
            terminal_status = "failed"
            if task is None:
                reason = "owner_task_missing"
            elif str(task.get("status") or "") in TERMINAL_TASK:
                task_status = str(task["status"])
                terminal_status = "cancelled" if task_status == "cancelled" else "failed"
                reason = f"owner_task_{task_status}_domain_active"
            elif str(run.get("status")) == "running":
                parameters = run.get("parameters") or {}
                try:
                    timeout = max(60, int(parameters.get("jobTimeoutSeconds") or 7200))
                except (TypeError, ValueError):
                    timeout = 7200
                anchor = str(run.get("started_at") or run.get("created_at") or "")
                try:
                    started = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=timezone.utc)
                    if now_dt - started > timedelta(seconds=timeout + max(60, stale_seconds)):
                        reason = "execution_timeout_without_terminal_state"
                except ValueError:
                    reason = "invalid_run_timestamp"
            if not reason:
                continue
            message = f"Reconciled active backtest: {reason}."
            connection.execute(
                """
                update backtest_runs
                set status=?,error=coalesce(error,?),error_message=coalesce(error_message,?),
                    finished_at=coalesce(finished_at,?)
                where id=? and status in ('created','queued','running')
                """,
                (terminal_status, message, message, now, run["id"]),
            )
            if task is not None:
                connection.execute(
                    """
                    update tasks set status=?,error=coalesce(error,?),finished_at=coalesce(finished_at,?)
                    where id=? and status not in ('success','failed','cancelled')
                    """,
                    (terminal_status, message, now, task["id"]),
                )
            connection.execute(
                "delete from scheduler_leases where resource='backtest' and holder_id=?",
                (run["id"],),
            )
            reconciled.append({"runId": str(run["id"]), "status": terminal_status, "reason": reason})
    return {"reconciled": reconciled, "count": len(reconciled)}


def reconcile_domain_runs(*, stale_seconds: int = 300) -> dict[str, Any]:
    return {
        "backtest": reconcile_backtest_runs(stale_seconds=stale_seconds),
        "research": reconcile_research_runs(stale_seconds=stale_seconds),
        "paper": quarantine_orphaned_paper_records(),
    }
