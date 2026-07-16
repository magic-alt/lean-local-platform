import sqlite3


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
    with sqlite3.connect(db_path) as connection:
        paper_columns = {row[1] for row in connection.execute("pragma table_info(paper_sessions)").fetchall()}
        walkforward_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'paper_walkforward_runs'"
        ).fetchone()
    assert {"mode", "source_backtest_id", "last_processed_date"} <= paper_columns
    assert walkforward_table is not None
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
