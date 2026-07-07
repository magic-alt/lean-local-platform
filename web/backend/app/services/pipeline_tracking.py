from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any
import uuid

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


def start_pipeline_run(
    *,
    universe_code: str | None,
    source: str,
    benchmark_symbol: str | None,
    artifact_dir: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    pipeline_id = run_id or f"l3p-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    with db() as connection:
        connection.execute(
            """
            insert into pipeline_runs
                (id, universe_code, source, benchmark_symbol, status, severity, decision,
                 started_at, artifact_dir, summary_json, warnings_json, errors_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pipeline_id,
                universe_code,
                source,
                benchmark_symbol,
                "running",
                "ok",
                None,
                now,
                artifact_dir,
                json_dump({}),
                json_dump([]),
                json_dump([]),
            ),
        )
    return {"id": pipeline_id, "startedAt": now, "perfStart": time.perf_counter()}


def finish_pipeline_run(
    run_id: str,
    *,
    status: str,
    severity: str,
    decision: str,
    summary: dict[str, Any],
    warnings: list[str],
    errors: list[str],
    artifact_object_id: str | None = None,
    perf_start: float | None = None,
) -> dict[str, Any]:
    now = utc_now()
    duration = (time.perf_counter() - perf_start) if perf_start else None
    with db() as connection:
        connection.execute(
            """
            update pipeline_runs
            set status = ?, severity = ?, decision = ?, finished_at = ?, duration_seconds = ?,
                artifact_object_id = ?, summary_json = ?, warnings_json = ?, errors_json = ?
            where id = ?
            """,
            (status, severity, decision, now, duration, artifact_object_id, json_dump(summary), json_dump(warnings), json_dump(errors), run_id),
        )
        row = connection.execute("select * from pipeline_runs where id = ?", (run_id,)).fetchone()
    return row_to_dict(row) or {"id": run_id}


def record_pipeline_step(
    run_id: str,
    step_name: str,
    *,
    status: str,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    started_at: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    now = utc_now()
    step_id = str(uuid.uuid5(uuid.UUID("633921c2-fd35-4b46-b0a4-9fd4fa6a7256"), f"{run_id}:{step_name}:{now}"))
    with db() as connection:
        connection.execute(
            """
            insert into pipeline_steps
                (id, run_id, step_name, status, started_at, finished_at, duration_seconds,
                 warnings_json, errors_json, details_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                run_id,
                step_name,
                status,
                started_at or now,
                now,
                duration_seconds,
                json_dump(warnings or []),
                json_dump(errors or []),
                json_dump(details or {}),
            ),
        )
    return {"id": step_id, "runId": run_id, "name": step_name, "status": status, "details": details or {}, "warnings": warnings or [], "errors": errors or [], "duration": duration_seconds}


def list_pipeline_runs(limit: int = 100) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from pipeline_runs
            order by started_at desc
            limit ?
            """,
            (max(1, min(int(limit), 1000)),),
        ).fetchall()
    return rows_to_dicts(rows)


def get_pipeline_run(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        run = connection.execute("select * from pipeline_runs where id = ?", (run_id,)).fetchone()
        steps = connection.execute("select * from pipeline_steps where run_id = ? order by started_at asc", (run_id,)).fetchall()
    item = row_to_dict(run)
    if not item:
        return None
    item["steps"] = rows_to_dicts(steps)
    return item
