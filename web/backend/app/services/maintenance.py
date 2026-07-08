from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..core.config import OBJECT_STORE_DIR, RUNTIME_DIR, REPORTS_DIR, RESEARCH_DIR, RUNS_DIR, UPLOADS_DIR
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
    "backtest_runs",
    "backtest_results",
    "optimization_runs",
    "research_sessions",
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


def clear_local_history(*, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    running_tasks: list[str] = []
    database_counts: dict[str, int] = {}
    deleted_rows: dict[str, int] = {}

    with db() as connection:
        rows = connection.execute("select id, status from tasks").fetchall()
        running_tasks = [row["id"] for row in rows if str(row["status"]).strip().lower() in TASK_TERMINAL_STATUSES]

        for table in HISTORY_TABLES:
            database_counts[table] = _count_table_rows(connection, table)
        database_counts["stored_objects"] = _count_table_rows(connection, "stored_objects")
        database_counts["stored_object_chunks"] = _count_table_rows(connection, "stored_object_chunks")

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

        deleted_rows["stored_object_chunks"] = _delete_all_rows(connection, "stored_object_chunks")
        deleted_rows["stored_objects"] = _delete_all_rows(connection, "stored_objects")

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
