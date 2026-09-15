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
import tempfile
import time
from typing import Any
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLES = (
    "schema_migrations",
    "paper_accounts",
    "paper_ledger_entries",
    "paper_account_checkpoints",
    "stored_objects",
)
HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        raise RuntimeError(completed.stderr.strip() or "unable_to_resolve_git_sha")
    return completed.stdout.strip()


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


def _database_url(options: dict[str, Any]) -> str:
    user = quote(str(options["user"]), safe="")
    password = quote(str(options["password"]), safe="")
    auth = user if not password else f"{user}:{password}"
    return (
        f"postgresql://{auth}@{options['host']}:{int(options['port'])}/"
        f"{quote(str(options['dbname']), safe='')}"
    )


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


def _projection_rebuild(target_url: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lean-restore-projection-") as directory:
        evidence = Path(directory) / "paper-projection-recompute.json"
        env = dict(os.environ)
        env["LEAN_DATABASE_URL"] = target_url
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "recompute_paper_projections.py"),
                "--apply",
                "--evidence",
                str(evidence),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        payload: dict[str, Any]
        if evidence.is_file():
            loaded = json.loads(evidence.read_text(encoding="utf-8"))
            payload = loaded if isinstance(loaded, dict) else {}
        else:
            payload = {}
        payload["exitCode"] = completed.returncode
        payload["stdoutTail"] = completed.stdout.strip().splitlines()[-8:]
        if completed.stderr.strip():
            payload["stderrTail"] = completed.stderr.strip().splitlines()[-8:]
        payload["passed"] = bool(payload.get("passed")) and completed.returncode == 0
        return payload


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirm != "RESTORE_ISOLATED_DATABASE":
        raise ValueError("explicit_restore_confirmation_required")
    if not re.fullmatch(r"lean_restore_[a-z0-9_]+", args.target_prefix):
        raise ValueError("unsafe_restore_target_prefix")
    if args.data_release_manifest_sha256 and not HEX_64_RE.fullmatch(
        args.data_release_manifest_sha256
    ):
        raise ValueError("data_release_manifest_sha256_invalid")

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
    target_options = _connection_options(
        os.environ.get("LEAN_POSTGRES_ADMIN_URL", source_url),
        database=f"{args.target_prefix}_platform",
    )
    source = psycopg.connect(**_connection_options(source_url))
    target = psycopg.connect(**target_options)
    try:
        table_results = [_table_evidence(source, target, table) for table in args.table]
    finally:
        source.close()
        target.close()

    projection_rebuild: dict[str, Any] = {
        "requested": bool(args.verify_paper_projections),
        "mode": "not_requested",
        "passed": False,
    }
    if args.verify_paper_projections:
        projection_rebuild = _projection_rebuild(_database_url(target_options))
        projection_rebuild["requested"] = True

    backup_age = max(0.0, started.timestamp() - backup.stat().st_mtime)
    table_checks_passed = bool(table_results) and all(item["passed"] for item in table_results)
    passed = table_checks_passed and (
        not args.verify_paper_projections or bool(projection_rebuild.get("passed"))
    )
    return {
        "schemaVersion": 3,
        "databaseEngine": "postgresql",
        "passed": passed,
        "status": "RESTORE_DRILL_PASS" if passed else "RESTORE_DRILL_FAIL",
        "startedAt": started.isoformat(),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "gitSha": _git_sha(),
        "releaseId": os.environ.get("LEAN_RELEASE_ID", "").strip() or None,
        "deploymentProfile": os.environ.get("LEAN_DEPLOYMENT_PROFILE", "").strip() or None,
        "dataReleaseId": args.data_release_id,
        "dataReleaseManifestSha256": args.data_release_manifest_sha256,
        "backup": str(backup),
        "sourceDatabase": _connection_options(source_url)["dbname"],
        "targetDatabase": f"{args.target_prefix}_platform",
        "rpoSeconds": round(backup_age, 3),
        "rtoSeconds": rto_seconds,
        "rowCountDiff": sum(abs(int(item["rowCountDiff"])) for item in table_results),
        "checksumMatch": all(item["checksumMatch"] for item in table_results),
        "tables": table_results,
        "projectionRebuild": projection_rebuild,
        "restoreOutput": completed.stdout.strip().splitlines()[-5:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Restore PostgreSQL backups into isolated databases, verify canonical row digests, "
            "and optionally rebuild Paper projections inside the isolated target."
        )
    )
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--target-prefix", default="lean_restore_drill")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--table", action="append", default=list(DEFAULT_TABLES))
    parser.add_argument("--data-release-id")
    parser.add_argument("--data-release-manifest-sha256")
    parser.add_argument(
        "--verify-paper-projections",
        action="store_true",
        help="Rebuild and verify Paper projections in the isolated restored database.",
    )
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
            "schemaVersion": 3,
            "databaseEngine": "postgresql",
            "passed": False,
            "status": "RESTORE_DRILL_FAIL",
            "completedAt": datetime.now(timezone.utc).isoformat(),
            "gitSha": None,
            "releaseId": os.environ.get("LEAN_RELEASE_ID", "").strip() or None,
            "dataReleaseId": args.data_release_id,
            "dataReleaseManifestSha256": args.data_release_manifest_sha256,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
        exit_code = 1
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(payload["status"])
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
