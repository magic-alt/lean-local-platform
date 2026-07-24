from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest


pytestmark = pytest.mark.integration_mysql

if os.environ.get("RUN_MYSQL_INTEGRATION") != "1":
    pytest.skip(
        "Set RUN_MYSQL_INTEGRATION=1 and use the isolated MySQL test database.",
        allow_module_level=True,
    )


def _assert_isolated_database() -> None:
    parsed = urlparse(os.environ.get("LEAN_DATABASE_URL", ""))
    database = parsed.path.lstrip("/")
    assert parsed.scheme.startswith("mysql")
    assert database == "lean_integration", (
        "The MySQL integration lane refuses any database other than "
        "lean_integration."
    )


def test_mysql_migrations_schema_indexes_and_unique_transaction() -> None:
    _assert_isolated_database()

    from app.db import db, init_db
    from app.migrations.runner import verify_migrations

    init_db()
    with db() as connection:
        verification = verify_migrations(connection)
    assert len(verification) >= 21
    assert all(item["status"] == "applied" for item in verification)

    with db() as connection:
        backend = connection.execute("select database() as name").fetchone()
        assert backend["name"] == "lean_integration"
        index_rows = connection.execute(
            """
            select index_name
            from information_schema.statistics
            where table_schema = database()
              and table_name = 'paper_walkforward_runs'
            """
        ).fetchall()
        assert {"PRIMARY", "idx_paper_walkforward_session_date"} <= {
            str(next(iter(row.values()))) for row in index_rows
        }
        connection.execute(
            """
            create table if not exists mysql_integration_unique_probe (
                id varchar(64) primary key,
                idempotency_key varchar(128) not null unique
            )
            """
        )
        connection.execute("delete from mysql_integration_unique_probe")
        connection.execute(
            "insert into mysql_integration_unique_probe (id,idempotency_key) values (?,?)",
            ("one", "same-request"),
        )

    with pytest.raises(Exception):
        with db() as connection:
            connection.execute(
                "insert into mysql_integration_unique_probe (id,idempotency_key) values (?,?)",
                ("two", "same-request"),
            )

    with db() as connection:
        count = connection.execute(
            "select count(*) as count from mysql_integration_unique_probe"
        ).fetchone()
        assert count["count"] == 1


def test_mysql_named_lock_excludes_concurrent_holder() -> None:
    _assert_isolated_database()

    from app.db import db

    with db() as first:
        acquired = first.execute(
            "select get_lock(?, 0) as acquired",
            ("lean-integration-lock",),
        ).fetchone()
        assert acquired["acquired"] == 1
        with db() as second:
            blocked = second.execute(
                "select get_lock(?, 0) as acquired",
                ("lean-integration-lock",),
            ).fetchone()
            assert blocked["acquired"] == 0
        released = first.execute(
            "select release_lock(?) as released",
            ("lean-integration-lock",),
        ).fetchone()
        assert released["released"] == 1
