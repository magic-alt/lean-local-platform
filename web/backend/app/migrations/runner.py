from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
import re
import time
from typing import Any


VERSIONS_DIR = Path(__file__).parent / "versions"
OBSOLETE_MARKET_INDEX_MIGRATIONS = {
    "0043_p1_lineage_query_index",
    "0050_daily_reconciliation_indexes",
}
IDEMPOTENT_RECONCILIATION_MIGRATIONS = {
    "0053_reconcile_instrument_identifier_columns",
}


def _description(script: str, revision: str) -> str:
    for line in script.splitlines():
        cleaned = line.strip()
        if cleaned.lower().startswith("-- description:"):
            return cleaned.split(":", 1)[1].strip()
        if cleaned and not cleaned.startswith("--"):
            break
    return revision


def _checksum(script: str) -> str:
    return hashlib.sha256(script.encode("utf-8")).hexdigest()


def _columns(connection: Any, table: str) -> set[str]:
    try:
        rows = connection.execute(f"show columns from `{table}`").fetchall()
        return {row["Field"] for row in rows}
    except Exception:
        rows = connection.execute(f"pragma table_info({table})").fetchall()
        return {row["name"] if "name" in row.keys() else row[1] for row in rows}


def _table_exists(connection: Any, table: str) -> bool:
    return bool(_columns(connection, table))


def _run_idempotent_reconciliation(connection: Any, script: str) -> None:
    """Apply additive repair statements on both SQLite tests and MySQL.

    SQLite has no portable ``add column if not exists`` syntax, while MySQL
    installations may be missing any subset of columns whose original
    migrations are already recorded. Check each target explicitly.
    """
    for raw_statement in script.split(";"):
        statement = "\n".join(
            line for line in raw_statement.strip().splitlines()
            if not line.strip().startswith("--")
        ).strip()
        if not statement:
            continue
        match = re.match(
            r"alter\s+table\s+`?([A-Za-z0-9_]+)`?\s+add\s+column\s+`?([A-Za-z0-9_]+)`?",
            statement,
            flags=re.IGNORECASE,
        )
        if match and match.group(2) in _columns(connection, match.group(1)):
            continue
        connection.execute(statement)


def _ensure_schema_migrations_columns(connection: Any) -> None:
    columns = _columns(connection, "schema_migrations")
    if "checksum" not in columns:
        connection.execute("alter table schema_migrations add column checksum text")
    if "execution_time_ms" not in columns:
        connection.execute("alter table schema_migrations add column execution_time_ms integer")


def migration_files() -> list[dict[str, Any]]:
    items = []
    for path in sorted(VERSIONS_DIR.glob("*.sql")):
        script = path.read_text(encoding="utf-8")
        items.append(
            {
                "revision": path.stem,
                "path": str(path),
                "description": _description(script, path.stem),
                "checksum": _checksum(script),
                "script": script,
            }
        )
    return items


def migration_status(connection: Any) -> list[dict[str, Any]]:
    connection.executescript(
        """
        create table if not exists schema_migrations (
            revision text primary key,
            description text not null,
            applied_at text not null
        );
        """
    )
    _ensure_schema_migrations_columns(connection)
    rows = connection.execute("select * from schema_migrations").fetchall()
    applied = {row["revision"]: dict(row) for row in rows}
    result = []
    for item in migration_files():
        row = applied.get(item["revision"])
        if not row:
            result.append({**{key: item[key] for key in ("revision", "description", "checksum", "path")}, "status": "pending"})
            continue
        stored_checksum = row.get("checksum")
        status = "applied" if not stored_checksum or stored_checksum == item["checksum"] else "checksum_mismatch"
        result.append(
            {
                **{key: item[key] for key in ("revision", "description", "checksum", "path")},
                "status": status,
                "appliedAt": row.get("applied_at"),
                "storedChecksum": stored_checksum,
                "executionTimeMs": row.get("execution_time_ms"),
            }
        )
    return result


def verify_migrations(connection: Any) -> list[dict[str, Any]]:
    status = migration_status(connection)
    mismatches = [item for item in status if item["status"] == "checksum_mismatch"]
    if mismatches:
        revisions = ", ".join(item["revision"] for item in mismatches)
        raise RuntimeError(f"Migration checksum mismatch: {revisions}")
    return status


def run_migrations(connection: Any, now: Callable[[], str]) -> None:
    connection.executescript(
        """
        create table if not exists schema_migrations (
            revision text primary key,
            description text not null,
            applied_at text not null
        );
        """
    )
    _ensure_schema_migrations_columns(connection)
    applied_rows = connection.execute("select * from schema_migrations").fetchall()
    applied = {row["revision"]: dict(row) for row in applied_rows}
    for item in migration_files():
        revision = item["revision"]
        row = applied.get(revision)
        if row:
            stored_checksum = row.get("checksum")
            if stored_checksum and stored_checksum != item["checksum"]:
                raise RuntimeError(f"Migration checksum mismatch: {revision}")
            if not stored_checksum:
                connection.execute(
                    "update schema_migrations set checksum = ?, execution_time_ms = coalesce(execution_time_ms, 0) where revision = ?",
                    (item["checksum"], revision),
                )
            continue
        script = item["script"]
        started = time.perf_counter()
        skip_obsolete_index = (
            revision in OBSOLETE_MARKET_INDEX_MIGRATIONS
            and not _table_exists(connection, "market_daily_bars")
        )
        if script.strip() and not skip_obsolete_index:
            if revision in IDEMPOTENT_RECONCILIATION_MIGRATIONS:
                _run_idempotent_reconciliation(connection, script)
            else:
                connection.executescript(script)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        connection.execute(
            """
            insert into schema_migrations
                (revision, description, applied_at, checksum, execution_time_ms)
            values (?, ?, ?, ?, ?)
            """,
            (revision, item["description"], now(), item["checksum"], elapsed_ms),
        )
