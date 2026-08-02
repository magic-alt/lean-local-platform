from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..core.config import REPORTS_DIR, RUNS_DIR
from ..core.errors import NotFoundError
from ..db import db, row_to_dict


ACTIVE_STATUSES = {"created", "pending", "dispatching", "queued", "checking", "running"}


def _is_active(status: object) -> bool:
    return str(status or "").strip().lower() in ACTIVE_STATUSES


def _remove_managed_path(value: object, *roots: Path, parent: bool = False) -> None:
    if not value:
        return
    candidate = Path(str(value)).expanduser()
    if parent:
        candidate = candidate.parent
    try:
        resolved = candidate.resolve()
    except OSError:
        return
    allowed = False
    for root in roots:
        try:
            resolved_root = root.resolve()
            resolved.relative_to(resolved_root)
            if resolved == resolved_root:
                continue
            allowed = True
            break
        except (OSError, ValueError):
            continue
    if not allowed:
        return
    if resolved.is_dir():
        shutil.rmtree(resolved, ignore_errors=True)
    else:
        try:
            resolved.unlink(missing_ok=True)
        except OSError:
            pass


def _delete_stored_objects(connection, *, namespace: str, object_key_prefix: str) -> int:
    rows = connection.execute(
        "select id from stored_objects where namespace = ? and object_key like ?",
        (namespace, f"{object_key_prefix}%"),
    ).fetchall()
    object_ids = [row["id"] for row in rows]
    if not object_ids:
        return 0
    placeholders = ",".join("?" for _ in object_ids)
    connection.execute(f"delete from object_store_items where stored_object_id in ({placeholders})", object_ids)
    connection.execute(f"delete from stored_object_chunks where object_id in ({placeholders})", object_ids)
    connection.execute(f"delete from stored_objects where id in ({placeholders})", object_ids)
    return len(object_ids)


def delete_backtest(run_id: str) -> dict[str, Any]:
    report_paths: list[str] = []
    with db() as connection:
        row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
        run = row_to_dict(row)
        if run is None:
            raise NotFoundError("Backtest run not found.")
        if _is_active(run.get("status")):
            raise ValueError("Active backtests must be cancelled before deletion.")
        active_tasks = connection.execute(
            "select count(*) as count from tasks where (related_id = ? or id = ?) and status in ('created','queued','running')",
            (run_id, run.get("task_id")),
        ).fetchone()
        if active_tasks and int(active_tasks["count"] or 0) > 0:
            raise ValueError("This backtest still has an active task. Cancel it before deletion.")

        linked_paper = connection.execute(
            "select count(*) as count from paper_sessions where source_backtest_id = ?",
            (run_id,),
        ).fetchone()
        if linked_paper and int(linked_paper["count"] or 0) > 0:
            raise ValueError("This backtest is used by a Paper session. Delete that session first.")

        walk_forward_oos = connection.execute(
            "select window_id from oos_evaluations where oos_run_id=? limit 1",
            (run_id,),
        ).fetchone()
        if walk_forward_oos:
            raise ValueError(
                f"Backtest is immutable Walk-Forward OOS evidence for window {walk_forward_oos['window_id']}."
            )
        walk_forward_phase = connection.execute(
            """
            select item.batch_id,item.id
            from experiment_batch_items item
            join walk_forward_runs wf_run on wf_run.batch_id=item.batch_id
            where item.related_id=? limit 1
            """,
            (run_id,),
        ).fetchone()
        if walk_forward_phase:
            raise ValueError(
                "Backtest is immutable Walk-Forward phase evidence "
                f"(batchId={walk_forward_phase['batch_id']}, itemId={walk_forward_phase['id']})."
            )

        report_rows = connection.execute("select report_path from reports where run_id = ?", (run_id,)).fetchall()
        report_paths = [str(item["report_path"]) for item in report_rows if item["report_path"]]
        connection.execute("delete from reports where run_id = ?", (run_id,))
        connection.execute("delete from backtest_results where job_id = ?", (run_id,))
        connection.execute("delete from experiments where run_id = ?", (run_id,))
        connection.execute("delete from tasks where related_id = ? or id = ?", (run_id, run.get("task_id")))
        stored_objects = _delete_stored_objects(connection, namespace="backtest-results", object_key_prefix=f"{run_id}/")
        connection.execute("delete from backtest_runs where id = ?", (run_id,))

    for path in report_paths:
        _remove_managed_path(path, REPORTS_DIR)
    _remove_managed_path(run.get("results_dir"), RUNS_DIR, parent=True)
    return {"deleted": True, "id": run_id, "storedObjects": stored_objects}


def delete_generated_report(report_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from reports where id = ?", (report_id,)).fetchone()
        report = row_to_dict(row)
        if report is None:
            raise NotFoundError("Generated report not found. Backtest reports are deleted with their backtest run.")
        if _is_active(report.get("status")):
            raise ValueError("Active reports must finish or be cancelled before deletion.")
        connection.execute("delete from tasks where related_id = ? or id = ?", (report_id, report.get("task_id")))
        connection.execute("delete from reports where id = ?", (report_id,))
    _remove_managed_path(report.get("report_path"), REPORTS_DIR)
    return {"deleted": True, "id": report_id}


def delete_paper_session(session_id: str) -> dict[str, Any]:
    child_tables = (
        "paper_ledger_entries",
        "paper_order_intents",
        "paper_lean_order_events",
        "paper_walkforward_runs",
        "paper_daily_reports",
        "paper_portfolio_snapshots",
        "paper_positions",
        "paper_orders",
        "paper_signals",
    )
    with db() as connection:
        row = connection.execute("select * from paper_sessions where id = ?", (session_id,)).fetchone()
        session = row_to_dict(row)
        if session is None:
            raise NotFoundError("Paper session not found.")
        account = connection.execute(
            "select id from paper_accounts where shadow_session_id=? limit 1",
            (session_id,),
        ).fetchone()
        if account:
            raise ValueError(
                "Paper Account shadow sessions are protected facts; archive the account instead "
                f"(paperAccountId={account['id']})."
            )
        if _is_active(session.get("status")):
            raise ValueError("Running Paper sessions must be stopped before deletion.")
        active_tasks = connection.execute(
            "select count(*) as count from tasks where related_id = ? and status in ('created','queued','running')",
            (session_id,),
        ).fetchone()
        if active_tasks and int(active_tasks["count"] or 0) > 0:
            raise ValueError("This Paper session still has an active task. Stop it before deletion.")
        connection.execute(
            """
            delete from paper_run_checkpoints
            where paper_run_id in (
                select id from paper_walkforward_runs where session_id=?
            )
            """,
            (session_id,),
        )
        connection.execute(
            """
            delete from paper_order_fills
            where intent_id in (
                select id from paper_order_intents where session_id=?
            )
            """,
            (session_id,),
        )
        connection.execute(
            """
            delete from paper_order_transitions
            where intent_id in (
                select id from paper_order_intents where session_id=?
            )
            """,
            (session_id,),
        )
        for table in child_tables:
            connection.execute(f"delete from {table} where session_id = ?", (session_id,))
        connection.execute("delete from tasks where related_id = ?", (session_id,))
        connection.execute("delete from paper_sessions where id = ?", (session_id,))
    return {"deleted": True, "id": session_id}


def delete_experiment_batch(batch_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from experiment_batches where id = ?", (batch_id,)).fetchone()
        batch = row_to_dict(row)
        if batch is None:
            raise NotFoundError("Experiment batch not found.")
        lineage = connection.execute(
            "select id,lineage_status from walk_forward_runs where batch_id=? limit 1",
            (batch_id,),
        ).fetchone()
        if lineage:
            raise ValueError(
                "Walk-Forward batches contain immutable selection and OOS evidence; archive the batch instead of deleting it "
                f"(walkForwardRunId={lineage['id']}, lineageStatus={lineage['lineage_status']})."
            )
        if _is_active(batch.get("status")):
            raise ValueError("Active experiment batches must be cancelled before deletion.")
        connection.execute(
            "delete from experiment_batch_attempts where item_id in (select id from experiment_batch_items where batch_id = ?)",
            (batch_id,),
        )
        connection.execute("delete from experiment_batch_items where batch_id = ?", (batch_id,))
        connection.execute("delete from experiment_batches where id = ?", (batch_id,))
    _remove_managed_path(RUNS_DIR / "batches" / batch_id, RUNS_DIR)
    return {"deleted": True, "id": batch_id}
