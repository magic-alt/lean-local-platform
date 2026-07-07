from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


VERSIONS_DIR = Path(__file__).parent / "versions"


def _description(script: str, revision: str) -> str:
    for line in script.splitlines():
        cleaned = line.strip()
        if cleaned.lower().startswith("-- description:"):
            return cleaned.split(":", 1)[1].strip()
        if cleaned and not cleaned.startswith("--"):
            break
    return revision


def run_migrations(connection: Any, now: Callable[[], str]) -> None:
    connection.executescript(
        """
        create table if not exists schema_migrations (
            revision text primary key,
            description text not null,
            applied_at text not null
        );
        """
    )
    applied = {row["revision"] for row in connection.execute("select revision from schema_migrations").fetchall()}
    for path in sorted(VERSIONS_DIR.glob("*.sql")):
        revision = path.stem
        if revision in applied:
            continue
        script = path.read_text(encoding="utf-8")
        if script.strip():
            connection.executescript(script)
        connection.execute(
            "insert into schema_migrations (revision, description, applied_at) values (?, ?, ?)",
            (revision, _description(script, revision), now()),
        )
