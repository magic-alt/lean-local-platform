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
    assert "0033_retire_legacy_paper_sessions" in revisions
    assert "0039_p0_lineage_and_run_convergence" in revisions
    assert "0041_p0_terminal_trust_and_release_identity" in revisions
    assert "0042_p1_notification_capacity_controls" in revisions
    assert "0043_p1_lineage_query_index" in revisions
    assert "0050_daily_reconciliation_indexes" in revisions
    assert "0051_market_lake_authority" in revisions
    assert "0052_reconcile_market_lake_control_plane" in revisions
    assert "0053_reconcile_instrument_identifier_columns" in revisions
    assert "0055_qlib_lean_promotion_gates" in revisions
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
        certification_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'paper_certification_cohorts'"
        ).fetchone()
        backtest_columns = {
            row[1] for row in connection.execute("pragma table_info(backtest_runs)").fetchall()
        }
        walk_forward_columns = {
            row[1] for row in connection.execute("pragma table_info(walk_forward_runs)").fetchall()
        }
        delivery_columns = {
            row[1] for row in connection.execute("pragma table_info(alert_deliveries)").fetchall()
        }
        identifier_columns = {
            row[1] for row in connection.execute("pragma table_info(instrument_identifiers)").fetchall()
        }
        financial_columns = {
            row[1] for row in connection.execute("pragma table_info(financial_statements)").fetchall()
        }
        outbox_columns = {
            row[1]
            for row in connection.execute("pragma table_info(paper_notification_outbox)").fetchall()
        }
        qlib_validation_table = connection.execute(
            "select name from sqlite_master where type = 'table' and name = 'qlib_lean_validations'"
        ).fetchone()
        lineage_index = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_market_daily_lineage'"
        ).fetchone()
        daily_reconcile_index = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_market_daily_source_date_symbol'"
        ).fetchone()
        status_reconcile_index = connection.execute(
            "select name from sqlite_master where type = 'index' and name = 'idx_market_status_source_date_symbol'"
        ).fetchone()
    assert {"mode", "source_backtest_id", "last_processed_date", "pipeline_version"} <= paper_columns
    assert walkforward_table is not None
    assert intent_table is not None
    assert account_table is not None
    assert certification_table is not None
    assert {"trust_status", "trust_reason", "trust_evaluated_at"} <= backtest_columns
    assert {"certificate_json", "certificate_digest", "certified_at"} <= walk_forward_columns
    assert "terminal_at" in delivery_columns
    assert "terminal_at" in outbox_columns
    assert {"provider", "identifier_type", "identifier_value", "valid_from", "valid_to"} <= identifier_columns
    assert {"report_type", "update_flag", "payload_hash"} <= financial_columns
    assert qlib_validation_table is not None
    assert lineage_index is None
    assert daily_reconcile_index is None
    assert status_reconcile_index is None
    assert index_row is not None


def test_script_splitter_ignores_semicolons_in_leading_comments():
    import app.db as db_module

    script = """
    -- description: Add tables
    -- compatibility: additive schema; legacy rows remain readable
    alter table reports add column agent_run_id text;
    create table if not exists agent_runs (id text primary key);
    """

    statements = [
        db_module._strip_leading_sql_comments(statement)
        for statement in db_module._split_sql_script(script)
    ]

    assert statements == [
        "alter table reports add column agent_run_id text",
        "create table if not exists agent_runs (id text primary key)",
    ]


def test_postgres_connect_retries_transient_handshake_failures(monkeypatch):
    import app.db as db_module

    sentinel = object()
    calls = []
    delays = []

    def connect(database_url=None):
        calls.append(database_url)
        if len(calls) < 3:
            error = RuntimeError("connection reset during handshake")
            error.sqlstate = "08006"
            raise error
        return sentinel

    monkeypatch.setenv("LEAN_POSTGRES_CONNECT_ATTEMPTS", "4")
    monkeypatch.setenv("LEAN_POSTGRES_CONNECT_RETRY_DELAY_SECONDS", "0.1")
    monkeypatch.setattr(db_module, "PostgresConnection", connect)
    monkeypatch.setattr(db_module.time, "sleep", delays.append)

    assert db_module._connect_postgres("postgresql://example") is sentinel
    assert calls == ["postgresql://example"] * 3
    assert delays == [0.1, 0.2]


def test_postgres_connect_raises_retryable_domain_error_after_exhaustion(monkeypatch):
    import app.db as db_module

    def connect(database_url=None):
        error = RuntimeError("Connection refused")
        error.sqlstate = "08001"
        raise error

    monkeypatch.setenv("LEAN_POSTGRES_CONNECT_ATTEMPTS", "2")
    monkeypatch.setenv("LEAN_POSTGRES_CONNECT_RETRY_DELAY_SECONDS", "0")
    monkeypatch.setattr(db_module, "PostgresConnection", connect)

    with pytest.raises(db_module.DatabaseUnavailableError) as error:
        db_module._connect_postgres()

    assert "2 connection attempts" in str(error.value)
    assert "Connection refused" in str(error.value.__cause__)


def test_postgres_connect_does_not_retry_configuration_errors(monkeypatch):
    import app.db as db_module

    calls = 0

    def connect(database_url=None):
        nonlocal calls
        calls += 1
        raise RuntimeError("Access denied")

    monkeypatch.setenv("LEAN_POSTGRES_CONNECT_ATTEMPTS", "5")
    monkeypatch.setattr(db_module, "PostgresConnection", connect)

    with pytest.raises(RuntimeError, match="Access denied"):
        db_module._connect_postgres()

    assert calls == 1
