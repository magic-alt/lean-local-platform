from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import uuid

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


ALERT_TYPES = {
    "api_down",
    "worker_down",
    "mysql_down",
    "migration_mismatch",
    "provider_unavailable",
    "qa_critical",
    "warning_expired",
    "benchmark_missing",
    "cache_restore_failed",
    "paper_reject_spike",
    "nav_drawdown_warning",
    "report_write_failed",
}


def emit_alert(
    event_type: str,
    *,
    severity: str = "warning",
    title: str | None = None,
    message: str | None = None,
    source: str | None = None,
    related_id: str | None = None,
    details: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    alert_file: str | Path | None = None,
) -> dict[str, Any]:
    if event_type not in ALERT_TYPES:
        raise ValueError(f"unsupported_alert_type:{event_type}")
    now = utc_now()
    key = dedupe_key or f"{event_type}:{source or ''}:{related_id or ''}:{json_dump(details or {})[:128]}"
    alert_id = str(uuid.uuid5(uuid.UUID("86d16cc7-5c13-49c7-a151-7ab940f4cb81"), key))
    payload = {
        "id": alert_id,
        "eventType": event_type,
        "severity": severity,
        "status": "open",
        "dedupeKey": key,
        "title": title or event_type,
        "message": message or event_type,
        "source": source,
        "relatedId": related_id,
        "details": details or {},
        "firstSeenAt": now,
        "lastSeenAt": now,
    }
    with db() as connection:
        connection.execute(
            """
            insert into alert_events
                (id, event_type, severity, status, dedupe_key, title, message, source,
                 related_id, details_json, first_seen_at, last_seen_at, count)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(dedupe_key, status) do update set
                severity = excluded.severity,
                title = excluded.title,
                message = excluded.message,
                source = excluded.source,
                related_id = excluded.related_id,
                details_json = excluded.details_json,
                last_seen_at = excluded.last_seen_at,
                count = alert_events.count + 1
            """,
            (
                alert_id,
                event_type,
                severity,
                "open",
                key,
                payload["title"],
                payload["message"],
                source,
                related_id,
                json_dump(details or {}),
                now,
                now,
                1,
            ),
        )
        row = connection.execute(
            "select * from alert_events where dedupe_key = ? and status = 'open'",
            (key,),
        ).fetchone()
    item = row_to_dict(row) or payload
    if alert_file:
        path = Path(alert_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
    return item


def list_alert_events(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    sql = "select * from alert_events"
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by last_seen_at desc limit ?"
    params.append(max(1, min(int(limit), 1000)))
    with db() as connection:
        rows = connection.execute(sql, params).fetchall()
    return rows_to_dicts(rows)


def update_alert_status(alert_id: str, status: str, *, actor: str = "api") -> dict[str, Any] | None:
    if status not in {"acknowledged", "resolved"}:
        raise ValueError("status must be acknowledged or resolved")
    now = utc_now()
    fields = (
        "acknowledged_at = ?, acknowledged_by = ?, status = ?"
        if status == "acknowledged"
        else "resolved_at = ?, resolved_by = ?, status = ?"
    )
    with db() as connection:
        connection.execute(f"update alert_events set {fields} where id = ?", (now, actor, status, alert_id))
        row = connection.execute("select * from alert_events where id = ?", (alert_id,)).fetchone()
    return row_to_dict(row)
