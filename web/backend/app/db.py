import json
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

sqlite3.register_adapter(Decimal, lambda value: format(value, "f"))

from .core.config import (
    DATABASE_URL,
    OBJECT_STORE_DIR,
    PROJECTS_DIR,
    REPORTS_DIR,
    RESEARCH_DIR,
    RUNS_DIR,
    RUNTIME_DIR,
    UPLOADS_DIR,
)

try:  # pragma: no cover - optional unless LEAN_DATABASE_URL points at MySQL.
    import pymysql
    from pymysql.cursors import DictCursor, SSDictCursor
except Exception:  # pragma: no cover
    pymysql = None
    DictCursor = None
    SSDictCursor = None


logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """Raised after transient MySQL connection failures exhaust bounded retries."""


TRANSIENT_MYSQL_CONNECTION_CODES = {1040, 2003, 2006, 2013}


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
    "performance_json": "performance",
    "fingerprint_json": "fingerprint",
    "validation_json": "validation",
    "experiment_json": "experiment",
    "failure_json": "failure",
    "reconciliation_json": "reconciliation",
    "event_json": "event",
    "raw_intent_json": "rawIntent",
    "baseline_snapshot_json": "baselineSnapshot",
    "evaluation_json": "evaluation",
    "payload_json": "payload",
    "positions_json": "positions",
    "report_json": "report",
    "signals_json": "signals",
    "rejects_json": "rejects",
    "snapshot_json": "snapshot",
    "benchmark_json": "benchmark",
    "qa_json": "qa",
    "concepts_json": "concepts",
    "qa_report_json": "qa_report",
    "coverage_json": "coverage",
    "warnings_json": "warnings",
    "errors_json": "errors",
    "summary_json": "summary",
    "provider_coverage_json": "providerCoverage",
    "supported_endpoints_json": "supportedEndpoints",
    "affected_symbols_json": "affectedSymbols",
    "fields_json": "fields",
    "terms_json": "terms",
    "partition_json": "partition",
    "sources_json": "sources",
    "symbols_json": "symbols",
    "details_json": "details",
    "scope_json": "scope",
    "context_json": "context",
    "raw_response_json": "rawResponse",
    "raw_signal_json": "rawSignal",
    "final_signal_json": "finalSignal",
    "guardrail_json": "guardrail",
    "data_completeness_json": "dataCompleteness",
    "source_conflicts_json": "sourceConflicts",
    "source_manifest_json": "sourceManifest",
    "pool_snapshot_json": "poolSnapshot",
    "rule_tags_json": "ruleTags",
    "checkpoint_json": "checkpoint",
    "requested_datasets_json": "requestedDatasets",
    "metrics_json": "metrics",
    "derived_status_json": "derivedStatus",
    "endpoint_counts_json": "endpointCounts",
    "universe_config_json": "universeConfig",
    "projection_json": "projection",
    "evidence_json": "evidence",
}


MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
SQLITE_SCHEMES = {"sqlite", "sqlite+pysqlite"}
SQLITE_TEST_BACKEND_ENABLED = os.environ.get("LEAN_ALLOW_SQLITE_TEST_DB", "").lower() in {"1", "true", "yes", "on"}
DB_PATH: Path | None = None
LONG_TEXT_COLUMNS = {
    "metadata_json",
    "config_json",
    "qa_report_json",
    "parameters_json",
    "artifacts_json",
    "statistics_json",
    "summary_metrics_json",
    "equity_curve_json",
    "drawdown_curve_json",
    "orders_json",
    "trades_json",
    "holdings_json",
    "performance_json",
    "validation_json",
    "experiment_json",
    "failure_json",
    "reconciliation_json",
    "event_json",
    "raw_intent_json",
    "report_json",
    "signals_json",
    "rejects_json",
    "snapshot_json",
    "benchmark_json",
    "qa_json",
    "result_json",
    "fields_json",
    "terms_json",
    "concepts_json",
    "symbols_json",
    "coverage_json",
    "warnings_json",
    "errors_json",
    "provider_coverage_json",
    "supported_endpoints_json",
    "affected_symbols_json",
    "details_json",
    "scope_json",
    "context_json",
    "raw_response_json",
    "raw_signal_json",
    "final_signal_json",
    "guardrail_json",
    "data_completeness_json",
    "source_conflicts_json",
    "source_manifest_json",
    "pool_snapshot_json",
    "rule_tags_json",
    "checkpoint_json",
    "requested_datasets_json",
    "derived_status_json",
    "endpoint_counts_json",
    "universe_config_json",
    "projection_json",
    "evidence_json",
    "error",
    "error_message",
}
PATH_TEXT_COLUMNS = {
    "lean_file",
    "file_path",
    "local_path",
    "project_path",
    "main_file",
    "log_path",
    "work_dir",
    "results_dir",
    "result_json_path",
    "summary_json_path",
    "report_html_path",
    "report_path",
    "raw_result_path",
    "source_path",
    "root_path",
    "strategy_path",
    "workspace_path",
}
MYSQL_RESERVED_COLUMNS = {"rows", "key"}
ID_TEXT_COLUMNS = {
    "id",
    "instrument_id",
    "object_id",
    "job_id",
    "task_id",
    "project_id",
    "batch_id",
    "session_id",
    "signal_id",
    "run_id",
    "related_id",
    "celery_task_id",
}
CODE_TEXT_COLUMNS = {
    "symbol",
    "normalized_symbol",
    "underlying_symbol",
    "stock_symbol",
    "bond_code",
    "contract_code",
    "product",
    "universe_code",
    "index_code",
    "exchange",
    "market",
    "venue",
    "asset_class",
    "resolution",
    "frequency",
    "data_type",
    "source",
    "status",
    "severity",
    "dataset",
    "kind",
    "side",
    "rule_type",
    "action_type",
    "statement_type",
    "field_name",
    "factor_name",
    "adjust",
    "currency",
    "base_currency",
    "quote_currency",
    "encoding",
    "storage_mode",
    "content_type",
    "parser_version",
    "parse_status",
    "provider",
    "main_symbol",
    "continuous_symbol",
}


def database_url() -> str:
    return DATABASE_URL


def database_backend() -> str:
    scheme = urlparse(DATABASE_URL).scheme.lower()
    if scheme in MYSQL_SCHEMES:
        return "mysql"
    if scheme in SQLITE_SCHEMES and SQLITE_TEST_BACKEND_ENABLED:
        return "sqlite"
    if scheme in SQLITE_SCHEMES:
        raise RuntimeError(
            "SQLite is disabled for runtime database use. Configure LEAN_DATABASE_URL with mysql+pymysql; "
            "use DuckDB only through the Parquet research layer."
        )
    raise RuntimeError(f"Unsupported database backend: {scheme or 'empty'}")


def _sqlite_db_path() -> Path:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme.lower() in SQLITE_SCHEMES and parsed.path:
        return Path(unquote(parsed.path)).expanduser()
    if DB_PATH is not None:
        return DB_PATH
    raise RuntimeError("SQLite test backend requires an explicit sqlite:/// path.")


def database_descriptor() -> dict[str, Any]:
    if database_backend() == "mysql":
        parsed = urlparse(DATABASE_URL)
        return {
            "engine": "mysql",
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "database": (parsed.path or "/lean_platform").lstrip("/"),
            "user": unquote(parsed.username or "lean"),
        }
    return {"engine": "sqlite", "mode": "test_only", "path": str(_sqlite_db_path())}


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


class MySQLConnection:
    def __init__(self, database_url: str | None = None) -> None:
        if pymysql is None or DictCursor is None:
            raise RuntimeError("pymysql is required when LEAN_DATABASE_URL uses mysql+pymysql.")
        parsed = urlparse(database_url or DATABASE_URL)
        database = (parsed.path or "/lean_platform").lstrip("/")
        if not database:
            raise RuntimeError("MySQL database name is required in LEAN_DATABASE_URL.")
        self._connection = pymysql.connect(
            host=parsed.hostname or "127.0.0.1",
            port=parsed.port or 3306,
            user=unquote(parsed.username or "lean"),
            password=unquote(parsed.password or "lean"),
            database=database,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=DictCursor,
            connect_timeout=5,
        )

    def execute(self, sql: str, parameters: Iterable[Any] | dict[str, Any] | None = None):
        translated = _translate_mysql_sql(_strip_leading_sql_comments(sql))
        add_column_info = _parse_alter_table_add_column(translated)
        if add_column_info:
            table_name, column_name = add_column_info
            with self._connection.cursor() as cursor:
                cursor.execute("show columns from `%s` like %%s" % table_name, (column_name,))
                if cursor.fetchone():
                    return cursor
        index_info = _parse_create_index_if_not_exists(translated)
        if index_info:
            index_name, table_name = index_info
            with self._connection.cursor() as cursor:
                cursor.execute("show index from `%s` where Key_name = %%s" % table_name, (index_name,))
                if cursor.fetchone():
                    return cursor
            translated = re.sub(
                r"\bcreate\s+(unique\s+)?index\s+if\s+not\s+exists\b",
                lambda match: f"create {match.group(1) or ''}index",
                translated,
                flags=re.IGNORECASE,
            )
        cursor = self._connection.cursor()
        cursor.execute(translated, parameters)
        return cursor

    def executemany(self, sql: str, parameters: Iterable[Iterable[Any] | dict[str, Any]]):
        cursor = self._connection.cursor()
        cursor.executemany(_translate_mysql_sql(sql), parameters)
        return cursor

    def iter_batches(
        self,
        sql: str,
        parameters: Iterable[Any] | dict[str, Any] | None = None,
        *,
        batch_size: int = 100_000,
    ) -> Iterable[list[dict[str, Any]]]:
        """Stream large read-only result sets without buffering them in Python."""
        if SSDictCursor is None:  # pragma: no cover - guarded by MySQL dependency.
            raise RuntimeError("PyMySQL SSDictCursor is required for streaming queries.")
        cursor = self._connection.cursor(SSDictCursor)
        try:
            cursor.execute(_translate_mysql_sql(sql), parameters)
            while True:
                rows = cursor.fetchmany(max(1, int(batch_size)))
                if not rows:
                    break
                yield list(rows)
        finally:
            cursor.close()

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            cleaned = _strip_leading_sql_comments(statement)
            if cleaned.strip():
                self.execute(cleaned)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _transient_mysql_connection_error(exc: Exception) -> bool:
    try:
        return int(exc.args[0]) in TRANSIENT_MYSQL_CONNECTION_CODES
    except (IndexError, TypeError, ValueError):
        return False


def _connect_mysql(database_url: str | None = None) -> MySQLConnection:
    attempts = max(1, min(int(os.environ.get("LEAN_MYSQL_CONNECT_ATTEMPTS", "5")), 10))
    base_delay = max(0.0, min(float(os.environ.get("LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS", "0.5")), 5.0))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return MySQLConnection(database_url)
        except Exception as exc:
            if not _transient_mysql_connection_error(exc):
                raise
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), 5.0)
            logger.warning(
                "MySQL connection unavailable (attempt %s/%s); retrying in %.1fs: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)
    raise DatabaseUnavailableError(
        f"MySQL is temporarily unavailable after {attempts} connection attempts."
    ) from last_error


def _rollback_quietly(connection: sqlite3.Connection | MySQLConnection) -> None:
    try:
        connection.rollback()
    except Exception:
        logger.warning("Database rollback failed after the original operation error", exc_info=True)


def _close_quietly(connection: sqlite3.Connection | MySQLConnection) -> None:
    try:
        connection.close()
    except Exception:
        logger.warning("Database connection close failed", exc_info=True)


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    previous = ""
    for char in script:
        if char == "'" and not in_double and previous != "\\":
            in_single = not in_single
        elif char == '"' and not in_single and previous != "\\":
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            statements.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        previous = char
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _strip_leading_sql_comments(sql: str) -> str:
    lines = sql.strip().splitlines()
    while lines and lines[0].strip().startswith("--"):
        lines.pop(0)
    return "\n".join(lines).strip()


def _parse_create_index_if_not_exists(sql: str) -> tuple[str, str] | None:
    match = re.match(r"\s*create\s+(?:unique\s+)?index\s+if\s+not\s+exists\s+`?([A-Za-z0-9_]+)`?\s+on\s+`?([A-Za-z0-9_]+)`?", sql, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1), match.group(2)


def _parse_alter_table_add_column(sql: str) -> tuple[str, str] | None:
    match = re.match(
        r"\s*alter\s+table\s+`?([A-Za-z0-9_]+)`?\s+add\s+column\s+`?([A-Za-z0-9_]+)`?",
        sql,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def _mysql_text_type(column: str) -> str:
    column = column.strip("`").lower()
    if column in ID_TEXT_COLUMNS or column.endswith("_id"):
        return "varchar(64)"
    if column.endswith("_sha256"):
        return "varchar(64)"
    if column in {"profile_name", "profile_version", "sample_set", "current_stage", "stage"}:
        return "varchar(64)"
    if column in CODE_TEXT_COLUMNS:
        return "varchar(96)"
    if column.endswith("_date") or column.endswith("_at") or column in {"date", "timestamp", "start_time", "end_time", "fiscal_period", "delivery_month", "maturity_date"}:
        return "varchar(32)"
    if column in LONG_TEXT_COLUMNS or column.endswith("_json"):
        return "longtext"
    if column == "raw_file_hash" or column.endswith("_hash"):
        return "varchar(128)"
    if column in PATH_TEXT_COLUMNS:
        return "varchar(1024)"
    if column.endswith("_url"):
        return "varchar(255)"
    if column in {"index_code", "universe_code", "symbol", "key", "id", "job_id", "task_id", "project_id"}:
        return "varchar(191)"
    return "varchar(255)"


def _translate_mysql_create_table(sql: str) -> str:
    sql = re.sub(r"\binteger\s+primary\s+key\s+autoincrement\b", "integer primary key auto_increment", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bblob\b", "longblob", sql, flags=re.IGNORECASE)
    lines = []
    for raw_line in sql.splitlines():
        line = raw_line
        match = re.match(r"(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s+)text(\b.*)", line, flags=re.IGNORECASE)
        if match:
            indent, column, spacer, suffix = match.groups()
            column_name = f"`{column}`" if column.lower() in MYSQL_RESERVED_COLUMNS else column
            line = f"{indent}{column_name}{spacer}{_mysql_text_type(column)}{suffix}"
        else:
            reserved_match = re.match(r"(\s*)(rows|key)(\s+)", line, flags=re.IGNORECASE)
            if reserved_match:
                indent, column, spacer = reserved_match.groups()
                line = f"{indent}`{column}`{spacer}{line[reserved_match.end():]}"
        lines.append(line)
    return "\n".join(lines)


def _translate_mysql_upsert(sql: str) -> str:
    match = re.search(r"\bon\s+conflict\s*\((?P<cols>[^)]+)\)\s*do\s+update\s+set\s*(?P<updates>.*)$", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return sql
    updates = match.group("updates").strip().rstrip(";")
    updates = re.sub(r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)", r"values(\1)", updates, flags=re.IGNORECASE)
    updates = re.sub(r"\bmin\s*\(", "least(", updates, flags=re.IGNORECASE)
    return sql[: match.start()].rstrip() + "\n            on duplicate key update " + updates


def _translate_mysql_sql(sql: str) -> str:
    translated = sql.strip()
    translated = re.sub(r"\?", "%s", translated)
    if re.match(r"create\s+view\s+if\s+not\s+exists", translated, flags=re.IGNORECASE):
        translated = re.sub(r"create\s+view\s+if\s+not\s+exists", "create or replace view", translated, count=1, flags=re.IGNORECASE)
    if re.match(r"create\s+table", translated, flags=re.IGNORECASE):
        translated = _translate_mysql_create_table(translated)
    alter_text = re.match(
        r"(?P<prefix>alter\s+table\s+`?[A-Za-z0-9_]+`?\s+add\s+column\s+`?(?P<column>[A-Za-z0-9_]+)`?\s+)text(?P<suffix>\b.*)",
        translated,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if alter_text:
        column = alter_text.group("column")
        translated = f"{alter_text.group('prefix')}{_mysql_text_type(column)}{alter_text.group('suffix')}"
    translated = _translate_mysql_upsert(translated)
    translated = re.sub(r"(?<![\w`])rows(?![\w`])", "`rows`", translated, flags=re.IGNORECASE)
    translated = re.sub(r"(?<![\w`])key(?![\w`])", "`key`", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bprimary\s+`key`", "primary key", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bforeign\s+`key`", "foreign key", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bduplicate\s+`key`", "duplicate key", translated, flags=re.IGNORECASE)
    return translated


def connect() -> sqlite3.Connection | MySQLConnection:
    init_storage()
    if database_backend() == "mysql":
        return _connect_mysql()
    connection = sqlite3.connect(_sqlite_db_path())
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db() -> Iterable[sqlite3.Connection | MySQLConnection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        _rollback_quietly(connection)
        raise
    finally:
        _close_quietly(connection)


@contextmanager
def bulk_db() -> Iterable[sqlite3.Connection | MySQLConnection]:
    """Connection used only for rebuildable provider data bulk ingestion.

    A dedicated loader URL may hold the restricted session-variable privilege
    required for ``sql_log_bin=0``.  Business/API connections continue using
    the normal URL and retain binary logging.
    """
    if database_backend() != "mysql":
        with db() as connection:
            yield connection
        return
    loader_url = os.environ.get("LEAN_LOADER_DATABASE_URL") or DATABASE_URL
    disable_binlog = os.environ.get("LEAN_MYSQL_BULK_DISABLE_BINLOG", "0").lower() in {"1", "true", "yes", "on"}
    require_loader = os.environ.get("LEAN_REQUIRE_LOADER_DATABASE", "0").lower() in {"1", "true", "yes", "on"}
    connection: MySQLConnection | None = None
    try:
        connection = _connect_mysql(loader_url)
        if disable_binlog:
            connection.execute("set session sql_log_bin=0")
    except Exception as exc:
        if connection is not None:
            connection.close()
        if require_loader or loader_url == DATABASE_URL:
            raise
        # Direct ``docker compose up`` does not provision the restricted loader
        # user created by start_web_single_instance.sh.  Keep that path usable
        # and retain normal business-session binlogging instead of failing a run.
        logger.warning("Bulk loader session unavailable; falling back to the normal database connection: %s", exc)
        connection = _connect_mysql(DATABASE_URL)
    try:
        yield connection
        connection.commit()
    except Exception:
        _rollback_quietly(connection)
        raise
    finally:
        _close_quietly(connection)


def _columns(connection: sqlite3.Connection | MySQLConnection, table: str) -> set[str]:
    if database_backend() == "mysql":
        rows = connection.execute(f"show columns from `{table}`").fetchall()
        return {row["Field"] for row in rows}
    return {row["name"] for row in connection.execute(f"pragma table_info({table})")}


def _add_column(connection: sqlite3.Connection | MySQLConnection, table: str, column: str, definition: str) -> None:
    if column not in _columns(connection, table):
        if database_backend() == "mysql":
            definition = _translate_mysql_create_table(f"{column} {definition}").split(" ", 1)[1]
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
                lean_object_id text,
                factor_object_id text,
                status text not null default 'active',
                superseded_by integer,
                superseded_at text,
                superseded_reason text,
                metadata_json text not null,
                created_at text not null
            );

            create table if not exists securities (
                symbol text primary key,
                name text not null,
                exchange text not null,
                market text not null default 'china',
                listed_date text not null,
                delisted_date text,
                status text not null default 'listed',
                is_st integer not null default 0,
                industry text,
                concepts_json text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists instruments (
                instrument_id text primary key,
                symbol text not null,
                normalized_symbol text not null,
                name text,
                asset_class text not null,
                market text not null,
                exchange text,
                venue text,
                currency text,
                base_currency text,
                quote_currency text,
                underlying_symbol text,
                listed_date text,
                delisted_date text,
                expiry_date text,
                status text not null default 'active',
                lot_size real,
                tick_size real,
                contract_multiplier real,
                margin_rate real,
                metadata_json text not null,
                source text not null,
                created_at text not null,
                updated_at text not null,
                unique(asset_class, market, venue, symbol)
            );

            create table if not exists instrument_identifiers (
                instrument_id text not null,
                id_type text not null,
                id_value text not null,
                start_date text,
                end_date text,
                source text not null,
                created_at text not null,
                primary key (instrument_id, id_type, id_value, source)
            );

            create table if not exists market_daily_bars (
                instrument_id text not null,
                symbol text not null,
                asset_class text not null,
                market text not null,
                venue text,
                trade_date text not null,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                open real,
                high real,
                low real,
                close real,
                settle real,
                volume real,
                amount real,
                turnover_rate real,
                open_interest real,
                prev_close real,
                pct_change real,
                adjust text not null default 'raw',
                adj_factor real,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (instrument_id, trade_date, resolution, data_type, adjust, source)
            );

            create table if not exists market_trade_status (
                instrument_id text not null,
                symbol text not null,
                asset_class text not null,
                market text not null,
                venue text,
                trade_date text not null,
                is_tradeable integer not null default 1,
                is_suspended integer not null default 0,
                can_buy integer not null default 1,
                can_sell integer not null default 1,
                limit_up real,
                limit_down real,
                status text,
                reason text,
                source text not null,
                batch_id text,
                updated_at text not null,
                primary key (instrument_id, trade_date, source)
            );

            create table if not exists market_intraday_bars (
                instrument_id text not null,
                symbol text not null,
                asset_class text not null,
                market text not null,
                venue text,
                timestamp text not null,
                frequency text not null,
                data_type text not null default 'trade',
                open real,
                high real,
                low real,
                close real,
                volume real,
                amount real,
                open_interest real,
                adjust text not null default 'raw',
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (instrument_id, timestamp, frequency, data_type, adjust, source)
            );

            create table if not exists market_ticks (
                id text primary key,
                instrument_id text not null,
                symbol text not null,
                asset_class text not null,
                market text not null,
                venue text,
                timestamp text not null,
                last_price real,
                bid_price real,
                ask_price real,
                bid_volume real,
                ask_volume real,
                volume real,
                open_interest real,
                source text not null,
                batch_id text,
                created_at text not null
            );

            create table if not exists parquet_datasets (
                id text primary key,
                dataset_key text not null unique,
                asset_class text not null,
                market text not null,
                venue text,
                resolution text not null,
                data_type text not null default 'trade',
                adjust text not null default 'raw',
                source text not null,
                root_path text not null,
                schema_version integer not null default 1,
                start_date text,
                end_date text,
                row_count integer not null default 0,
                file_count integer not null default 0,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists parquet_files (
                id text primary key,
                dataset_id text not null,
                file_path text not null,
                partition_json text not null,
                row_count integer not null,
                first_timestamp text,
                last_timestamp text,
                sha256 text not null,
                size integer not null,
                created_at text not null
            );

            create table if not exists data_quality_reports (
                id text primary key,
                report_type text not null,
                asset_class text not null,
                market text not null,
                symbol text,
                start_date text,
                end_date text,
                sources_json text not null,
                severity text not null,
                result_json text not null,
                created_at text not null
            );

            create table if not exists trade_calendar (
                market text not null,
                trade_date text not null,
                is_open integer not null,
                prev_trade_date text,
                next_trade_date text,
                source text,
                batch_id text,
                primary key (market, trade_date)
            );

            create table if not exists ashare_daily_bars (
                symbol text not null,
                trade_date text not null,
                open real not null,
                high real not null,
                low real not null,
                close real not null,
                volume real not null,
                amount real,
                turnover_rate real,
                prev_close real,
                pct_change real,
                adj_factor real,
                adjust text not null default 'raw',
                source text not null,
                batch_id text not null,
                created_at text not null,
                primary key (symbol, trade_date, adjust, source)
            );

            create table if not exists ashare_trade_status (
                symbol text not null,
                trade_date text not null,
                is_suspended integer not null default 0,
                limit_up real,
                limit_down real,
                is_limit_up integer not null default 0,
                is_limit_down integer not null default 0,
                is_one_word_limit_up integer not null default 0,
                is_one_word_limit_down integer not null default 0,
                can_buy integer not null default 1,
                can_sell integer not null default 1,
                is_st integer not null default 0,
                source text not null,
                batch_id text not null,
                primary key (symbol, trade_date)
            );

            create table if not exists adjustment_factors (
                symbol text not null,
                trade_date text not null,
                adj_factor real not null,
                source text not null,
                batch_id text not null,
                primary key (symbol, trade_date, source)
            );

            create table if not exists corporate_actions (
                symbol text not null,
                ex_date text not null,
                action_type text not null,
                cash_dividend real,
                stock_dividend real,
                split_ratio real,
                allotment_ratio real,
                allotment_price real,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, ex_date, action_type, source)
            );

            create table if not exists universe_membership (
                universe_code text not null,
                symbol text not null,
                start_date text not null,
                end_date text,
                announce_date text,
                effective_date text,
                weight real,
                source text not null,
                batch_id text,
                primary key (universe_code, symbol, start_date)
            );

            create table if not exists index_weights (
                universe_code text not null,
                symbol text not null,
                trade_date text not null,
                weight real not null,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (universe_code, symbol, trade_date, source)
            );

            create table if not exists paper_universe_certifications (
                id text primary key,
                universe_code text not null,
                source text not null,
                benchmark_symbol text not null,
                certification_status text not null,
                certification_date text not null,
                start_date text not null,
                end_date text not null,
                target_size integer not null,
                min_size integer not null,
                symbol_count integer not null default 0,
                coverage_report_id text,
                qa_report_id text,
                valid_from text not null,
                valid_to text,
                coverage_json text not null,
                qa_report_json text not null,
                warnings_json text not null,
                errors_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(universe_code, source, start_date, end_date)
            );

            create table if not exists paper_universe_symbols (
                id text primary key,
                universe_code text not null,
                symbol text not null,
                source text not null,
                certification_status text not null,
                certification_date text not null,
                coverage_report_id text,
                qa_report_id text,
                valid_from text not null,
                valid_to text,
                coverage_json text not null,
                qa_json text not null,
                warnings_json text not null,
                errors_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(universe_code, symbol, valid_from)
            );

            create table if not exists qa_warning_allowlist (
                id text primary key,
                warning_code text not null,
                reason text not null,
                valid_until text not null,
                approved_by text not null,
                affected_symbols_json text not null,
                scope_json text not null,
                status text not null default 'active',
                created_at text not null,
                updated_at text not null
            );

            create table if not exists provider_availability_log (
                id text primary key,
                provider text not null,
                status text not null,
                installed integer not null default 0,
                configured integer not null default 0,
                credentials_status text not null,
                unavailable_reason text,
                supported_endpoints_json text not null,
                coverage_json text not null,
                production_certified integer not null default 0,
                checked_at text not null,
                metadata_json text not null
            );

            create table if not exists pipeline_runs (
                id text primary key,
                universe_code text,
                source text not null,
                benchmark_symbol text,
                status text not null,
                severity text not null,
                decision text,
                started_at text not null,
                finished_at text,
                duration_seconds real,
                artifact_dir text,
                artifact_object_id text,
                summary_json text not null,
                warnings_json text not null,
                errors_json text not null
            );

            create table if not exists pipeline_steps (
                id text primary key,
                run_id text not null,
                step_name text not null,
                status text not null,
                started_at text not null,
                finished_at text,
                duration_seconds real,
                warnings_json text not null,
                errors_json text not null,
                details_json text not null
            );

            create table if not exists alert_events (
                id text primary key,
                event_type text not null,
                severity text not null,
                status text not null default 'open',
                dedupe_key text not null,
                title text not null,
                message text not null,
                source text,
                related_id text,
                details_json text not null,
                first_seen_at text not null,
                last_seen_at text not null,
                count integer not null default 1,
                cooldown_until text,
                acknowledged_at text,
                acknowledged_by text,
                resolved_at text,
                resolved_by text,
                unique(dedupe_key, status)
            );

            create table if not exists alert_deliveries (
                id text primary key,
                alert_id text not null,
                channel text not null,
                status text not null,
                attempt_count integer not null default 0,
                last_attempt_at text,
                last_success_at text,
                next_retry_at text,
                last_error text,
                response_code integer,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(alert_id, channel)
            );

            create table if not exists index_source_artifacts (
                id text primary key,
                index_code text not null,
                source_url text not null,
                local_path text,
                raw_file_hash text not null,
                content_type text,
                parser_version text not null,
                parse_status text not null,
                error text,
                metadata_json text not null,
                fetched_at text not null,
                unique(index_code, source_url, raw_file_hash)
            );

            create table if not exists index_membership_events (
                id text primary key,
                index_code text not null,
                symbol text not null,
                name text,
                action_type text not null,
                adjustment_type text,
                announce_date text not null,
                effective_date text not null,
                source_url text,
                raw_file_hash text,
                batch_id text not null,
                parse_status text not null,
                updated_at text not null,
                unique(index_code, symbol, action_type, effective_date, source_url)
            );

            create view if not exists index_membership_pit as
            select
                universe_code as index_code,
                symbol,
                announce_date,
                effective_date,
                start_date,
                end_date,
                weight,
                source,
                batch_id
            from universe_membership;

            create table if not exists financial_statements (
                symbol text not null,
                statement_type text not null,
                report_date text not null,
                announce_date text not null,
                effective_date text not null,
                fiscal_period text,
                currency text,
                fields_json text not null,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, statement_type, report_date, announce_date, source)
            );

            create table if not exists financial_facts (
                symbol text not null,
                field_name text not null,
                report_date text not null,
                announce_date text not null,
                effective_date text not null,
                value real,
                unit text,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, field_name, report_date, announce_date, source)
            );

            create table if not exists factor_values (
                symbol text not null,
                trade_date text not null,
                factor_name text not null,
                value real not null,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (symbol, trade_date, factor_name, source)
            );

            create table if not exists factor_evaluations (
                id text primary key,
                factor_name text not null,
                universe_code text not null,
                start_date text not null,
                end_date text not null,
                forward_days integer not null,
                quantiles integer not null,
                engine text not null,
                result_json text not null,
                created_at text not null
            );

            create table if not exists cbond_securities (
                bond_code text primary key,
                bond_name text not null,
                stock_symbol text not null,
                listed_date text,
                delisted_date text,
                maturity_date text,
                rating text,
                conversion_price real,
                issue_size real,
                remaining_size real,
                terms_json text,
                source text not null,
                updated_at text not null
            );

            create table if not exists cbond_daily_bars (
                bond_code text not null,
                trade_date text not null,
                close real not null,
                stock_close real,
                conversion_price real,
                conversion_value real,
                premium_rate real,
                remaining_size real,
                double_low real,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (bond_code, trade_date, source)
            );

            create table if not exists cbond_call_events (
                id text primary key,
                bond_code text not null,
                announce_date text not null,
                trigger_date text,
                status text not null,
                call_price real,
                last_trade_date text,
                source text not null,
                created_at text not null
            );

            create table if not exists futures_contracts (
                contract_code text primary key,
                product text not null,
                exchange text not null,
                name text,
                multiplier real,
                margin_rate real,
                tick_size real,
                delivery_month text,
                listed_date text,
                last_trade_date text,
                source text not null,
                updated_at text not null
            );

            create table if not exists futures_daily_bars (
                contract_code text not null,
                trade_date text not null,
                open real,
                high real,
                low real,
                close real,
                volume real,
                open_interest real,
                source text not null,
                batch_id text,
                created_at text not null,
                primary key (contract_code, trade_date, source)
            );

            create table if not exists futures_main_rules (
                product text not null,
                exchange text not null,
                rule_type text not null,
                roll_days_before_expiry integer not null default 0,
                min_open_interest_days integer not null default 1,
                source text not null,
                updated_at text not null,
                primary key (product, exchange)
            );

            create table if not exists futures_main_mapping (
                product text not null,
                exchange text not null,
                trade_date text not null,
                main_symbol text not null,
                continuous_symbol text,
                rule text not null,
                source text not null,
                batch_id text,
                updated_at text not null,
                primary key (product, exchange, trade_date, source)
            );

            create table if not exists recording_jobs (
                id text primary key,
                name text not null,
                asset_class text not null,
                market text not null,
                venue text,
                symbols_json text not null,
                frequency text,
                status text not null,
                source text not null,
                parameters_json text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists recording_status (
                job_id text primary key,
                status text not null,
                last_event_at text,
                last_bar_at text,
                last_error text,
                updated_at text not null
            );

            create table if not exists data_gaps (
                id text primary key,
                dataset text not null,
                asset_class text not null,
                market text not null,
                symbol text,
                start_time text not null,
                end_time text not null,
                severity text not null,
                source text not null,
                details_json text not null,
                created_at text not null
            );

            create table if not exists data_import_batches (
                id text primary key,
                provider text not null,
                market text not null,
                asset_class text not null,
                status text not null,
                config_json text not null,
                qa_report_json text,
                error text,
                started_at text not null,
                finished_at text
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
                duration_seconds real,
                fingerprint_json text,
                validation_json text,
                experiment_json text
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
                performance_json text,
                raw_result_path text,
                raw_result_object_id text,
                summary_object_id text,
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

            create table if not exists insight_reports (
                id text primary key,
                task_id text,
                symbol text not null,
                asset_class text not null,
                market text,
                venue text not null,
                resolution text not null default 'daily',
                data_type text not null default 'trade',
                as_of_date text,
                lookback_bars integer not null,
                backtest_run_id text,
                status text not null,
                model text,
                prompt_version text not null,
                input_fingerprint text,
                context_json text,
                raw_response_json text,
                report_json text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text
            );

            create table if not exists decision_signals (
                id text primary key,
                insight_report_id text not null unique,
                symbol text not null,
                asset_class text not null,
                venue text not null,
                as_of_date text,
                raw_signal_json text not null,
                final_signal_json text not null,
                guardrail_json text not null,
                status text not null,
                paper_session_id text,
                paper_signal_id text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists object_store_items (
                key text primary key,
                file_path text not null,
                stored_object_id text,
                size integer not null,
                updated_at text not null
            );

            create table if not exists stored_objects (
                id text primary key,
                namespace text not null,
                object_key text not null,
                content_type text,
                encoding text not null default 'binary',
                size integer not null,
                sha256 text not null,
                storage_mode text not null default 'database',
                source_path text,
                metadata_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(namespace, object_key, sha256)
            );

            create table if not exists stored_object_chunks (
                object_id text not null,
                chunk_index integer not null,
                data blob not null,
                size integer not null,
                sha256 text not null,
                primary key (object_id, chunk_index)
            );

            create table if not exists settings (
                key text primary key,
                value_json text not null,
                updated_at text not null
            );

            create table if not exists scheduler_leases (
                id text primary key,
                resource text not null,
                slot_index integer not null,
                holder_id text not null,
                limit_count integer not null,
                acquired_at text not null,
                expires_at text not null,
                metadata_json text not null,
                unique(resource, holder_id),
                unique(resource, slot_index)
            );

            create table if not exists strategy_versions (
                id text primary key,
                project_id text,
                strategy_path text,
                source_sha256 text,
                git_commit text,
                git_branch text,
                git_dirty integer not null default 0,
                git_status_hash text,
                metadata_json text not null,
                created_at text not null
            );

            create table if not exists dataset_versions (
                id text primary key,
                dataset_key text not null,
                asset_class text,
                market text,
                venue text,
                resolution text,
                data_type text,
                adjust text,
                symbol text,
                start_date text,
                end_date text,
                row_count integer not null default 0,
                status_count integer not null default 0,
                benchmark_symbol text,
                benchmark_row_count integer not null default 0,
                data_batch_id text,
                lean_zip_sha256 text,
                factor_file_sha256 text,
                parquet_dataset_id text,
                parquet_file_sha256 text,
                metadata_json text not null,
                created_at text not null
            );

            create table if not exists experiments (
                id text primary key,
                run_id text not null unique,
                strategy_version_id text not null,
                dataset_version_id text not null,
                parameter_hash text,
                docker_image text,
                docker_image_digest text,
                git_commit text,
                fingerprint_json text not null,
                validation_json text not null,
                experiment_json text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists strategy_admissions (
                id text primary key,
                strategy_id text not null,
                strategy_version_id text,
                parameters_sha256 text not null,
                profile_name text not null,
                profile_version text not null,
                sample_set text not null,
                current_stage text not null,
                baseline_snapshot_json text not null,
                evaluation_json text not null,
                created_at text not null,
                updated_at text not null,
                unique(strategy_id, parameters_sha256, profile_name, profile_version)
            );

            create table if not exists strategy_admission_events (
                id text primary key,
                admission_id text not null,
                stage text not null,
                source_id text,
                payload_json text not null,
                created_at text not null
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

            create table if not exists paper_signals (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                symbol text not null,
                side text not null,
                target_percent real,
                strength real,
                reason text,
                status text not null,
                source text not null,
                created_at text not null
            );

            create table if not exists paper_orders (
                id text primary key,
                session_id text not null,
                signal_id text,
                trade_date text not null,
                symbol text not null,
                side text not null,
                quantity real not null,
                order_price real,
                fill_price real,
                fee real not null default 0,
                status text not null,
                reason text,
                created_at text not null,
                filled_at text
            );

            create table if not exists paper_positions (
                session_id text not null,
                symbol text not null,
                quantity real not null,
                average_price real not null,
                market_price real,
                market_value real,
                last_buy_date text,
                updated_at text not null,
                primary key (session_id, symbol)
            );

            create table if not exists paper_portfolio_snapshots (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                cash real not null,
                market_value real not null,
                equity real not null,
                positions_json text not null,
                benchmark_symbol text,
                benchmark_close real,
                benchmark_return real,
                created_at text not null,
                unique(session_id, trade_date)
            );

            create table if not exists paper_daily_reports (
                id text primary key,
                session_id text not null,
                trade_date text not null,
                report_json text not null,
                signals_json text not null,
                orders_json text not null,
                trades_json text not null,
                rejects_json text not null,
                positions_json text not null,
                snapshot_json text not null,
                benchmark_json text not null,
                qa_json text not null,
                created_at text not null,
                unique(session_id, trade_date)
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
            create index if not exists idx_reports_run_created
                on reports(run_id, created_at desc);
            create index if not exists idx_reports_status_created
                on reports(status, created_at desc);
            create index if not exists idx_stored_objects_namespace_updated
                on stored_objects(namespace, updated_at desc);
            create index if not exists idx_stored_objects_key_updated
                on stored_objects(object_key, updated_at desc);
            create index if not exists idx_instruments_symbol
                on instruments(asset_class, market, venue, symbol);
            create index if not exists idx_instruments_status
                on instruments(asset_class, market, status, listed_date, delisted_date);
            create index if not exists idx_market_daily_symbol_date
                on market_daily_bars(asset_class, market, symbol, trade_date);
            create index if not exists idx_market_daily_instrument_date
                on market_daily_bars(instrument_id, trade_date);
            create index if not exists idx_market_status_symbol_date
                on market_trade_status(asset_class, market, symbol, trade_date);
            create index if not exists idx_market_intraday_symbol_time
                on market_intraday_bars(asset_class, market, symbol, frequency, timestamp);
            create index if not exists idx_market_ticks_symbol_time
                on market_ticks(asset_class, market, symbol, timestamp);
            create index if not exists idx_parquet_datasets_lookup
                on parquet_datasets(asset_class, market, venue, resolution, data_type, adjust, source);
            create index if not exists idx_parquet_files_dataset
                on parquet_files(dataset_id, first_timestamp, last_timestamp);
            create index if not exists idx_data_quality_reports_lookup
                on data_quality_reports(report_type, asset_class, market, symbol, created_at desc);
            create index if not exists idx_securities_market_status
                on securities(market, status);
            create index if not exists idx_ashare_daily_symbol_date
                on ashare_daily_bars(symbol, trade_date);
            create index if not exists idx_ashare_status_symbol_date
                on ashare_trade_status(symbol, trade_date);
            create index if not exists idx_corporate_actions_symbol_date
                on corporate_actions(symbol, ex_date);
            create index if not exists idx_universe_asof
                on universe_membership(universe_code, start_date, end_date);
            create index if not exists idx_index_weights_date
                on index_weights(universe_code, trade_date, symbol);
            create index if not exists idx_paper_universe_cert_status
                on paper_universe_certifications(universe_code, certification_status, certification_date);
            create index if not exists idx_paper_universe_symbols_status
                on paper_universe_symbols(universe_code, certification_status, symbol);
            create index if not exists idx_qa_warning_allowlist_code
                on qa_warning_allowlist(warning_code, status, valid_until);
            create index if not exists idx_provider_availability_checked
                on provider_availability_log(provider, checked_at);
            create index if not exists idx_pipeline_runs_created
                on pipeline_runs(started_at desc, status);
            create index if not exists idx_pipeline_steps_run
                on pipeline_steps(run_id, step_name);
            create index if not exists idx_alert_events_status
                on alert_events(status, event_type, last_seen_at);
            create index if not exists idx_alert_deliveries_status
                on alert_deliveries(status, updated_at);
            create index if not exists idx_alert_deliveries_alert
                on alert_deliveries(alert_id, channel);
            create index if not exists idx_index_events_asof
                on index_membership_events(index_code, effective_date, announce_date, symbol);
            create index if not exists idx_index_artifacts_code
                on index_source_artifacts(index_code, fetched_at);
            create index if not exists idx_financial_statements_pit
                on financial_statements(symbol, statement_type, effective_date, announce_date, report_date);
            create index if not exists idx_financial_facts_pit
                on financial_facts(symbol, field_name, effective_date, announce_date, report_date);
            create index if not exists idx_factor_values_name_date
                on factor_values(factor_name, trade_date, symbol);
            create index if not exists idx_factor_values_symbol_date
                on factor_values(symbol, trade_date);
            create index if not exists idx_factor_evaluations_created_at
                on factor_evaluations(created_at desc);
            create index if not exists idx_cbond_daily_date
                on cbond_daily_bars(trade_date, bond_code);
            create index if not exists idx_cbond_stock_symbol
                on cbond_securities(stock_symbol);
            create index if not exists idx_cbond_call_events_date
                on cbond_call_events(announce_date, last_trade_date, status);
            create index if not exists idx_futures_contracts_product
                on futures_contracts(product, exchange, last_trade_date);
            create index if not exists idx_futures_daily_date
                on futures_daily_bars(trade_date, contract_code);
            create index if not exists idx_futures_main_mapping_date
                on futures_main_mapping(product, exchange, trade_date);
            create index if not exists idx_data_gaps_lookup
                on data_gaps(dataset, asset_class, market, symbol);
            create index if not exists idx_import_batches_started_at
                on data_import_batches(started_at desc);
            create index if not exists idx_stored_objects_lookup
                on stored_objects(namespace, object_key, updated_at);
            create index if not exists idx_stored_objects_hash
                on stored_objects(sha256);
            create index if not exists idx_scheduler_leases_resource
                on scheduler_leases(resource, expires_at);
            create index if not exists idx_strategy_versions_project
                on strategy_versions(project_id, created_at desc);
            create index if not exists idx_dataset_versions_lookup
                on dataset_versions(asset_class, market, symbol, start_date, end_date);
            create index if not exists idx_experiments_run
                on experiments(run_id);
            create index if not exists idx_strategy_admissions_lookup
                on strategy_admissions(strategy_id, parameters_sha256, updated_at desc);
            create index if not exists idx_strategy_admission_events
                on strategy_admission_events(admission_id, created_at);
            create index if not exists idx_paper_sessions_created_at
                on paper_sessions(created_at desc);
            create index if not exists idx_paper_signals_session_date
                on paper_signals(session_id, trade_date);
            create index if not exists idx_paper_orders_session_date
                on paper_orders(session_id, trade_date);
            create index if not exists idx_paper_snapshots_session_date
                on paper_portfolio_snapshots(session_id, trade_date);
            create index if not exists idx_paper_reports_session_date
                on paper_daily_reports(session_id, trade_date);
            create index if not exists idx_insight_reports_created
                on insight_reports(created_at desc);
            create index if not exists idx_insight_reports_asset_symbol
                on insight_reports(asset_class, venue, symbol, created_at desc);
            create index if not exists idx_decision_signals_status
                on decision_signals(status, created_at desc);
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
        _add_column(connection, "backtest_runs", "fingerprint_json", "text")
        _add_column(connection, "backtest_runs", "validation_json", "text")
        _add_column(connection, "backtest_runs", "experiment_json", "text")
        _add_column(connection, "scheduler_leases", "slot_index", "integer not null default 0")
        _add_column(connection, "data_assets", "asset_class", "text not null default 'equity'")
        _add_column(connection, "data_assets", "venue", "text")
        _add_column(connection, "data_assets", "resolution", "text not null default 'daily'")
        _add_column(connection, "data_assets", "data_type", "text not null default 'trade'")
        _add_column(connection, "data_assets", "status", "text not null default 'active'")
        _add_column(connection, "data_assets", "superseded_by", "integer")
        _add_column(connection, "data_assets", "superseded_at", "text")
        _add_column(connection, "data_assets", "superseded_reason", "text")
        _add_column(connection, "backtest_results", "performance_json", "text")
        _add_column(connection, "backtest_results", "raw_result_object_id", "text")
        _add_column(connection, "backtest_results", "summary_object_id", "text")
        _add_column(connection, "data_assets", "lean_object_id", "text")
        _add_column(connection, "data_assets", "factor_object_id", "text")
        _add_column(connection, "object_store_items", "stored_object_id", "text")
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_symbol", "text")
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_close", "real")
        from .migrations.runner import run_migrations

        run_migrations(connection, utc_now)
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_return", "real")
        _add_column(connection, "universe_membership", "announce_date", "text")
        _add_column(connection, "universe_membership", "effective_date", "text")
        _add_column(connection, "index_membership_events", "adjustment_type", "text")
        connection.execute(
            "create index if not exists idx_backtest_runs_asset on backtest_runs(asset_class, venue, symbol)"
        )
        connection.execute(
            "create index if not exists idx_data_assets_status_created on data_assets(status, created_at desc)"
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
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def relative_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(Path(path))
