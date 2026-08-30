from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.parse import unquote, urlsplit

from ..core.config import (
    DATABASE_URL,
    MLFLOW_DATABASE_URL,
    POSTGRES_BACKUP_DIR,
    POSTGRES_BACKUP_MAX_FILES,
    POSTGRES_BACKUP_RETENTION_DAYS,
    POSTGRES_BIN,
)


def _connection(url: str, label: str) -> dict[str, Any]:
    normalized = url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise RuntimeError(f"postgres_backup_invalid_{label}_database_url")
    return {
        "label": label,
        "host": parsed.hostname,
        "port": int(parsed.port or 5432),
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


def _binary(name: str) -> str:
    executable = f"{name}.exe" if os.name == "nt" else name
    if POSTGRES_BIN:
        candidate = POSTGRES_BIN / executable
        if candidate.is_file():
            return str(candidate)
    resolved = shutil.which(executable) or shutil.which(name)
    if not resolved:
        raise RuntimeError(f"postgres_{name}_client_unavailable")
    return resolved


def _prune(root: Path) -> list[str]:
    completed = sorted(
        (path for path in root.glob("postgres-*") if path.is_dir() and (path / "COMPLETE").is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=POSTGRES_BACKUP_RETENTION_DAYS)
    removed: list[str] = []
    for index, path in enumerate(completed):
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if index < POSTGRES_BACKUP_MAX_FILES and modified >= cutoff:
            continue
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def create_backup(output_dir: Path | None = None) -> dict[str, Any]:
    pg_dump = _binary("pg_dump")
    root = Path(output_dir or POSTGRES_BACKUP_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    partial_dir = root / f".postgres-{stamp}.partial"
    final_dir = root / f"postgres-{stamp}"
    if partial_dir.exists() or final_dir.exists():
        raise RuntimeError("postgres_backup_destination_exists")
    partial_dir.mkdir(mode=0o700)
    started = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    try:
        for item in (
            _connection(DATABASE_URL, "platform"),
            _connection(MLFLOW_DATABASE_URL, "mlflow"),
        ):
            destination = partial_dir / f"{item['database']}.dump"
            command = [
                pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                f"--host={item['host']}",
                f"--port={item['port']}",
                f"--username={item['user']}",
                f"--file={destination}",
                item["database"],
            ]
            environment = dict(os.environ)
            environment["PGPASSWORD"] = str(item["password"])
            completed = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
            if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size <= 0:
                error = completed.stderr.decode("utf-8", errors="replace")[-2000:]
                raise RuntimeError(
                    f"postgres_backup_failed:{item['label']}:{completed.returncode}:{error}"
                )
            digest = _sha256(destination)
            (partial_dir / f"{destination.name}.sha256").write_text(
                f"{digest}  {destination.name}\n", encoding="utf-8"
            )
            records.append(
                {
                    "label": item["label"],
                    "database": item["database"],
                    "file": destination.name,
                    "bytes": destination.stat().st_size,
                    "sha256": digest,
                }
            )
        completed_at = datetime.now(timezone.utc)
        manifest = {
            "schemaVersion": 1,
            "status": "complete",
            "startedAt": started.isoformat(),
            "completedAt": completed_at.isoformat(),
            "databases": records,
            "excluded": ["lean_celery"],
        }
        (partial_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (partial_dir / "COMPLETE").write_text("complete\n", encoding="utf-8")
        partial_dir.replace(final_dir)
    except Exception:
        shutil.rmtree(partial_dir, ignore_errors=True)
        raise
    removed = _prune(root)
    return {
        "status": "success",
        "backup": str(final_dir),
        "manifest": str(final_dir / "manifest.json"),
        "startedAt": started.isoformat(),
        "completedAt": completed_at.isoformat(),
        "durationSeconds": round((completed_at - started).total_seconds(), 3),
        "databases": records,
        "pruned": removed,
    }
