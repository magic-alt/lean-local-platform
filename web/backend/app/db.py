import json
import logging
import os
import re
import sqlite3
import time
import uuid
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

try:  # pragma: no cover - optional unless LEAN_DATABASE_URL points at PostgreSQL.
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None
    ConnectionPool = None


logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """Raised after transient database connection failures exhaust bounded retries."""


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
    "certificate_json": "certificate",
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
    "runtime_identity_json": "runtimeIdentity",
    "sandbox_json": "sandbox",
    "final_signal_json": "finalSignal",
    "guardrail_json": "guardrail",
    "data_completeness_json": "dataCompleteness",
    "source_conflicts_json": "sourceConflicts",
    "source_manifest_json": "sourceManifest",
    "pool_snapshot_json": "poolSnapshot",
    "rule_tags_json": "ruleTags",
    "checkpoint_json": "checkpoint",
    "requested_datasets_json": "requestedDatasets",
    "requested_layers_json": "requested_layers",
    "metrics_json": "metrics",
    "derived_status_json": "derivedStatus",
    "endpoint_counts_json": "endpointCounts",
    "universe_config_json": "universeConfig",
    "projection_json": "projection",
    "agent_summary_json": "agentSummary",
    "stage_summary_json": "stageSummary",
    "usage_json": "usage",
    "input_fact_ids_json": "inputFactIds",
    "probabilities_json": "probabilities",
    "evidence_ids_json": "evidenceIds",
    "output_json": "output",
    "stage_prompts_json": "stagePrompts",
    "prompt_snapshot_json": "promptSnapshot",
    "evidence_json": "evidence",
    "run_ids_json": "runIds",
    "constraints_json": "constraints",
    "input_fingerprints_json": "inputFingerprints",
    "manifest_json": "manifest",
    "quality_json": "quality",
    "fold_plan_json": "foldPlan",
    "request_scope_json": "requestScope",
    "batch_snapshot_json": "batchSnapshot",
    "project_snapshot_json": "projectSnapshot",
    "selection_inputs_json": "selectionInputs",
    "selection_outputs_json": "selectionOutputs",
    "contract_json": "contract",
    "certificate_json": "certificate",
}


POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+psycopg"}
SQLITE_SCHEMES = {"sqlite", "sqlite+pysqlite"}
SQLITE_TEST_BACKEND_ENABLED = os.environ.get("LEAN_ALLOW_SQLITE_TEST_DB", "").lower() in {"1", "true", "yes", "on"}
DB_PATH: Path | None = None
def database_url() -> str:
    return DATABASE_URL


def database_backend() -> str:
    scheme = urlparse(DATABASE_URL).scheme.lower()
    if scheme in POSTGRES_SCHEMES:
        return "postgresql"
    if scheme in SQLITE_SCHEMES and SQLITE_TEST_BACKEND_ENABLED:
        return "sqlite"
    if scheme in SQLITE_SCHEMES:
        raise RuntimeError(
            "SQLite is disabled for runtime database use. Configure LEAN_DATABASE_URL with postgresql; "
            "use DuckDB only through the Parquet research layer."
        )
    raise RuntimeError(f"Unsupported database backend: {scheme or 'empty'}")


def _sqlite_db_path() -> Path:
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme.lower() in SQLITE_SCHEMES and parsed.path:
        raw_path = unquote(parsed.path)
        if os.name == "nt" and re.match(r"^/[A-Za-z]:[/\\]", raw_path):
            raw_path = raw_path[1:]
        return Path(raw_path).expanduser()
    if DB_PATH is not None:
        return DB_PATH
    raise RuntimeError("SQLite test backend requires an explicit sqlite:/// path.")


def database_descriptor() -> dict[str, Any]:
    if database_backend() == "postgresql":
        parsed = urlparse(DATABASE_URL)
        return {
            "engine": "postgresql",
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 5432,
            "database": (parsed.path or "/lean_platform").lstrip("/"),
            "user": unquote(parsed.username or "lean_app"),
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


_POSTGRES_POOLS: dict[tuple[int, str], Any] = {}


def _postgres_conninfo(database_url: str) -> str:
    parsed = urlparse(database_url)
    scheme = "postgresql"
    return parsed._replace(scheme=scheme).geturl()


def _postgres_pool(database_url: str | None = None):
    if ConnectionPool is None or dict_row is None:
        raise RuntimeError(
            "psycopg and psycopg_pool are required when LEAN_DATABASE_URL uses PostgreSQL."
        )
    url = _postgres_conninfo(database_url or DATABASE_URL)
    key = (os.getpid(), url)
    pool = _POSTGRES_POOLS.get(key)
    if pool is None:
        pool = ConnectionPool(
            conninfo=url,
            min_size=max(1, int(os.environ.get("LEAN_POSTGRES_POOL_MIN_SIZE", "1"))),
            max_size=max(2, int(os.environ.get("LEAN_POSTGRES_POOL_MAX_SIZE", "10"))),
            timeout=max(1.0, float(os.environ.get("LEAN_POSTGRES_POOL_TIMEOUT_SECONDS", "5"))),
            kwargs={"autocommit": False, "row_factory": dict_row},
            open=False,
            name=f"lean-platform-{os.getpid()}",
        )
        pool.open(wait=True)
        _POSTGRES_POOLS[key] = pool
    return pool


class PostgresConnection:
    """SQLite-shaped connection facade backed by a process-local psycopg pool."""

    def __init__(self, database_url: str | None = None) -> None:
        self._pool = _postgres_pool(database_url)
        self._connection = self._pool.getconn()

    def execute(self, sql: str, parameters: Iterable[Any] | dict[str, Any] | None = None):
        cursor = self._connection.cursor()
        cursor.execute(_translate_postgres_sql(_strip_leading_sql_comments(sql)), parameters)
        return cursor

    def executemany(self, sql: str, parameters: Iterable[Iterable[Any] | dict[str, Any]]):
        cursor = self._connection.cursor()
        cursor.executemany(_translate_postgres_sql(sql), parameters)
        return cursor

    def iter_batches(
        self,
        sql: str,
        parameters: Iterable[Any] | dict[str, Any] | None = None,
        *,
        batch_size: int = 100_000,
    ) -> Iterable[list[dict[str, Any]]]:
        cursor = self._connection.cursor(name=f"platform_stream_{uuid.uuid4().hex}")
        try:
            cursor.execute(_translate_postgres_sql(sql), parameters)
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
        connection, self._connection = self._connection, None
        if connection is not None:
            self._pool.putconn(connection)


def _transient_postgres_connection_error(exc: Exception) -> bool:
    sqlstate = str(getattr(exc, "sqlstate", "") or "")
    operational = bool(psycopg is not None and isinstance(exc, psycopg.OperationalError))
    return operational or sqlstate.startswith("08") or sqlstate in {"53300", "57P01", "57P02", "57P03"}


def _connect_postgres(database_url: str | None = None) -> PostgresConnection:
    attempts = max(1, min(int(os.environ.get("LEAN_POSTGRES_CONNECT_ATTEMPTS", "5")), 10))
    base_delay = max(
        0.0,
        min(float(os.environ.get("LEAN_POSTGRES_CONNECT_RETRY_DELAY_SECONDS", "0.5")), 5.0),
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return PostgresConnection(database_url)
        except Exception as exc:
            if not _transient_postgres_connection_error(exc):
                raise
            last_error = exc
            if attempt >= attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), 5.0)
            logger.warning(
                "PostgreSQL connection unavailable (attempt %s/%s); retrying in %.1fs: %s",
                attempt,
                attempts,
                delay,
                exc,
            )
            time.sleep(delay)
    raise DatabaseUnavailableError(
        f"PostgreSQL is temporarily unavailable after {attempts} connection attempts."
    ) from last_error


def _rollback_quietly(connection: sqlite3.Connection | PostgresConnection) -> None:
    try:
        connection.rollback()
    except Exception:
        logger.warning("Database rollback failed after the original operation error", exc_info=True)


def _close_quietly(connection: sqlite3.Connection | PostgresConnection) -> None:
    try:
        connection.close()
    except Exception:
        logger.warning("Database connection close failed", exc_info=True)


def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    previous = ""
    for index, char in enumerate(script):
        if in_line_comment:
            current.append(char)
            if char in {"\n", "\r"}:
                in_line_comment = False
            previous = char
            continue
        if (
            char == "-"
            and index + 1 < len(script)
            and script[index + 1] == "-"
            and not in_single
            and not in_double
        ):
            in_line_comment = True
            current.append(char)
            previous = char
            continue
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


def _translate_postgres_sql(sql: str) -> str:
    """Translate the repository's portable SQLite-shaped SQL to PostgreSQL."""

    translated = sql.strip()
    translated = re.sub(r"\?", "%s", translated)
    translated = translated.replace("`", '"')
    translated = re.sub(
        r"\binteger\s+primary\s+key\s+autoincrement\b",
        "bigserial primary key",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"\blongtext\b", "text", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdatetime\s*\(\s*6\s*\)", "text", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\blongblob\b|\bblob\b", "bytea", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdouble\b(?!\s+precision)", "double precision", translated, flags=re.IGNORECASE)
    if re.match(r"create\s+view\s+if\s+not\s+exists", translated, flags=re.IGNORECASE):
        translated = re.sub(
            r"create\s+view\s+if\s+not\s+exists",
            "create or replace view",
            translated,
            count=1,
            flags=re.IGNORECASE,
        )
    translated = re.sub(r'(?<![\w"])(rows|key)(?![\w"])', r'"\1"', translated, flags=re.IGNORECASE)
    translated = re.sub(r'\bprimary\s+"key"', "primary key", translated, flags=re.IGNORECASE)
    translated = re.sub(r'\bforeign\s+"key"', "foreign key", translated, flags=re.IGNORECASE)
    return translated


def connect() -> sqlite3.Connection | PostgresConnection:
    init_storage()
    if database_backend() == "postgresql":
        return _connect_postgres()
    connection = sqlite3.connect(_sqlite_db_path())
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def db() -> Iterable[sqlite3.Connection | PostgresConnection]:
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
def bulk_db() -> Iterable[sqlite3.Connection | PostgresConnection]:
    """Use the same transactional PostgreSQL pool for control-plane bulk writes."""
    with db() as connection:
        yield connection


def _columns(
    connection: sqlite3.Connection | PostgresConnection,
    table: str,
) -> set[str]:
    if database_backend() == "postgresql":
        rows = connection.execute(
            """
            select column_name
            from information_schema.columns
            where table_schema = current_schema() and table_name = ?
            """,
            (table,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    return {row["name"] for row in connection.execute(f"pragma table_info({table})")}


def _add_column(
    connection: sqlite3.Connection | PostgresConnection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _columns(connection, table):
        connection.execute(f"alter table {table} add column {column} {definition}")


def init_db(*, apply_migrations: bool = False) -> None:
    init_storage()
    if database_backend() == "postgresql":
        from .migrations.runner import (
            run_postgres_migrations,
            verify_postgres_migrations_read_only,
        )
        from .services.database_invariants import assert_control_plane_schema

        with db() as connection:
            if apply_migrations:
                run_postgres_migrations(connection, utc_now)
            else:
                verification = verify_postgres_migrations_read_only(connection)
                incomplete = [
                    item["revision"]
                    for item in verification
                    if item["status"] != "applied"
                ]
                if incomplete:
                    raise RuntimeError(
                        "PostgreSQL migrations must be applied by platformctl/migration service: "
                        + ", ".join(incomplete)
                    )
            assert_control_plane_schema(connection)
        return
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

            create table if not exists research_workspaces (
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
                finished_at text,
                readiness_status text,
                container_status text,
                workspace_path text,
                last_checked_at text,
                project_name text,
                snapshot_id text
            );

            create table if not exists research_runs (
                id text primary key,
                task_id text,
                template_key text not null,
                name text not null,
                status text not null,
                scope_json text not null,
                parameters_json text not null,
                result_json text,
                summary_json text,
                data_fingerprint text,
                source_research_run_id text,
                error text,
                cancel_requested integer not null default 0,
                created_at text not null,
                started_at text,
                finished_at text
            );

            create table if not exists research_run_items (
                id text primary key,
                run_id text not null,
                item_index integer not null,
                item_key text not null,
                status text not null,
                parameters_json text not null,
                result_json text,
                error text,
                created_at text not null,
                started_at text,
                finished_at text,
                unique(run_id, item_key)
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
            create index if not exists idx_parquet_datasets_lookup
                on parquet_datasets(asset_class, market, venue, resolution, data_type, adjust, source);
            create index if not exists idx_parquet_files_dataset
                on parquet_files(dataset_id, first_timestamp, last_timestamp);
            create index if not exists idx_data_quality_reports_lookup
                on data_quality_reports(report_type, asset_class, market, symbol, created_at desc);
            create index if not exists idx_securities_market_status
                on securities(market, status);
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
        # Revision 0035 retires the legacy table. The compatibility bootstrap
        # above still creates it so older migrations can run on a fresh test
        # database; remove it after the ordered migration chain is complete.
        connection.execute("drop table if exists optimization_runs")
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
              and not exists (
                  select 1 from restricted_runner_jobs runner
                  where runner.run_id=backtest_runs.id and runner.status='success'
              )
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
              and not exists (
                  select 1 from backtest_runs run
                  join restricted_runner_jobs runner
                    on runner.run_id=run.id and runner.status='success'
                  where run.task_id=tasks.id
              )
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


def try_advisory_lock(connection: Any, name: str) -> bool:
    """Acquire a session-scoped deployment-neutral advisory lock."""

    backend = database_backend()
    if backend == "postgresql":
        row = connection.execute(
            "select pg_try_advisory_lock(hashtext(?)) as acquired", (name,)
        ).fetchone()
        return bool(row and row["acquired"])
    return True


def release_advisory_lock(connection: Any, name: str) -> None:
    backend = database_backend()
    if backend == "postgresql":
        connection.execute("select pg_advisory_unlock(hashtext(?))", (name,))


def advisory_lock_in_use(name: str) -> bool:
    """Probe a lock using an independent session without stealing ownership."""

    if database_backend() == "sqlite":
        return False
    with db() as connection:
        if try_advisory_lock(connection, name):
            release_advisory_lock(connection, name)
            return False
        return True


def for_update_clause(*, skip_locked: bool = False) -> str:
    if database_backend() != "postgresql":
        return ""
    return " for update skip locked" if skip_locked else " for update"


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
