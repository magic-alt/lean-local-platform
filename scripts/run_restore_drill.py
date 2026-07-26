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


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLES = (
    "schema_migrations",
    "paper_accounts",
    "paper_ledger_entries",
    "paper_account_checkpoints",
    "stored_objects",
)


def _mysql_value(database: str, sql: str, password: str) -> str:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "-p",
            os.environ.get("LEAN_COMPOSE_PROJECT_NAME", "lean-platform"),
            "exec",
            "-T",
            "-e",
            f"MYSQL_PWD={password}",
            os.environ.get("LEAN_MYSQL_SERVICE", "mysql"),
            "mysql",
            "--user=root",
            "--batch",
            "--skip-column-names",
            database,
            "-e",
            sql,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _table_evidence(source: str, target: str, table: str, password: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_]+", table):
        raise ValueError(f"unsafe_table_name:{table}")
    source_count = int(_mysql_value(source, f"select count(*) from `{table}`", password))
    target_count = int(_mysql_value(target, f"select count(*) from `{table}`", password))
    source_checksum = _mysql_value(source, f"checksum table `{table}`", password).split("\t")[-1]
    target_checksum = _mysql_value(target, f"checksum table `{table}`", password).split("\t")[-1]
    return {
        "table": table,
        "sourceRows": source_count,
        "targetRows": target_count,
        "rowCountDiff": target_count - source_count,
        "sourceChecksum": source_checksum,
        "targetChecksum": target_checksum,
        "checksumMatch": bool(source_checksum and source_checksum == target_checksum),
        "passed": source_count == target_count and bool(source_checksum) and source_checksum == target_checksum,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != "RESTORE_ISOLATED_DATABASE":
        raise ValueError("explicit_restore_confirmation_required")
    if not re.fullmatch(r"lean_restore_[A-Za-z0-9_]+", args.target_database):
        raise ValueError("unsafe_restore_target")
    password = os.environ.get("LEAN_MYSQL_ROOT_PASSWORD", "").strip()
    if not password:
        raise RuntimeError("LEAN_MYSQL_ROOT_PASSWORD_required")
    backup = args.backup.resolve()
    started = datetime.now(timezone.utc)
    restore_started = time.monotonic()
    environment = dict(os.environ)
    environment["LEAN_MYSQL_ROOT_PASSWORD"] = password
    completed = subprocess.run(
        [
            str(ROOT / "scripts" / "restore_mysql.sh"),
            "--backup",
            str(backup),
            "--target-database",
            args.target_database,
            "--confirm",
            args.confirm,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    rto_seconds = round(time.monotonic() - restore_started, 3)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    table_results = [
        _table_evidence(args.source_database, args.target_database, table, password)
        for table in args.table
    ]
    backup_age = max(0.0, started.timestamp() - backup.stat().st_mtime)
    passed = bool(table_results) and all(item["passed"] for item in table_results)
    return {
        "schemaVersion": 1,
        "passed": passed,
        "status": "RESTORE_DRILL_PASS" if passed else "RESTORE_DRILL_FAIL",
        "startedAt": started.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "backup": str(backup),
        "sourceDatabase": args.source_database,
        "targetDatabase": args.target_database,
        "rpoSeconds": round(backup_age, 3),
        "rtoSeconds": rto_seconds,
        "rowCountDiff": sum(abs(int(item["rowCountDiff"])) for item in table_results),
        "checksumMatch": all(item["checksumMatch"] for item in table_results),
        "tables": table_results,
        "restoreOutput": completed.stdout.strip().splitlines()[-5:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a MySQL dump into an isolated database and verify it.")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--source-database", default="lean_market")
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
            "schemaVersion": 1,
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
