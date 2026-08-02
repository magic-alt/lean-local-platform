from __future__ import annotations

import json
import uuid
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts, utc_now


def record_workflow_event(
    *,
    workflow_id: str,
    trace_id: str,
    stage: str,
    action: str,
    status: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    error_code: str | None = None,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    with db() as connection:
        connection.execute(
            """
            insert into workflow_events
                (id, workflow_id, trace_id, stage, action, resource_type, resource_id,
                 status, error_code, message, details_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, workflow_id, trace_id, stage, action, resource_type, resource_id,
             status, error_code, message, json.dumps(details or {}, ensure_ascii=False, default=str), utc_now()),
        )
        row = connection.execute("select * from workflow_events where id=?", (event_id,)).fetchone()
    return _event_payload(row_to_dict(row) or {})


def _event_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    raw = payload.pop("details_json", None)
    try:
        payload["details"] = json.loads(raw or "{}")
    except (TypeError, ValueError):
        payload["details"] = {}
    return payload


def list_workflows(*, limit: int = 100, offset: int = 0, status: str | None = None) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status=?")
        params.append(status)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    with db() as connection:
        total = connection.execute(
            f"select count(distinct workflow_id) as count from workflow_events {where}",
            tuple(params),
        ).fetchone()
        rows = connection.execute(
            f"""
            select workflow_id, min(created_at) as started_at, max(created_at) as updated_at,
                   count(*) as event_count,
                   sum(case when status='failed' then 1 else 0 end) as failure_count
            from workflow_events {where}
            group by workflow_id order by updated_at desc limit ? offset ?
            """,
            (*params, bounded_limit, bounded_offset),
        ).fetchall()
    return {
        "items": rows_to_dicts(rows),
        "count": int(total["count"] or 0),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def workflow_detail(workflow_id: str) -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            "select * from workflow_events where workflow_id=? order by created_at, id", (workflow_id,)
        ).fetchall()
    events = [_event_payload(dict(row)) for row in rows]
    if not events:
        raise KeyError(workflow_id)
    return {"workflow_id": workflow_id,
            "status": "failed" if any(item["status"] == "failed" for item in events) else events[-1]["status"],
            "events": events}


def list_verifications(limit: int = 100, offset: int = 0) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    with db() as connection:
        total = connection.execute("select count(*) as count from verification_runs").fetchone()
        rows = connection.execute(
            "select * from verification_runs order by created_at desc limit ? offset ?",
            (bounded_limit, bounded_offset),
        ).fetchall()
    return {
        "items": rows_to_dicts(rows),
        "count": int(total["count"] or 0),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def verification_detail(run_id: str) -> dict[str, Any]:
    with db() as connection:
        run = connection.execute("select * from verification_runs where id=?", (run_id,)).fetchone()
        cases = connection.execute(
            "select * from verification_cases where verification_run_id=? order by started_at, case_key", (run_id,)
        ).fetchall()
    if not run:
        raise KeyError(run_id)
    return {"run": row_to_dict(run), "cases": rows_to_dicts(cases)}
