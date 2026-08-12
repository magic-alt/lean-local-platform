from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
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
        source_table_count = connection.execute(
            """
            select count(*) as count from information_schema.tables
            where table_schema=database() and table_type='BASE TABLE'
              and table_name like 'src_tushare_%'
            """
        ).fetchone()
        assert source_table_count["count"] == 139
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


def test_mysql_paper_accounts_decimal_foreign_keys_and_isolation() -> None:
    _assert_isolated_database()

    from app.db import db, init_db
    from app.services.paper_accounts import CanonicalStateDivergence, create_account, rebuild_projection

    init_db()
    first = create_account({"name": "MySQL Account A", "initialCash": "1000000.12345678"})
    second = create_account({"name": "MySQL Account B", "initialCash": "250000.00000001"})
    assert first["cash"] == "1000000.12345678"
    assert second["cash"] == "250000.00000001"

    with db() as connection:
        decimal_column = connection.execute(
            """
            select data_type as kind,numeric_precision as precision_value,
                   numeric_scale as scale_value
            from information_schema.columns
            where table_schema=database() and table_name='paper_accounts'
              and column_name='initial_cash'
            """
        ).fetchone()
        foreign_keys = connection.execute(
            """
            select count(*) as count
            from information_schema.referential_constraints
            where constraint_schema=database()
              and table_name in ('paper_account_generations','paper_strategy_deployments',
                                 'paper_execution_cycles','paper_account_projections')
            """
        ).fetchone()
        connection.execute(
            """
            update paper_ledger_entries set precise_amount=precise_amount-100
            where paper_account_id=? and ledger_sequence=1
            """,
            (first["id"],),
        )
    normalized_column = {str(key).lower(): value for key, value in decimal_column.items()}
    assert normalized_column["kind"] == "decimal"
    assert normalized_column["precision_value"] == 28
    assert normalized_column["scale_value"] == 8
    assert foreign_keys["count"] >= 4
    with pytest.raises(CanonicalStateDivergence, match="checkpoint_divergence"):
        rebuild_projection(first["id"], "2026-07-26")
    assert rebuild_projection(second["id"], "2026-07-26")["account"]["cash"] == "250000.00000001"


def test_mysql_concurrent_cycle_creation_is_idempotent() -> None:
    _assert_isolated_database()

    from app.db import db, init_db
    from app.services.paper_accounts import create_account

    init_db()
    account = create_account({"name": "Concurrent cycle account", "initialCash": "1000000"})
    deployment_id = str(uuid.uuid4())
    now = "2026-07-25T12:00:00+00:00"
    with db() as connection:
        connection.execute(
            """
            insert into paper_strategy_deployments (
                id,paper_account_id,generation,supersedes_deployment_id,version,name,status,
                is_primary,project_id,source_backtest_id,strategy_version_id,project_snapshot_id,
                dataset_version_id,experiment_version_id,schedule_type,schedule_expression,
                market_timezone,run_after_market_close,execution_timing,signal_mode,
                parameters_json,universe_config_json,risk_config_version,strategy_fingerprint,
                dataset_fingerprint,deployment_fingerprint,last_successful_trading_date,
                next_scheduled_at,consecutive_failures,created_at,updated_at,paused_at,disabled_at
            ) values (
                ?,?,?,null,1,?,'active',1,?,?,null,?,?,null,'daily_after_close','45 18 * * 1-5',
                'Asia/Shanghai',1,'next_open','paper_execute','{}','{}',1,?,?,?,null,?,0,?,?,null,null
            )
            """,
            (
                deployment_id,
                account["id"],
                1,
                "Concurrent deployment",
                "project-concurrency",
                "backtest-concurrency",
                "snapshot-concurrency",
                "dataset-concurrency",
                f"strategy-{deployment_id}",
                f"dataset-{deployment_id}",
                f"deployment-{deployment_id}",
                now,
                now,
                now,
            ),
        )

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def insert_cycle(index: int) -> str:
        try:
            barrier.wait(timeout=5)
            with db() as connection:
                connection.execute(
                    """
                    insert into paper_execution_cycles (
                        id,paper_account_id,account_generation,deployment_id,trading_date,
                        scheduled_at,started_at,finished_at,status,attempt,idempotency_key,
                        input_fingerprint,account_checkpoint_digest,strategy_fingerprint,
                        dataset_fingerprint,result_digest,signal_count,intent_count,order_count,
                        fill_count,rejected_count,skip_reason,failure_code,failure_detail,
                        lean_run_id,paper_run_id,daily_report_id,lease_holder,lease_expires_at,
                        version,created_at,updated_at
                    ) values (
                        ?,?,1,?,'2026-07-24',?,null,null,'queued',0,?,?,?,?,
                        ?,null,0,0,0,0,0,null,null,null,null,null,null,null,null,1,?,?
                    )
                    """,
                    (
                        f"cycle-{index}-{uuid.uuid4()}",
                        account["id"],
                        deployment_id,
                        now,
                        f"paper:{account['id']}:{deployment_id}:2026-07-24",
                        f"input-{deployment_id}",
                        account["source_checkpoint_digest"],
                        f"strategy-{deployment_id}",
                        f"dataset-{deployment_id}",
                        now,
                        now,
                    ),
                )
            return "inserted"
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            return "duplicate"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(insert_cycle, (1, 2)))

    assert sorted(outcomes) == ["duplicate", "inserted"], errors
    with db() as connection:
        count = connection.execute(
            """
            select count(*) as count from paper_execution_cycles
            where deployment_id=? and trading_date='2026-07-24'
            """,
            (deployment_id,),
        ).fetchone()
    assert count["count"] == 1


def test_mysql_tushare_source_revisions_have_one_current_row() -> None:
    _assert_isolated_database()

    from app.db import db, init_db
    from app.services.tushare_typed_source import persist_typed_source_rows

    init_db()
    with db() as connection:
        connection.execute("delete from src_tushare_stock_company where ts_code=?", ("000001.SZ",))
    original = {"ts_code": "000001.SZ", "com_name": "Original", "setup_date": "19910403"}
    assert persist_typed_source_rows("stock_company", [original], "mysql-batch-1")["inserted"] == 1
    assert persist_typed_source_rows(
        "stock_company", [{**original, "com_name": "Revised"}], "mysql-batch-2"
    )["revised"] == 1

    with db() as connection:
        rows = connection.execute(
            """
            select `_revision_no`,`_is_current`,`com_name`
            from `src_tushare_stock_company`
            where `ts_code`='000001.SZ'
            order by `_revision_no`
            """
        ).fetchall()
        current_unique = connection.execute(
            """
            select count(*) as count from information_schema.statistics
            where table_schema=database()
              and table_name='src_tushare_stock_company'
              and non_unique=0
              and column_name='_current_natural_key_hash'
            """
        ).fetchone()
    assert [(row["_revision_no"], row["_is_current"], row["com_name"]) for row in rows] == [
        (1, 0, "Original"),
        (2, 1, "Revised"),
    ]
    assert current_unique["count"] == 1


def test_mysql_local_infile_loads_canonical_and_typed_daily_batches() -> None:
    _assert_isolated_database()

    from app.db import db, init_db
    from app.services.market_repository import upsert_market_daily_bars_batch
    from app.services.tushare_typed_source import persist_typed_source_rows

    init_db()
    with db() as connection:
        connection.execute("delete from src_tushare_daily where ts_code=?", ("999999.SZ",))
        connection.execute(
            "delete from market_daily_bars where source=?",
            ("mysql_local_infile_probe",),
        )
    rows = [
        {
            "symbol": "999999.SZ",
            "ts_code": "999999.SZ",
            "trade_date": (date(2023, 1, 1) + timedelta(days=index)).strftime("%Y%m%d"),
            "open": 10 + index / 10_000,
            "high": 11 + index / 10_000,
            "low": 9 + index / 10_000,
            "close": 10.5 + index / 10_000,
            "pre_close": 10,
            "change": 0.5,
            "pct_chg": 5,
            "vol": 1000 + index,
            "amount": 10000 + index,
            "volume": 1000 + index,
            "pct_change": 5,
        }
        for index in range(1_000)
    ]
    canonical = upsert_market_daily_bars_batch(
        rows,
        source="mysql_local_infile_probe",
        batch_id="mysql-local-infile-canonical",
        bulk=True,
    )
    typed = persist_typed_source_rows("daily", rows, "mysql-local-infile-typed")

    assert canonical == {"count": 1_000, "symbols": 1}
    assert typed["inserted"] == 1_000
    with db() as connection:
        canonical_count = connection.execute(
            "select count(*) as count from market_daily_bars where batch_id=?",
            ("mysql-local-infile-canonical",),
        ).fetchone()
        typed_count = connection.execute(
            "select count(*) as count from src_tushare_daily where `_batch_id`=?",
            ("mysql-local-infile-typed",),
        ).fetchone()
    assert canonical_count["count"] == 1_000
    assert typed_count["count"] == 1_000
