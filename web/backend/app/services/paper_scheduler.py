from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


JOB_STATES = {
    "SCHEDULED",
    "WAITING_FOR_DATA",
    "READY",
    "RUNNING",
    "RETRYING",
    "COMPLETED",
    "SKIPPED_NON_TRADING_DAY",
    "BLOCKED_PREVIOUS_DAY",
    "BLOCKED_DATA",
    "BLOCKED_QA",
    "FAILED",
    "ESCALATED",
    "MANUAL_INTERVENTION_REQUIRED",
}

LEGAL_TRANSITIONS = {
    None: {"SCHEDULED", "SKIPPED_NON_TRADING_DAY"},
    "SCHEDULED": {"WAITING_FOR_DATA", "READY", "BLOCKED_PREVIOUS_DAY", "BLOCKED_DATA", "BLOCKED_QA"},
    "WAITING_FOR_DATA": {"READY", "BLOCKED_DATA", "FAILED"},
    "READY": {"RUNNING", "BLOCKED_DATA", "BLOCKED_QA", "FAILED"},
    "RUNNING": {"COMPLETED", "RETRYING", "FAILED"},
    "RETRYING": {"READY", "RUNNING", "FAILED", "ESCALATED"},
    "BLOCKED_PREVIOUS_DAY": {"READY", "MANUAL_INTERVENTION_REQUIRED"},
    "BLOCKED_DATA": {"WAITING_FOR_DATA", "READY", "RETRYING", "ESCALATED"},
    "BLOCKED_QA": {"READY", "RETRYING", "ESCALATED"},
    "FAILED": {"RETRYING", "ESCALATED", "MANUAL_INTERVENTION_REQUIRED"},
    "ESCALATED": {"RETRYING", "MANUAL_INTERVENTION_REQUIRED"},
    "COMPLETED": set(),
    "SKIPPED_NON_TRADING_DAY": set(),
    "MANUAL_INTERVENTION_REQUIRED": set(),
}


def _append_event(
    connection: Any,
    job: dict[str, Any],
    *,
    from_state: str | None,
    to_state: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    latest = connection.execute(
        "select max(sequence) as sequence from paper_daily_job_events where job_id=?",
        (job["id"],),
    ).fetchone()
    sequence = int(latest["sequence"] or 0) + 1 if latest else 1
    connection.execute(
        """
        insert into paper_daily_job_events
            (id,job_id,sequence,from_state,to_state,event_type,payload_json,
             correlation_id,created_at)
        values (?,?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            job["id"],
            sequence,
            from_state,
            to_state,
            event_type,
            json_dump(payload or {}),
            job["correlation_id"],
            utc_now(),
        ),
    )


def ensure_job(
    session_id: str,
    trade_date: str,
    *,
    max_attempts: int = 3,
    state: str = "SCHEDULED",
) -> dict[str, Any]:
    if state not in JOB_STATES:
        raise ValueError(f"Unknown Paper daily job state: {state}")
    with db() as connection:
        existing = connection.execute(
            "select * from paper_daily_jobs where session_id=? and trade_date=?",
            (session_id, trade_date),
        ).fetchone()
        if existing:
            return row_to_dict(existing) or {}
        now = utc_now()
        job = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "trade_date": trade_date,
            "correlation_id": f"paper:{session_id}:{trade_date}",
        }
        connection.execute(
            """
            insert into paper_daily_jobs
                (id,session_id,trade_date,state,attempt,max_attempts,version,
                 correlation_id,scheduled_at,updated_at)
            values (?,?,?,?,0,?,1,?,?,?)
            """,
            (
                job["id"],
                session_id,
                trade_date,
                state,
                max(1, int(max_attempts)),
                job["correlation_id"],
                now,
                now,
            ),
        )
        _append_event(
            connection,
            job,
            from_state=None,
            to_state=state,
            event_type="job_created",
        )
        row = connection.execute("select * from paper_daily_jobs where id=?", (job["id"],)).fetchone()
    return row_to_dict(row) or {}


def transition_job(
    job_id: str,
    to_state: str,
    *,
    event_type: str,
    payload: dict[str, Any] | None = None,
    expected_states: set[str] | None = None,
    paper_run_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    if to_state not in JOB_STATES:
        raise ValueError(f"Unknown Paper daily job state: {to_state}")
    with db() as connection:
        row = connection.execute("select * from paper_daily_jobs where id=?", (job_id,)).fetchone()
        job = row_to_dict(row)
        if not job:
            raise KeyError("Paper daily job not found.")
        from_state = str(job["state"])
        if expected_states is not None and from_state not in expected_states:
            return job
        if to_state == from_state:
            return job
        if to_state not in LEGAL_TRANSITIONS[from_state]:
            raise ValueError(f"Illegal Paper daily job transition: {from_state} -> {to_state}")
        attempt = int(job.get("attempt") or 0)
        if to_state == "RUNNING":
            attempt += 1
        completion_marker = (
            f"{job['session_id']}:{job['trade_date']}:complete"
            if to_state == "COMPLETED"
            else job.get("completion_marker")
        )
        now = utc_now()
        cursor = connection.execute(
            """
            update paper_daily_jobs
            set state=?,attempt=?,version=version+1,paper_run_id=coalesce(?,paper_run_id),
                task_id=coalesce(?,task_id),completion_marker=?,last_error=?,
                started_at=case when ?='RUNNING' then coalesce(started_at,?) else started_at end,
                completed_at=case when ?='COMPLETED' then ? else completed_at end,
                updated_at=?
            where id=? and version=?
            """,
            (
                to_state,
                attempt,
                paper_run_id,
                task_id,
                completion_marker,
                (payload or {}).get("error"),
                to_state,
                now,
                to_state,
                now,
                now,
                job_id,
                job["version"],
            ),
        )
        if getattr(cursor, "rowcount", 1) != 1:
            concurrent = connection.execute(
                "select * from paper_daily_jobs where id=?",
                (job_id,),
            ).fetchone()
            return row_to_dict(concurrent) or {}
        _append_event(
            connection,
            job,
            from_state=from_state,
            to_state=to_state,
            event_type=event_type,
            payload=payload,
        )
        updated = connection.execute("select * from paper_daily_jobs where id=?", (job_id,)).fetchone()
    return row_to_dict(updated) or {}


def job_for_date(session_id: str, trade_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_daily_jobs where session_id=? and trade_date=?",
            (session_id, trade_date),
        ).fetchone()
    return row_to_dict(row)


def list_jobs(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from paper_daily_jobs where session_id=? order by trade_date",
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def recover_orphaned_jobs(*, timeout_seconds: int = 3600) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(60, timeout_seconds))).isoformat()
    recovered: list[str] = []
    with db() as connection:
        rows = connection.execute(
            """
            select id from paper_daily_jobs
            where state='RUNNING' and started_at<?
            """,
            (cutoff,),
        ).fetchall()
    for row in rows:
        transition_job(
            str(row["id"]),
            "RETRYING",
            event_type="orphan_recovered",
            payload={"error": "run_lease_expired"},
            expected_states={"RUNNING"},
        )
        recovered.append(str(row["id"]))
    return recovered
