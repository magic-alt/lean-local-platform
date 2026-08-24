#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
LEGACY_DIR = BACKEND / "app" / "migrations" / "versions"
POSTGRES_DIR = BACKEND / "app" / "migrations" / "postgres"
CONTRACT_PATH = ROOT / "config" / "tushare_contracts.v1.json"


EXPLICIT_FORBIDDEN_RELATIONS = {
    "cbond_daily_bars",
    "futures_continuous_bars",
    "futures_daily_bars",
}
TIMESERIES_DATASET_TOKENS = (
    "daily",
    "weekly",
    "monthly",
    "mins",
    "minute",
    "tick",
    "realtime",
    "rt_",
    "adj_factor",
    "daily_basic",
    "moneyflow",
    "suspend",
)


def _sha256(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()


def _legacy_manifest() -> dict[str, object]:
    entries: list[dict[str, str]] = []
    for path in sorted(LEGACY_DIR.glob("*.sql")):
        entries.append(
            {
                "revision": path.stem,
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": _sha256(path.read_bytes()),
            }
        )
    root_material = "\n".join(f"{item['revision']}:{item['sha256']}" for item in entries)
    return {
        "schemaVersion": 1,
        "sourceSchemaVersion": entries[-1]["revision"] if entries else None,
        "legacyMigrationRootSha256": _sha256(root_material),
        "migrations": entries,
    }


def _forbidden_contract_relations() -> set[str]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    forbidden: set[str] = set()
    for contract in payload.get("contracts", []):
        table = str(contract.get("sourceTable") or "").strip()
        dataset = str(contract.get("datasetKey") or "").strip().lower()
        tier = str(contract.get("storageTier") or "").strip().lower()
        if table and (
            tier == "columnar"
            or any(token in dataset for token in TIMESERIES_DATASET_TOKENS)
        ):
            forbidden.add(table)
    return forbidden


def _postgres_ddl(sql: str) -> str:
    translated = sql.strip().replace("`", '"')
    translated = re.sub(
        r"\binteger\s+primary\s+key\s+autoincrement\b",
        "bigserial primary key",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(r"\blongtext\b", "text", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdatetime\s*\(\s*6\s*\)", "text", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bblob\b", "bytea", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\breal\b", "double precision", translated, flags=re.IGNORECASE)
    translated = re.sub(r'(?<![\w"])(rows|key)(?![\w"])', r'"\1"', translated, flags=re.IGNORECASE)
    translated = re.sub(r'\bprimary\s+"key"', "primary key", translated, flags=re.IGNORECASE)
    translated = re.sub(r'\bforeign\s+"key"', "foreign key", translated, flags=re.IGNORECASE)
    translated = re.sub(
        r"^CREATE\s+TABLE\s+",
        "create table if not exists ",
        translated,
        count=1,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"^CREATE\s+(UNIQUE\s+)?INDEX\s+",
        lambda match: f"create {match.group(1) or ''}index if not exists ",
        translated,
        count=1,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"^CREATE\s+VIEW\s+",
        "create or replace view ",
        translated,
        count=1,
        flags=re.IGNORECASE,
    )
    return translated.rstrip(";") + ";"


def _schema_snapshot(path: Path) -> tuple[str, list[str]]:
    os.environ["LEAN_ALLOW_SQLITE_TEST_DB"] = "1"
    os.environ["LEAN_DATABASE_URL"] = f"sqlite:///{path.as_posix()}"
    os.environ["LEAN_RUNTIME_DIR"] = str(path.parent / "runtime")
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.db import init_db

    init_db()
    forbidden = EXPLICIT_FORBIDDEN_RELATIONS | _forbidden_contract_relations()
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            """
            select type,name,tbl_name,sql
            from sqlite_master
            where type in ('table','index','view')
              and name not like 'sqlite_%'
              and sql is not null
            order by case type when 'table' then 0 when 'index' then 1 else 2 end, name
            """
        ).fetchall()
    statements: list[str] = []
    included_tables = {
        str(row[1])
        for row in rows
        if row[0] == "table" and row[1] != "schema_migrations" and row[1] not in forbidden
    }
    table_rows = {
        str(name): str(sql)
        for kind, name, _table, sql in rows
        if kind == "table" and name in included_tables
    }
    ordered_tables: list[str] = []
    remaining = set(table_rows)
    while remaining:
        ready = sorted(
            name
            for name in remaining
            if {
                dependency
                for dependency in re.findall(
                    r"\breferences\s+[`\"]?([A-Za-z0-9_]+)",
                    table_rows[name],
                    flags=re.IGNORECASE,
                )
                if dependency in included_tables and dependency != name
            }.isdisjoint(remaining)
        )
        if not ready:
            raise RuntimeError(
                "postgres_baseline_foreign_key_cycle:" + ",".join(sorted(remaining))
            )
        ordered_tables.extend(ready)
        remaining.difference_update(ready)
    statements.extend(_postgres_ddl(table_rows[name]) for name in ordered_tables)
    for kind, name, table, sql in rows:
        if name == "schema_migrations" or table == "schema_migrations":
            continue
        if kind == "table":
            continue
        if kind == "index" and table not in included_tables:
            continue
        if kind == "view" and name != "index_membership_pit":
            continue
        statements.append(_postgres_ddl(str(sql)))
    header = """-- description: PostgreSQL baseline equivalent to the certified legacy 0056 schema
-- compatibility: fresh PostgreSQL initialization only; no MySQL data migration or legacy replay
-- rollback: restore an isolated pg_dump or recreate the empty database from this baseline
-- data migration: none
-- affected tests: PostgreSQL baseline, schema contract, market time-series relation guard
"""
    return header + "\n" + "\n\n".join(statements) + "\n", sorted(forbidden)


def main() -> int:
    POSTGRES_DIR.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_manifest()
    with tempfile.TemporaryDirectory(prefix="platform-pg-baseline-") as temp_dir:
        baseline, forbidden = _schema_snapshot(Path(temp_dir) / "baseline.sqlite3")
    baseline_path = POSTGRES_DIR / "P0001_postgresql_baseline.sql"
    baseline_path.write_text(baseline, encoding="utf-8", newline="\n")
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    manifest = {
        "schemaVersion": "postgresql-baseline-v1",
        "sourceSchemaVersion": legacy["sourceSchemaVersion"],
        "legacyMigrationRootSha256": legacy["legacyMigrationRootSha256"],
        "platformCommit": commit,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "baselineSha256": _sha256(baseline),
        "forbiddenRelations": forbidden,
    }
    (POSTGRES_DIR / "baseline_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (LEGACY_DIR / "checksums.json").write_text(
        json.dumps(legacy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "baseline": str(baseline_path.relative_to(ROOT)),
                "sha256": manifest["baselineSha256"],
                "forbiddenRelations": len(forbidden),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
