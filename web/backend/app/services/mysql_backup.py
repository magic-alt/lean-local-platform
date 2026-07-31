from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.parse import unquote, urlsplit

from ..core.config import REPO_ROOT


def _database_connection() -> dict[str, Any]:
    url = os.environ.get(
        "LEAN_DATABASE_URL",
        "mysql+pymysql://lean:lean@mysql:3306/lean_market",
    )
    parsed = urlsplit(url.replace("mysql+pymysql://", "mysql://", 1))
    if parsed.scheme != "mysql" or not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError("mysql_backup_requires_mysql_database_url")
    return {
        "host": parsed.hostname,
        "port": int(parsed.port or 3306),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "database": parsed.path.strip("/"),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prune_backups(output_dir: Path, *, keep_days: int, keep_files: int) -> list[str]:
    dumps = sorted(
        output_dir.glob("lean_market-*.sql"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, keep_days))
    removed: list[str] = []
    for index, dump in enumerate(dumps):
        modified = datetime.fromtimestamp(dump.stat().st_mtime, timezone.utc)
        if index < max(1, keep_files) and modified >= cutoff:
            continue
        checksum = dump.with_suffix(dump.suffix + ".sha256")
        dump.unlink(missing_ok=True)
        checksum.unlink(missing_ok=True)
        removed.append(dump.name)
    return removed


def create_backup(output_dir: Path | None = None) -> dict[str, Any]:
    connection = _database_connection()
    additional_databases = [
        value.strip() for value in os.environ.get("LEAN_MYSQL_ADDITIONAL_BACKUP_DATABASES", "").split(",")
        if value.strip() and value.strip() != connection["database"]
    ]
    databases = [str(connection["database"]), *additional_databases]
    binary = shutil.which("mysqldump") or shutil.which("mariadb-dump")
    if not binary:
        raise RuntimeError("mysql_dump_client_unavailable")
    destination = Path(
        output_dir
        or os.environ.get(
            "LEAN_MYSQL_BACKUP_DIR",
            str(REPO_ROOT / "web" / "runtime" / "backups"),
        )
    ).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = destination / f"lean_market-{stamp}.sql"
    partial = backup.with_suffix(".sql.partial")
    started = datetime.now(timezone.utc)
    command = [
        binary,
        f"--host={connection['host']}",
        f"--port={connection['port']}",
        f"--user={connection['user']}",
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--no-tablespaces",
        "--databases",
        *databases,
    ]
    environment = dict(os.environ)
    environment["MYSQL_PWD"] = str(connection["password"])
    try:
        with partial.open("wb") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
        if completed.returncode != 0 or not partial.exists() or partial.stat().st_size <= 0:
            error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"mysql_backup_failed:{completed.returncode}:{error}")
        partial.replace(backup)
    finally:
        partial.unlink(missing_ok=True)
    digest = _sha256(backup)
    checksum = backup.with_suffix(".sql.sha256")
    checksum.write_text(f"{digest}  {backup}\n", encoding="utf-8")
    backup.chmod(0o600)
    checksum.chmod(0o600)
    removed = _prune_backups(
        destination,
        keep_days=int(os.environ.get("LEAN_MYSQL_BACKUP_RETENTION_DAYS", "7")),
        keep_files=int(os.environ.get("LEAN_MYSQL_BACKUP_MAX_FILES", "14")),
    )
    completed_at = datetime.now(timezone.utc)
    return {
        "status": "success",
        "backup": str(backup),
        "checksum": str(checksum),
        "sha256": digest,
        "bytes": backup.stat().st_size,
        "startedAt": started.isoformat(),
        "completedAt": completed_at.isoformat(),
        "durationSeconds": round((completed_at - started).total_seconds(), 3),
        "pruned": removed,
        "databases": databases,
    }
