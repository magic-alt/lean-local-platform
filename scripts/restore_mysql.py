#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mysql_command(*, database: str | None = None, execute: str | None = None) -> tuple[list[str], dict[str, str]]:
    binary = shutil.which("mysql") or shutil.which("mariadb")
    if not binary:
        raise RuntimeError("mysql_client_unavailable")
    password = os.environ.get("LEAN_MYSQL_ROOT_PASSWORD", "")
    if not password:
        raise RuntimeError("LEAN_MYSQL_ROOT_PASSWORD_required")
    command = [
        binary,
        f"--host={os.environ.get('LEAN_MYSQL_HOST', '127.0.0.1')}",
        f"--port={int(os.environ.get('LEAN_MYSQL_PORT', '3306'))}",
        f"--user={os.environ.get('LEAN_MYSQL_ADMIN_USER', 'root')}",
        "--batch",
        "--skip-column-names",
    ]
    if database:
        command.append(database)
    if execute:
        command.extend(["--execute", execute])
    environment = dict(os.environ)
    environment["MYSQL_PWD"] = password
    return command, environment


def _query(sql: str, *, database: str | None = None) -> str:
    command, environment = _mysql_command(database=database, execute=sql)
    completed = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError("mysql_restore_query_failed")
    return completed.stdout.strip()


def _verified_backup(path: Path) -> None:
    checksum_path = Path(str(path) + ".sha256")
    if not path.is_file() or not checksum_path.is_file():
        raise RuntimeError("backup_or_checksum_missing")
    expected = checksum_path.read_text(encoding="utf-8").split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or _sha256(path) != expected:
        raise RuntimeError("backup_checksum_mismatch")


def _restore_stream(backup: Path, source: str, target: str) -> None:
    command, environment = _mysql_command()
    process = subprocess.Popen(command, env=environment, stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stdin is not None
    active = True
    seen_source = False
    create_pattern = re.compile(r"^CREATE DATABASE .*?`([A-Za-z0-9_]+)`", re.IGNORECASE)
    use_pattern = re.compile(r"^USE `([A-Za-z0-9_]+)`;", re.IGNORECASE)
    try:
        with backup.open("r", encoding="utf-8", errors="strict") as source_file:
            for line in source_file:
                create = create_pattern.match(line)
                if create:
                    database = create.group(1)
                    if database == source:
                        process.stdin.write(line.replace(f"`{source}`", f"`{target}`"))
                    continue
                use = use_pattern.match(line)
                if use:
                    active = use.group(1) == source
                    if active:
                        seen_source = True
                        process.stdin.write(f"USE `{target}`;\n")
                    continue
                if active:
                    process.stdin.write(line)
        if not seen_source:
            raise RuntimeError("source_database_not_found_in_backup")
    finally:
        process.stdin.close()
    stderr = process.stderr.read() if process.stderr is not None else ""
    code = process.wait()
    if code:
        raise RuntimeError(f"mysql_restore_failed:{code}:{stderr[-500:]}")


def restore(backup: Path, source: str, target: str, tables: list[str]) -> dict[str, object]:
    if not SAFE_NAME.fullmatch(source) or not re.fullmatch(r"lean_restore_[A-Za-z0-9_]+", target):
        raise RuntimeError("unsafe_restore_database_name")
    _verified_backup(backup)
    existing = int(_query(f"select count(*) from information_schema.schemata where schema_name='{target}'") or 0)
    if existing:
        raise RuntimeError("restore_target_already_exists")
    _query(f"create database `{target}` character set utf8mb4 collate utf8mb4_0900_ai_ci")
    _restore_stream(backup, source, target)
    evidence = []
    for table in tables:
        if not SAFE_NAME.fullmatch(table):
            raise RuntimeError("unsafe_verification_table")
        source_rows = int(_query(f"select count(*) from `{source}`.`{table}`") or 0)
        target_rows = int(_query(f"select count(*) from `{target}`.`{table}`") or 0)
        source_checksum = _query(f"checksum table `{source}`.`{table}`").split("\t")[-1]
        target_checksum = _query(f"checksum table `{target}`.`{table}`").split("\t")[-1]
        evidence.append(
            {
                "table": table,
                "sourceRows": source_rows,
                "targetRows": target_rows,
                "checksumMatch": bool(source_checksum and source_checksum == target_checksum),
                "passed": source_rows == target_rows and bool(source_checksum) and source_checksum == target_checksum,
            }
        )
    return {"status": "restored_verified" if all(item["passed"] for item in evidence) else "verification_failed", "targetDatabase": target, "tables": evidence}


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a MySQL backup over TCP into an isolated database.")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--source-database", default="lean_market")
    parser.add_argument("--target-database", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--verify-table", action="append", default=["schema_migrations", "paper_accounts", "paper_ledger_entries", "stored_objects"])
    args = parser.parse_args()
    if args.confirm != "RESTORE_ISOLATED_DATABASE":
        print("failed: explicit_restore_confirmation_required", file=sys.stderr)
        return 2
    try:
        result = restore(args.backup.resolve(), args.source_database, args.target_database, args.verify_table)
    except Exception as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 2
    print(result["status"])
    for item in result["tables"]:
        print(f"{item['table']}: passed={item['passed']}")
    return 0 if result["status"] == "restored_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
