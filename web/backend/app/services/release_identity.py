from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..core.config import FRONTEND_DIST
from ..db import database_backend, db
from ..migrations.runner import POSTGRES_VERSIONS_DIR, migration_files


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def _frontend_digest(root: Path = FRONTEND_DIST) -> str | None:
    if not root.is_dir():
        return None
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": str(path.relative_to(root)), "sha256": digest})
    return _digest(files) if files else None


def _schema_identity() -> dict[str, Any]:
    versions_dir = POSTGRES_VERSIONS_DIR if database_backend() == "postgresql" else None
    source = migration_files(versions_dir) if versions_dir is not None else migration_files()
    latest_source = source[-1]["revision"] if source else None
    source_checksum = source[-1]["checksum"] if source else None
    latest_applied = None
    stored_checksum = None
    aligned = False
    try:
        with db() as connection:
            rows = connection.execute(
                "select revision,checksum from schema_migrations"
            ).fetchall()
        applied = {str(row["revision"]): row["checksum"] for row in rows}
        applied_source = [item for item in source if item["revision"] in applied]
        if applied_source:
            latest = applied_source[-1]
            latest_applied = latest["revision"]
            stored_checksum = applied[latest_applied]
        aligned = bool(
            source
            and len(applied_source) == len(source)
            and all(
                not applied[item["revision"]]
                or applied[item["revision"]] == item["checksum"]
                for item in source
            )
        )
    except Exception:
        pass
    return {
        "latestSourceMigration": latest_source,
        "latestAppliedMigration": latest_applied,
        "latestSourceMigrationChecksum": source_checksum,
        "latestAppliedMigrationChecksum": stored_checksum,
        "aligned": aligned,
    }


def runtime_release_identity(openapi: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = _schema_identity()
    openapi_hash = _digest(openapi) if openapi is not None else None
    openapi_paths = len(openapi.get("paths") or {}) if openapi is not None else None
    release_sha = os.environ.get("LEAN_RELEASE_SHA", "unknown").strip() or "unknown"
    release_id = os.environ.get("LEAN_RELEASE_ID", "local-unversioned").strip() or "local-unversioned"
    return {
        "releaseId": release_id,
        "gitSha": release_sha,
        "processRole": os.environ.get("LEAN_RELEASE_ROLE", "api").strip() or "api",
        "schema": schema,
        "openApiSha256": openapi_hash,
        "openApiPathCount": openapi_paths,
        "frontendAssetsSha256": _frontend_digest(),
        "aligned": bool(schema["aligned"] and release_sha != "unknown" and release_id != "local-unversioned"),
    }
