import sqlite3

import pytest


def test_init_db_adds_data_assets_status_before_status_index(tmp_path, monkeypatch):
    import app.db as db_module

    db_path = tmp_path / "legacy.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            create table data_assets (
                id integer primary key autoincrement,
                symbol text not null,
                source text not null,
                rows integer not null,
                first_date text not null,
                last_date text not null,
                lean_file text not null,
                metadata_json text not null,
                created_at text not null
            )
            """
        )

    db_module.init_db()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("pragma table_info(data_assets)").fetchall()}
        index_row = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_data_assets_status_created'"
        ).fetchone()
    assert "status" in columns
    assert index_row is not None


def test_init_db_records_file_migrations(tmp_path, monkeypatch):
    import app.db as db_module

    db_path = tmp_path / "migrations.sqlite3"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")

    db_module.init_db()

    with sqlite3.connect(db_path) as connection:
        revisions = {
            row[0]
            for row in connection.execute("select revision from schema_migrations").fetchall()
        }
        index_row = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_backtest_runs_task_created'"
        ).fetchone()
    assert "0001_backtest_child_run_indexes" in revisions
    assert "0010_lean_paper_walkforward" in revisions
    assert "0022_paper_order_pipeline_v2" in revisions
    assert "0029_paper_accounts" in revisions
    with sqlite3.connect(db_path) as connection:
        paper_columns = {row[1] for row in connection.execute("pragma table_info(paper_sessions)").fetchall()}
        walkforward_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'paper_walkforward_runs'"
        ).fetchone()
        intent_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'paper_order_intents'"
        ).fetchone()
        account_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'paper_accounts'"
        ).fetchone()
    assert {"mode", "source_backtest_id", "last_processed_date", "pipeline_version"} <= paper_columns
    assert walkforward_table is not None
    assert intent_table is not None
    assert account_table is not None
    assert index_row is not None


def test_mysql_index_parser_handles_leading_migration_comment():
    import app.db as db_module

    statement = """
    -- description: Add indexes for optimization child backtest runs
    create index if not exists idx_backtest_runs_task_created
        on backtest_runs(task_id, created_at desc)
    """

    cleaned = db_module._strip_leading_sql_comments(statement)

    assert cleaned.startswith("create index if not exists")
    assert db_module._parse_create_index_if_not_exists(cleaned) == (
        "idx_backtest_runs_task_created",
        "backtest_runs",
    )


def test_mysql_connect_retries_transient_handshake_failures(monkeypatch):
    import app.db as db_module

    sentinel = object()
    calls = []
    delays = []

    def connect(database_url=None):
        calls.append(database_url)
        if len(calls) < 3:
            raise RuntimeError(2013, "Lost connection during handshake")
        return sentinel

    monkeypatch.setenv("LEAN_MYSQL_CONNECT_ATTEMPTS", "4")
    monkeypatch.setenv("LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS", "0.1")
    monkeypatch.setattr(db_module, "MySQLConnection", connect)
    monkeypatch.setattr(db_module.time, "sleep", delays.append)

    assert db_module._connect_mysql("mysql+pymysql://example") is sentinel
    assert calls == ["mysql+pymysql://example"] * 3
    assert delays == [0.1, 0.2]


def test_mysql_connect_raises_retryable_domain_error_after_exhaustion(monkeypatch):
    import app.db as db_module

    def connect(database_url=None):
        raise RuntimeError(2003, "Connection refused")

    monkeypatch.setenv("LEAN_MYSQL_CONNECT_ATTEMPTS", "2")
    monkeypatch.setenv("LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(db_module, "MySQLConnection", connect)

    with pytest.raises(db_module.DatabaseUnavailableError) as error:
        db_module._connect_mysql()

    assert "2 connection attempts" in str(error.value)
    assert error.value.__cause__.args[0] == 2003


def test_mysql_connect_does_not_retry_configuration_errors(monkeypatch):
    import app.db as db_module

    calls = 0

    def connect(database_url=None):
        nonlocal calls
        calls += 1
        raise RuntimeError(1045, "Access denied")

    monkeypatch.setenv("LEAN_MYSQL_CONNECT_ATTEMPTS", "5")
    monkeypatch.setattr(db_module, "MySQLConnection", connect)

    with pytest.raises(RuntimeError, match="Access denied"):
        db_module._connect_mysql()

    assert calls == 1
