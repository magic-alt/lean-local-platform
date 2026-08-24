#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target(value: str) -> str:
    if not re.fullmatch(r"lean_restore_[a-z0-9_]+", value):
        raise RuntimeError("restore_target_must_use_lean_restore_prefix")
    return value


def _binary(name: str) -> str:
    configured = os.environ.get("LEAN_POSTGRES_BIN", "").strip()
    executable = f"{name}.exe" if os.name == "nt" else name
    if configured and (Path(configured) / executable).is_file():
        return str(Path(configured) / executable)
    resolved = shutil.which(executable) or shutil.which(name)
    if not resolved:
        raise RuntimeError(f"postgres_{name}_client_unavailable")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore a PostgreSQL backup into isolated databases.")
    parser.add_argument("backup_dir", type=Path)
    parser.add_argument("--target-prefix", default="lean_restore_v2")
    args = parser.parse_args()
    backup_dir = args.backup_dir.resolve()
    if not (backup_dir / "COMPLETE").is_file():
        raise RuntimeError("postgres_restore_requires_complete_backup")
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise RuntimeError("postgres_restore_manifest_incomplete")

    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise RuntimeError("psycopg_required_in_backend_environment") from exc
    admin_url = os.environ.get("LEAN_POSTGRES_ADMIN_URL", "").strip()
    parsed = urlsplit(admin_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RuntimeError("LEAN_POSTGRES_ADMIN_URL_invalid")
    admin_database = (parsed.path or "/postgres").strip("/") or "postgres"
    connection_options = {
        "host": parsed.hostname,
        "port": int(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
    }
    admin = psycopg.connect(dbname=admin_database, autocommit=True, **connection_options)
    restored: list[dict[str, str]] = []
    try:
        for record in manifest.get("databases", []):
            source = backup_dir / str(record["file"])
            if not source.is_file() or _sha256(source) != str(record["sha256"]):
                raise RuntimeError(f"postgres_restore_checksum_mismatch:{source.name}")
            target = _target(f"{args.target_prefix}_{record['label']}")
            with admin.cursor() as cursor:
                cursor.execute("select 1 from pg_database where datname=%s", (target,))
                if cursor.fetchone():
                    raise RuntimeError(f"postgres_restore_target_exists:{target}")
                cursor.execute(sql.SQL("create database {}").format(sql.Identifier(target)))
            environment = dict(os.environ)
            environment["PGPASSWORD"] = str(connection_options["password"])
            completed = subprocess.run(
                [
                    _binary("pg_restore"),
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    f"--host={connection_options['host']}",
                    f"--port={connection_options['port']}",
                    f"--username={connection_options['user']}",
                    f"--dbname={target}",
                    str(source),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
            if completed.returncode != 0:
                error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
                raise RuntimeError(f"postgres_restore_failed:{target}:{completed.returncode}:{error}")
            restored.append({"label": str(record["label"]), "database": target})
    finally:
        admin.close()

    platform_target = next(
        (item["database"] for item in restored if item["label"] == "platform"), None
    )
    if platform_target:
        verification = psycopg.connect(dbname=platform_target, **connection_options)
        try:
            required = {
                "schema_migrations",
                "data_releases",
                "paper_ledger_entries",
                "paper_run_checkpoints",
                "stored_objects",
                "restricted_runner_jobs",
            }
            with verification.cursor() as cursor:
                cursor.execute(
                    "select table_name from information_schema.tables where table_schema='public'"
                )
                present = {str(row[0]) for row in cursor.fetchall()}
            missing = sorted(required - present)
            if missing:
                raise RuntimeError("postgres_restore_verification_missing:" + ",".join(missing))
        finally:
            verification.close()
    print(json.dumps({"status": "verified", "restored": restored}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
