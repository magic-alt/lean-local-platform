#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLES = (
    "schema_migrations",
    "paper_accounts",
    "paper_ledger_entries",
    "paper_account_checkpoints",
    "stored_objects",
)


def _connection_options(url: str, *, database: str | None = None) -> dict[str, Any]:
    parsed = urlsplit(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("postgresql_database_url_invalid")
    return {
        "host": parsed.hostname,
        "port": int(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
        "dbname": database or ((parsed.path or "/postgres").strip("/") or "postgres"),
    }


def _table_evidence(source, target, table: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError(f"unsafe_table_name:{table}")
    from psycopg import sql

    statement = sql.SQL(
        """
        select count(*) as row_count,
               md5(coalesce(string_agg(row_digest, '' order by row_digest), '')) as content_digest
        from (
            select md5(row_to_json(item)::text) as row_digest
            from {} as item
        ) rows
        """
    ).format(sql.Identifier(table))
    with source.cursor() as cursor:
        cursor.execute(statement)
        source_count, source_digest = cursor.fetchone()
    with target.cursor() as cursor:
        cursor.execute(statement)
        target_count, target_digest = cursor.fetchone()
    return {
        "table": table,
        "sourceRows": int(source_count),
        "targetRows": int(target_count),
        "rowCountDiff": int(target_count) - int(source_count),
        "sourceDigest": str(source_digest),
        "targetDigest": str(target_digest),
        "checksumMatch": source_digest == target_digest,
        "passed": source_count == target_count and source_digest == target_digest,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != "RESTORE_ISOLATED_DATABASE":
        raise ValueError("explicit_restore_confirmation_required")
    if not re.fullmatch(r"lean_restore_[a-z0-9_]+", args.target_prefix):
        raise ValueError("unsafe_restore_target_prefix")
    backup = args.backup.resolve()
    started = datetime.now(timezone.utc)
    restore_started = time.monotonic()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "restore_postgres.py"),
            str(backup),
            "--target-prefix",
            args.target_prefix,
        ],
        cwd=ROOT,
        env=dict(os.environ),
        text=True,
        capture_output=True,
        check=False,
    )
    rto_seconds = round(time.monotonic() - restore_started, 3)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg_required_in_backend_environment") from exc
    source_url = os.environ.get("LEAN_DATABASE_URL", "").strip()
    if not source_url:
        raise RuntimeError("LEAN_DATABASE_URL_required")
    source = psycopg.connect(**_connection_options(source_url))
    target = psycopg.connect(
        **_connection_options(
            os.environ.get("LEAN_POSTGRES_ADMIN_URL", source_url),
            database=f"{args.target_prefix}_platform",
        )
    )
    try:
        table_results = [_table_evidence(source, target, table) for table in args.table]
    finally:
        source.close()
        target.close()
    backup_age = max(0.0, started.timestamp() - backup.stat().st_mtime)
    passed = bool(table_results) and all(item["passed"] for item in table_results)
    return {
        "schemaVersion": 2,
        "databaseEngine": "postgresql",
        "passed": passed,
        "status": "RESTORE_DRILL_PASS" if passed else "RESTORE_DRILL_FAIL",
        "startedAt": started.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "backup": str(backup),
        "sourceDatabase": _connection_options(source_url)["dbname"],
        "targetDatabase": f"{args.target_prefix}_platform",
        "rpoSeconds": round(backup_age, 3),
        "rtoSeconds": rto_seconds,
        "rowCountDiff": sum(abs(int(item["rowCountDiff"])) for item in table_results),
        "checksumMatch": all(item["checksumMatch"] for item in table_results),
        "tables": table_results,
        "restoreOutput": completed.stdout.strip().splitlines()[-5:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore PostgreSQL backups into isolated databases and verify row digests."
    )
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target-prefix", default="lean_restore_drill")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--table", action="append", default=list(DEFAULT_TABLES))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    evidence_path = args.evidence or (
        ROOT
        / "web"
        / "runtime"
        / "audit"
        / f"restore-drill-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    try:
        payload = run(args)
        exit_code = 0 if payload["passed"] else 1
    except Exception as exc:
        payload = {
            "schemaVersion": 2,
            "databaseEngine": "postgresql",
            "passed": False,
            "status": "RESTORE_DRILL_FAIL",
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
        exit_code = 1
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(payload["status"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
