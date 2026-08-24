from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import pytest


pytestmark = pytest.mark.integration_postgres

if os.environ.get("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "Set RUN_POSTGRES_INTEGRATION=1 and use the isolated PostgreSQL test database.",
        allow_module_level=True,
    )


def _assert_isolated_database() -> None:
    parsed = urlparse(os.environ.get("LEAN_DATABASE_URL", ""))
    assert parsed.scheme.startswith("postgresql")
    assert parsed.path.lstrip("/") == "lean_integration"


def test_postgres_baseline_invariants_and_advisory_lock() -> None:
    _assert_isolated_database()
    from app.db import db, init_db, release_advisory_lock, try_advisory_lock
    from app.migrations.runner import verify_migrations
    from app.services.database_invariants import assert_control_plane_schema

    init_db(apply_migrations=True)
    with db() as connection:
        assert all(item["status"] == "applied" for item in verify_migrations(connection))
        assert_control_plane_schema(connection)
        assert try_advisory_lock(connection, "postgres-integration-lock") is True
        with db() as second:
            assert try_advisory_lock(second, "postgres-integration-lock") is False
        release_advisory_lock(connection, "postgres-integration-lock")


def test_postgres_skip_locked_claims_each_row_once() -> None:
    _assert_isolated_database()
    from app.db import db, init_db

    init_db(apply_migrations=True)
    with db() as connection:
        connection.execute(
            "create table if not exists postgres_claim_probe(id text primary key,status text not null)"
        )
        connection.execute("delete from postgres_claim_probe")
        connection.executemany(
            "insert into postgres_claim_probe(id,status) values (?,?)",
            [(f"job-{index}", "queued") for index in range(8)],
        )

    barrier = threading.Barrier(2)

    def claim() -> list[str]:
        barrier.wait(timeout=5)
        with db() as connection:
            rows = connection.execute(
                """
                select id from postgres_claim_probe where status='queued'
                order by id for update skip locked limit 4
                """
            ).fetchall()
            claimed = [str(row["id"]) for row in rows]
            for item in claimed:
                connection.execute(
                    "update postgres_claim_probe set status='claimed' where id=? and status='queued'",
                    (item,),
                )
            return claimed

    with ThreadPoolExecutor(max_workers=2) as executor:
        groups = list(executor.map(lambda _index: claim(), range(2)))
    assert len(set(groups[0]) | set(groups[1])) == 8
    assert set(groups[0]).isdisjoint(groups[1])
