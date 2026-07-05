import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from .core.config import (
    DATABASE_URL,
    DB_PATH,
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
    from pymysql.cursors import DictCursor
except Exception:  # pragma: no cover
    pymysql = None
    DictCursor = None


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
    "positions_json": "positions",
    "concepts_json": "concepts",
    "qa_report_json": "qa_report",
    "fields_json": "fields",
    "terms_json": "terms",
    "partition_json": "partition",
    "sources_json": "sources",
    "symbols_json": "symbols",
    "details_json": "details",
}


MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
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
    "result_json",
    "fields_json",
    "terms_json",
    "concepts_json",
    "symbols_json",
    "details_json",
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
    return "sqlite"


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
    return {"engine": "sqlite", "path": str(DB_PATH), "url": f"sqlite:///{DB_PATH}"}


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
    def __init__(self) -> None:
        if pymysql is None or DictCursor is None:
            raise RuntimeError("pymysql is required when LEAN_DATABASE_URL uses mysql+pymysql.")
        parsed = urlparse(DATABASE_URL)
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
        translated = _translate_mysql_sql(sql)
        index_info = _parse_create_index_if_not_exists(translated)
        if index_info:
            index_name, table_name = index_info
            with self._connection.cursor() as cursor:
                cursor.execute("show index from `%s` where Key_name = %%s" % table_name, (index_name,))
                if cursor.fetchone():
                    return cursor
            translated = re.sub(r"\bcreate\s+index\s+if\s+not\s+exists\b", "create index", translated, flags=re.IGNORECASE)
        cursor = self._connection.cursor()
        cursor.execute(translated, parameters)
        return cursor

    def executemany(self, sql: str, parameters: Iterable[Iterable[Any] | dict[str, Any]]):
        cursor = self._connection.cursor()
        cursor.executemany(_translate_mysql_sql(sql), parameters)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in _split_sql_script(script):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


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


def _parse_create_index_if_not_exists(sql: str) -> tuple[str, str] | None:
    match = re.match(r"\s*create\s+index\s+if\s+not\s+exists\s+`?([A-Za-z0-9_]+)`?\s+on\s+`?([A-Za-z0-9_]+)`?", sql, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1), match.group(2)


def _mysql_text_type(column: str) -> str:
    column = column.strip("`").lower()
    if column in ID_TEXT_COLUMNS or column.endswith("_id"):
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
        return MySQLConnection()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db() -> Iterable[sqlite3.Connection | MySQLConnection]:
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


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
                fingerprint_json text
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
            create index if not exists idx_paper_sessions_created_at
                on paper_sessions(created_at desc);
            create index if not exists idx_paper_signals_session_date
                on paper_signals(session_id, trade_date);
            create index if not exists idx_paper_orders_session_date
                on paper_orders(session_id, trade_date);
            create index if not exists idx_paper_snapshots_session_date
                on paper_portfolio_snapshots(session_id, trade_date);
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
        _add_column(connection, "data_assets", "asset_class", "text not null default 'equity'")
        _add_column(connection, "data_assets", "venue", "text")
        _add_column(connection, "data_assets", "resolution", "text not null default 'daily'")
        _add_column(connection, "data_assets", "data_type", "text not null default 'trade'")
        _add_column(connection, "backtest_results", "performance_json", "text")
        _add_column(connection, "backtest_results", "raw_result_object_id", "text")
        _add_column(connection, "backtest_results", "summary_object_id", "text")
        _add_column(connection, "data_assets", "lean_object_id", "text")
        _add_column(connection, "data_assets", "factor_object_id", "text")
        _add_column(connection, "object_store_items", "stored_object_id", "text")
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_symbol", "text")
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_close", "real")
        _add_column(connection, "paper_portfolio_snapshots", "benchmark_return", "real")
        _add_column(connection, "universe_membership", "announce_date", "text")
        _add_column(connection, "universe_membership", "effective_date", "text")
        _add_column(connection, "index_membership_events", "adjustment_type", "text")
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
