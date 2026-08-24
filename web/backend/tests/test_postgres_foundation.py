from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_postgres_backend_and_descriptor(monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(
        db_module,
        "DATABASE_URL",
        "postgresql+psycopg://lean_app:secret@db.internal:5544/lean_platform",
    )
    assert db_module.database_backend() == "postgresql"
    assert db_module.database_descriptor() == {
        "engine": "postgresql",
        "host": "db.internal",
        "port": 5544,
        "database": "lean_platform",
        "user": "lean_app",
    }


def test_postgres_sql_translation_preserves_portable_contract():
    from app.db import _translate_postgres_sql

    translated = _translate_postgres_sql(
        """
        insert into sample(id, rows, metadata_json)
        values (?, ?, ?)
        on conflict(id) do update set rows=excluded.rows
        """
    )
    assert "values (%s, %s, %s)" in translated
    assert '"rows"' in translated
    assert "on conflict(id) do update" in translated
    assert "excluded." in translated


def test_postgres_baseline_is_bound_and_excludes_market_timeseries():
    root = Path(__file__).parents[3]
    migration_root = root / "web" / "backend" / "app" / "migrations"
    manifest = json.loads(
        (migration_root / "postgres" / "baseline_manifest.json").read_text(encoding="utf-8")
    )
    baseline = (migration_root / "postgres" / "P0001_postgresql_baseline.sql").read_text(
        encoding="utf-8"
    )
    assert manifest["sourceSchemaVersion"] == "0056_runtime_neutral_execution"
    assert hashlib.sha256(baseline.encode("utf-8")).hexdigest() == manifest["baselineSha256"]
    assert "create table if not exists data_releases" in baseline.lower()
    assert "create table if not exists paper_ledger_entries" in baseline.lower()
    for relation in manifest["forbiddenRelations"]:
        assert f"create table if not exists {relation.lower()} " not in baseline.lower()


def test_legacy_migration_manifest_is_complete_and_immutable():
    versions = Path(__file__).parents[1] / "app" / "migrations" / "versions"
    manifest = json.loads((versions / "checksums.json").read_text(encoding="utf-8"))
    sql_files = sorted(versions.glob("*.sql"))
    assert manifest["sourceSchemaVersion"] == sql_files[-1].stem
    assert len(manifest["migrations"]) == len(sql_files)
    for entry, path in zip(manifest["migrations"], sql_files, strict=True):
        assert entry["revision"] == path.stem
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_postgres_backup_is_atomic_and_excludes_celery(tmp_path, monkeypatch):
    from app.services import postgres_backup

    monkeypatch.setattr(
        postgres_backup,
        "DATABASE_URL",
        "postgresql://lean_app:secret@127.0.0.1:5432/lean_platform",
    )
    monkeypatch.setattr(
        postgres_backup,
        "MLFLOW_DATABASE_URL",
        "postgresql+psycopg://lean_mlflow:secret@127.0.0.1:5432/lean_mlflow",
    )
    monkeypatch.setattr(postgres_backup, "_binary", lambda _name: "pg_dump")

    class Completed:
        returncode = 0
        stderr = b""

    def fake_run(command, **_kwargs):
        destination = Path(next(item.split("=", 1)[1] for item in command if item.startswith("--file=")))
        destination.write_bytes(b"PGDMP\x00unit-test")
        return Completed()

    monkeypatch.setattr(postgres_backup.subprocess, "run", fake_run)
    result = postgres_backup.create_backup(tmp_path)
    backup = Path(result["backup"])
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert (backup / "COMPLETE").is_file()
    assert {item["database"] for item in manifest["databases"]} == {
        "lean_platform",
        "lean_mlflow",
    }
    assert manifest["excluded"] == ["lean_celery"]
    assert not list(tmp_path.glob("*.partial"))
