from __future__ import annotations

from datetime import datetime, timedelta, timezone
import shutil
from pathlib import Path
from typing import Any

from ..core.config import OBJECT_STORE_DIR, QUEUED_TASK_TIMEOUT_MINUTES, RUNTIME_DIR, REPORTS_DIR, RESEARCH_DIR, RUNS_DIR, UPLOADS_DIR
from ..db import db

TARGET_DIRECTORIES = (
    RUNS_DIR,
    REPORTS_DIR,
    RESEARCH_DIR,
    UPLOADS_DIR,
    OBJECT_STORE_DIR,
    RUNTIME_DIR / "alerts",
    RUNTIME_DIR / "pipeline-artifacts",
    RUNTIME_DIR / "source-cache",
)

HISTORY_TABLES = (
    "paper_run_checkpoints",
    "paper_ledger_entries",
    "paper_order_fills",
    "paper_order_transitions",
    "paper_order_intents",
    "paper_lean_order_events",
    "paper_walkforward_runs",
    "experiment_batch_attempts",
    "experiment_batch_items",
    "experiment_batches",
    "backtest_runs",
    "backtest_results",
    "optimization_runs",
    "research_sessions",
    "research_workspaces",
    "research_runs",
    "research_run_items",
    "reports",
    "experiments",
    "tasks",
    "paper_sessions",
    "paper_signals",
    "paper_orders",
    "paper_positions",
    "paper_portfolio_snapshots",
    "paper_daily_reports",
    "pipeline_runs",
    "pipeline_steps",
    "alert_events",
    "object_store_items",
)

TASK_TERMINAL_STATUSES = {"created", "queued", "running"}
HISTORY_OBJECT_NAMESPACES = ("backtest-results", "reports", "object-store")


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def cleanup_stale_queued(*, max_queued_minutes: int = QUEUED_TASK_TIMEOUT_MINUTES, dry_run: bool = False) -> dict[str, Any]:
    if max_queued_minutes <= 0:
        raise ValueError("max_queued_minutes must be greater than 0.")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max_queued_minutes)
    cutoff_iso = cutoff.isoformat()
    now_iso = now.isoformat()
    failure_reason = f"Queued for more than {max_queued_minutes} minutes without a worker."

    tasks_marked: list[str] = []
    runs_marked: list[str] = []
    skipped_tasks = 0
    skipped_runs = 0

    with db() as connection:
        task_rows = connection.execute("select id, created_at from tasks where status = 'queued'").fetchall()
        for row in task_rows:
            created_at = _parse_iso_datetime(row["created_at"])
            if created_at is None:
                skipped_tasks += 1
                continue
            if created_at < cutoff:
                tasks_marked.append(row["id"])
                if dry_run:
                    continue
                connection.execute(
                    """
                    update tasks
                        set status = ?, error = ?, finished_at = coalesce(finished_at, ?)
                        where id = ?
                    """,
                    ("failed", failure_reason, now_iso, row["id"]),
                )

        run_rows = connection.execute("select id, queued_at from backtest_runs where status = 'queued'").fetchall()
        for row in run_rows:
            queued_at = _parse_iso_datetime(row["queued_at"])
            if queued_at is None:
                skipped_runs += 1
                continue
            if queued_at < cutoff:
                runs_marked.append(row["id"])
                if dry_run:
                    continue
                connection.execute(
                    """
                    update backtest_runs
                        set status = ?, error = ?, error_message = ?, finished_at = coalesce(finished_at, ?)
                        where id = ?
                    """,
                    ("failed", failure_reason, failure_reason, now_iso, row["id"]),
                )

    return {
        "status": "completed",
        "dryRun": dry_run,
        "maxQueuedMinutes": max_queued_minutes,
        "cutoff": cutoff_iso,
        "evaluated": len(task_rows) + len(run_rows),
        "tasksMarked": len(tasks_marked),
        "backtestRunsMarked": len(runs_marked),
        "skipped": {
            "invalidTaskCreatedAt": skipped_tasks,
            "invalidRunQueuedAt": skipped_runs,
        },
        "taskIds": tasks_marked,
        "backtestRunIds": runs_marked,
    }


def _count_table_rows(connection, table: str) -> int:
    row = connection.execute(f"select count(*) as count from {table}").fetchone()
    return int(row["count"])


def _delete_all_rows(connection, table: str) -> int:
    result = connection.execute(f"delete from {table}")
    return int(result.rowcount or 0)


def _path_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _path_stats(target: Path) -> tuple[int, int, int]:
    files = 0
    dirs = 0
    size = 0
    if not target.exists():
        return files, dirs, size
    if target.is_file():
        return 1, 0, _path_size(target)
    for entry in target.rglob("*"):
        try:
            if entry.is_dir():
                dirs += 1
            else:
                files += 1
                size += _path_size(entry)
        except OSError:
            continue
    return files, dirs, size


def _clear_target_directory(target: Path, dry_run: bool) -> tuple[int, int, int, list[str]]:
    if not target.exists():
        return 0, 0, 0, []

    removed_files = 0
    removed_dirs = 0
    removed_bytes = 0
    removed = []

    for child in list(target.iterdir()):
        child_files, child_dirs, child_bytes = _path_stats(child)
        if not dry_run:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass
        if child.is_dir():
            removed_dirs += child_dirs + 1
        else:
            removed_files += 1
        removed_bytes += child_bytes
        removed.append(str(child))

    return removed_files, removed_dirs, removed_bytes, removed


def clear_local_history(*, dry_run: bool = False, force: bool = False, confirmation: str | None = None) -> dict[str, Any]:
    running_tasks: list[str] = []
    database_counts: dict[str, int] = {}
    deleted_rows: dict[str, int] = {}

    with db() as connection:
        rows = connection.execute("select id, status from tasks").fetchall()
        running_tasks = [row["id"] for row in rows if str(row["status"]).strip().lower() in TASK_TERMINAL_STATUSES]

        for table in HISTORY_TABLES:
            database_counts[table] = _count_table_rows(connection, table)
        placeholders = ",".join("?" for _ in HISTORY_OBJECT_NAMESPACES)
        object_rows = connection.execute(
            f"select id from stored_objects where namespace in ({placeholders})",
            HISTORY_OBJECT_NAMESPACES,
        ).fetchall()
        history_object_ids = [row["id"] for row in object_rows]
        database_counts["stored_objects"] = len(history_object_ids)
        if history_object_ids:
            object_placeholders = ",".join("?" for _ in history_object_ids)
            database_counts["stored_object_chunks"] = int(
                connection.execute(
                    f"select count(*) as count from stored_object_chunks where object_id in ({object_placeholders})",
                    history_object_ids,
                ).fetchone()["count"]
                or 0
            )
        else:
            database_counts["stored_object_chunks"] = 0

        if not dry_run and confirmation != "DELETE ALL LOCAL HISTORY":
            return {
                "status": "blocked",
                "dryRun": False,
                "force": force,
                "message": "Explicit confirmation is required. Prefer deleting selected resources from their own page.",
                "activeTaskCount": len(running_tasks),
                "database": database_counts,
            }

        if running_tasks and not force:
            return {
                "status": "blocked",
                "dryRun": dry_run,
                "force": force,
                "message": "Active tasks are running. Use force=true to proceed.",
                "activeTasks": running_tasks,
                "activeTaskCount": len(running_tasks),
                "database": database_counts,
            }

        if dry_run:
            return {
                "status": "ready",
                "dryRun": True,
                "force": force,
                "message": "Dry run complete. No files were removed.",
                "activeTaskCount": len(running_tasks),
                "database": database_counts,
            }

        for table in HISTORY_TABLES:
            deleted_rows[table] = _delete_all_rows(connection, table)

        if history_object_ids:
            object_placeholders = ",".join("?" for _ in history_object_ids)
            deleted_rows["stored_object_chunks"] = connection.execute(
                f"delete from stored_object_chunks where object_id in ({object_placeholders})",
                history_object_ids,
            ).rowcount
            deleted_rows["stored_objects"] = connection.execute(
                f"delete from stored_objects where id in ({object_placeholders})",
                history_object_ids,
            ).rowcount
        else:
            deleted_rows["stored_object_chunks"] = 0
            deleted_rows["stored_objects"] = 0

    runtime_summary = {
        "filesRemoved": 0,
        "dirsRemoved": 0,
        "bytesRemoved": 0,
        "targets": [],
    }

    for target in TARGET_DIRECTORIES:
        files, dirs, bytes_removed, removed = _clear_target_directory(target, dry_run=dry_run)
        runtime_summary["filesRemoved"] += files
        runtime_summary["dirsRemoved"] += dirs
        runtime_summary["bytesRemoved"] += bytes_removed
        runtime_summary["targets"].extend(removed)

    return {
        "status": "completed",
        "dryRun": False,
        "force": force,
        "message": "Local history and local cache cleared.",
        "database": database_counts,
        "deletedRows": deleted_rows,
        "runtime": runtime_summary,
    }
