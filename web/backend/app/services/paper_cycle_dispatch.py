from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from ..db import db, for_update_clause, row_to_dict, rows_to_dicts, utc_now
from . import paper_accounts


CLAIMABLE_CYCLE_STATES = {"queued", "scheduled", "waiting_data"}


def claim_cycle_for_worker(cycle_id: str) -> dict[str, Any]:
    """Atomically grant one at-least-once broker delivery execution ownership."""
    with db() as connection:
        current = row_to_dict(
            connection.execute(
                "select * from paper_execution_cycles where id=?" + for_update_clause(),
                (cycle_id,),
            ).fetchone()
        )
        if not current:
            raise KeyError("Paper execution cycle not found.")
        if str(current["status"]) not in CLAIMABLE_CYCLE_STATES:
            return {"claimed": False, "cycle": current}
        now = utc_now()
        cursor = connection.execute(
            """
            update paper_execution_cycles
            set status='running',started_at=coalesce(started_at,?),attempt=attempt+1,
                updated_at=?,version=version+1
            where id=? and version=? and status=?
            """,
            (now, now, cycle_id, current["version"], current["status"]),
        )
        if getattr(cursor, "rowcount", 1) != 1:
            concurrent = row_to_dict(
                connection.execute(
                    "select * from paper_execution_cycles where id=?",
                    (cycle_id,),
                ).fetchone()
            )
            return {"claimed": False, "cycle": concurrent or current}
        paper_accounts._append_cycle_event(
            connection,
            cycle_id,
            str(current["status"]),
            "running",
            "worker_dispatch_claimed",
            {"atLeastOnceDelivery": True},
        )
        claimed = row_to_dict(
            connection.execute(
                "select * from paper_execution_cycles where id=?",
                (cycle_id,),
            ).fetchone()
        )
    return {"claimed": True, "cycle": claimed or current}


def _duplicate_delivery_result(cycle: dict[str, Any]) -> dict[str, Any]:
    actual_status = str(cycle.get("status") or "")
    if actual_status in {"running", "finalizing"}:
        return {
            **cycle,
            "status": "skipped",
            "actualStatus": actual_status,
            "duplicateDelivery": True,
            "idempotent": True,
        }
    return {**cycle, "duplicateDelivery": True, "idempotent": True}


def guarded_begin_cycle(
    cycle_id: str,
    *,
    begin: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    claim = claim_cycle_for_worker(cycle_id)
    if not claim["claimed"]:
        return _duplicate_delivery_result(dict(claim["cycle"]))
    result = begin(cycle_id)
    return {**result, "workerClaimed": True}


def install_worker_guard() -> None:
    """Install the DB ownership claim before Celery worker task registration."""
    current = paper_accounts.begin_cycle
    if getattr(current, "_paper_cycle_dispatch_guarded", False):
        return

    def guarded(cycle_id: str) -> dict[str, Any]:
        return guarded_begin_cycle(cycle_id, begin=current)

    setattr(guarded, "_paper_cycle_dispatch_guarded", True)
    paper_accounts.begin_cycle = guarded


def recover_stale_queued_dispatches(
    publish: Callable[[str], Any],
    *,
    stale_seconds: int = 120,
    limit: int = 100,
) -> dict[str, Any]:
    """Republish durable queued intents stranded around broker publication."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=max(0, int(stale_seconds)))
    ).isoformat()
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select * from paper_execution_cycles
                where status='queued' and updated_at<=?
                order by updated_at,created_at limit ?
                """,
                (cutoff, max(1, min(int(limit), 500))),
            ).fetchall()
        )

    published: list[str] = []
    failed: list[str] = []
    for candidate in rows:
        cycle_id = str(candidate["id"])
        with db() as connection:
            current = row_to_dict(
                connection.execute(
                    "select * from paper_execution_cycles where id=?" + for_update_clause(),
                    (cycle_id,),
                ).fetchone()
            )
            if (
                not current
                or current["status"] != "queued"
                or int(current["version"]) != int(candidate["version"])
            ):
                continue
            now = utc_now()
            cursor = connection.execute(
                """
                update paper_execution_cycles
                set updated_at=?,version=version+1
                where id=? and version=? and status='queued'
                """,
                (now, cycle_id, current["version"]),
            )
            if getattr(cursor, "rowcount", 1) != 1:
                continue
            paper_accounts._append_cycle_event(
                connection,
                cycle_id,
                "queued",
                "queued",
                "dispatch_recovery_claimed",
                {"staleSeconds": max(0, int(stale_seconds))},
            )
        try:
            publish(cycle_id)
        except Exception as exc:
            with db() as connection:
                paper_accounts._append_cycle_event(
                    connection,
                    cycle_id,
                    "queued",
                    "queued",
                    "dispatch_recovery_publish_failed",
                    {"error": str(exc)[:1000]},
                )
            failed.append(cycle_id)
            continue
        with db() as connection:
            paper_accounts._append_cycle_event(
                connection,
                cycle_id,
                "queued",
                "queued",
                "dispatch_recovery_published",
                {},
            )
        published.append(cycle_id)
    return {"published": published, "failed": failed}
