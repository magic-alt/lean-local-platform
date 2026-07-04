import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .core.config import (
    DB_PATH,
    OBJECT_STORE_DIR,
    PROJECTS_DIR,
    REPORTS_DIR,
    RESEARCH_DIR,
    RUNS_DIR,
    RUNTIME_DIR,
    UPLOADS_DIR,
)


JSON_COLUMNS = {
    "parameters_json": "parameters",
    "statistics_json": "statistics",
    "metadata_json": "metadata",
    "artifacts_json": "artifacts",
    "config_json": "config",
    "result_json": "result",
    "summary_metrics_json": "summary_metrics",
    "equity_curve_json": "equity_curve",
    "drawdown_curve_json": "drawdown_curve",
    "orders_json": "orders",
    "trades_json": "trades",
    "holdings_json": "holdings",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_storage() -> None:
    for path in (
        RUNTIME_DIR,
        RUNS_DIR,
        UPLOADS_DIR,
        PROJECTS_DIR,
        RESEARCH_DIR,
        OBJECT_STORE_DIR,
        REPORTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    init_storage()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"pragma table_info({table})")}


def _add_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _columns(connection, table):
        connection.execute(f"alter table {table} add column {column} {definition}")


def init_db() -> None:
    init_storage()
    with db() as connection:
        connection.executescript(
            """
            create table if not exists data_assets (
                id integer primary key autoincrement,
                symbol text not null,
                asset_class text not null default 'equity',
                venue text,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                source text not null,
                rows integer not null,
                first_date text not null,
                last_date text not null,
                lean_file text not null,
                metadata_json text not null,
                created_at text not null
            );

            create table if not exists projects (
                id text primary key,
                name text not null,
                language text not null,
                algorithm_class text not null,
                project_path text not null,
                main_file text not null,
                config_json text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists tasks (
                id text primary key,
                celery_task_id text,
                kind text not null,
                status text not null,
                title text not null,
                project_id text,
                related_id text,
                parameters_json text not null,
                log_path text not null,
                artifacts_json text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            );

            create table if not exists backtest_runs (
                id text primary key,
                task_id text,
                project_id text,
                symbol text not null,
                asset_class text not null default 'equity',
                venue text,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                parameters_json text not null,
                status text not null,
                docker_image text not null,
                name text,
                container_name text,
                work_dir text,
                results_dir text not null,
                result_json_path text,
                summary_json_path text,
                report_html_path text,
                log_path text,
                statistics_json text,
                exit_code integer,
                error text,
                error_message text,
                created_at text not null,
                queued_at text,
                started_at text,
                finished_at text,
                duration_seconds real
            );

            create table if not exists backtest_results (
                id text primary key,
                job_id text not null unique,
                summary_metrics_json text not null,
                equity_curve_json text not null,
                drawdown_curve_json text not null,
                orders_json text not null,
                trades_json text not null,
                holdings_json text not null,
                statistics_json text not null,
                raw_result_path text,
                created_at text not null
            );

            create table if not exists optimization_runs (
                id text primary key,
                task_id text,
                project_id text,
                status text not null,
                parameters_json text not null,
                result_json text,
                results_dir text not null,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            );

            create table if not exists research_sessions (
                id text primary key,
                task_id text,
                project_id text,
                status text not null,
                port integer not null,
                container_id text,
                url text,
                log_path text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            );

            create table if not exists reports (
                id text primary key,
                task_id text,
                run_id text not null,
                status text not null,
                report_path text,
                error text,
                created_at text not null,
                finished_at text
            );

            create table if not exists object_store_items (
                key text primary key,
                file_path text not null,
                size integer not null,
                updated_at text not null
            );

            create table if not exists settings (
                key text primary key,
                value_json text not null,
                updated_at text not null
            );

            create table if not exists paper_sessions (
                id text primary key,
                project_id text,
                name text not null,
                status text not null,
                symbol text not null,
                asset_class text not null,
                venue text not null,
                resolution text not null,
                cash real not null,
                equity real not null,
                parameters_json text not null,
                created_at text not null,
                updated_at text not null,
                finished_at text
            );

            create index if not exists idx_backtest_runs_created_at
                on backtest_runs(created_at desc);
            create index if not exists idx_backtest_runs_symbol
                on backtest_runs(symbol);
            create index if not exists idx_backtest_runs_status
                on backtest_runs(status);
            create index if not exists idx_backtest_results_job
                on backtest_results(job_id);
            create index if not exists idx_tasks_created_at
                on tasks(created_at desc);
            create index if not exists idx_projects_name
                on projects(name);
            create index if not exists idx_data_assets_symbol
                on data_assets(symbol);
            create index if not exists idx_paper_sessions_created_at
                on paper_sessions(created_at desc);
            """
        )
        _add_column(connection, "backtest_runs", "task_id", "text")
        _add_column(connection, "backtest_runs", "project_id", "text")
        _add_column(connection, "backtest_runs", "asset_class", "text not null default 'equity'")
        _add_column(connection, "backtest_runs", "venue", "text")
        _add_column(connection, "backtest_runs", "resolution", "text not null default 'daily'")
        _add_column(connection, "backtest_runs", "data_type", "text not null default 'trade'")
        _add_column(connection, "backtest_runs", "name", "text")
        _add_column(connection, "backtest_runs", "container_name", "text")
        _add_column(connection, "backtest_runs", "work_dir", "text")
        _add_column(connection, "backtest_runs", "error_message", "text")
        _add_column(connection, "backtest_runs", "queued_at", "text")
        _add_column(connection, "backtest_runs", "duration_seconds", "real")
        _add_column(connection, "data_assets", "asset_class", "text not null default 'equity'")
        _add_column(connection, "data_assets", "venue", "text")
        _add_column(connection, "data_assets", "resolution", "text not null default 'daily'")
        _add_column(connection, "data_assets", "data_type", "text not null default 'trade'")
        connection.execute(
            "create index if not exists idx_backtest_runs_asset on backtest_runs(asset_class, venue, symbol)"
        )
        connection.execute(
            "create index if not exists idx_data_assets_asset on data_assets(asset_class, venue, symbol)"
        )
        connection.execute("update backtest_runs set status = 'success' where status = 'succeeded'")
        connection.execute("update tasks set status = 'success' where status = 'succeeded'")
        connection.execute(
            """
            update backtest_runs
            set status = 'failed',
                error = coalesce(error, 'Backend restarted while run was active.'),
                error_message = coalesce(error_message, error, 'Backend restarted while run was active.'),
                finished_at = coalesce(finished_at, ?)
            where status in ('queued', 'running', 'interrupted')
            """,
            (utc_now(),),
        )
        connection.execute(
            """
            update tasks
            set status = 'failed',
                error = coalesce(error, 'Backend restarted while task was active.'),
                finished_at = coalesce(finished_at, ?)
            where status in ('queued', 'running', 'interrupted')
            """,
            (utc_now(),),
        )

def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for key, public_key in JSON_COLUMNS.items():
        if key in item:
            value = item.pop(key)
            item[public_key] = json.loads(value) if value else None
    return item


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in rows if row is not None]


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def relative_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(Path(path))
