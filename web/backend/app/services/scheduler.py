from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now

try:  # pragma: no cover - optional unless MySQL is configured.
    import pymysql
except Exception:  # pragma: no cover
    pymysql = None


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _is_integrity_error(exc: Exception) -> bool:
    mysql_integrity = pymysql is not None and isinstance(exc, pymysql.err.IntegrityError)
    return mysql_integrity or exc.__class__.__name__ == "IntegrityError"


def acquire_scheduler_lease(
    *,
    resource: str,
    holder_id: str,
    limit: int,
    ttl_seconds: int,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    max_slots = max(1, int(limit or 1))
    ttl = max(60, int(ttl_seconds or 60))
    now = _now_dt()
    now_text = _iso(now)
    expires_at = _iso(now + timedelta(seconds=ttl))
    with db() as connection:
        connection.execute("delete from scheduler_leases where expires_at <= ?", (now_text,))
        if resource == "backtest":
            # A worker can be terminated after acquiring its slot but before
            # reaching the task's finally block. Startup recovery marks that
            # run terminal; do not make every subsequent run wait for the
            # original multi-hour TTL.
            connection.execute(
                """
                delete from scheduler_leases
                where resource = 'backtest' and holder_id in (
                    select id from backtest_runs
                    where status in ('success','failed','cancelled')
                )
                """
            )
        existing = connection.execute(
            """
            select * from scheduler_leases
            where resource = ? and holder_id = ? and expires_at > ?
            """,
            (resource, holder_id, now_text),
        ).fetchone()
        if existing is not None:
            return row_to_dict(existing)
        row = None
        for slot_index in range(max_slots):
            lease_id = str(uuid.uuid4())
            try:
                connection.execute(
                    """
                    insert into scheduler_leases
                        (id, resource, slot_index, holder_id, limit_count, acquired_at, expires_at, metadata_json)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease_id,
                        resource,
                        slot_index,
                        holder_id,
                        max_slots,
                        now_text,
                        expires_at,
                        json_dump(metadata or {}),
                    ),
                )
            except Exception as exc:
                if not _is_integrity_error(exc):
                    raise
                continue
            row = connection.execute("select * from scheduler_leases where id = ?", (lease_id,)).fetchone()
            break
    return row_to_dict(row)


def release_scheduler_lease(lease_id: str | None) -> None:
    if not lease_id:
        return
    with db() as connection:
        connection.execute("delete from scheduler_leases where id = ?", (lease_id,))


def renew_scheduler_lease(lease_id: str | None, *, ttl_seconds: int) -> bool:
    """Extend an active lease without extending an orphan indefinitely."""
    if not lease_id:
        return False
    now = _now_dt()
    now_text = _iso(now)
    expires_at = _iso(now + timedelta(seconds=max(60, int(ttl_seconds))))
    with db() as connection:
        cursor = connection.execute(
            """
            update scheduler_leases set expires_at=?
            where id=? and expires_at>?
            """,
            (expires_at, lease_id, now_text),
        )
    return bool(cursor.rowcount)


def active_scheduler_leases(resource: str | None = None) -> list[dict[str, Any]]:
    now = utc_now()
    clauses = ["expires_at > ?"]
    values: list[Any] = [now]
    if resource:
        clauses.append("resource = ?")
        values.append(resource)
    with db() as connection:
        rows = connection.execute(
            f"""
            select *
            from scheduler_leases
            where {" and ".join(clauses)}
            order by acquired_at asc
            """,
            values,
        ).fetchall()
    return rows_to_dicts(rows)
