from __future__ import annotations

import json
import os
from pathlib import Path
import re

import polars as pl


OBSOLETE_RUNTIME_RELATION = re.compile(
    r"(?i)(?:from|join|into|update|delete\s+from)\s+"
    r"(?:market_daily_bars|market_trade_status|market_intraday_bars|market_ticks|"
    r"adjustment_factors|daily_basic_values|all_factor_values|daily_basic_factor_values)\b"
)


def test_runtime_has_no_mysql_market_time_series_sql():
    app_root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    for path in app_root.rglob("*.py"):
        matches = OBSOLETE_RUNTIME_RELATION.findall(path.read_text(encoding="utf-8"))
        if matches:
            violations.append(str(path.relative_to(app_root)))
    assert violations == []


def test_control_plane_reconciliation_migration_repairs_schema_drift():
    from app import db as db_module

    db_module.init_db()
    with db_module.db() as connection:
        connection.execute("drop table provider_raw_archive_issues")
        connection.execute("drop table data_sync_runs")
        connection.execute("drop table asset_capabilities")
        connection.execute(
            "delete from schema_migrations where revision='0052_reconcile_market_lake_control_plane'"
        )

    db_module.init_db()

    with db_module.db() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "select name from sqlite_master where type='table'"
            ).fetchall()
        }
        issue_columns = {
            row["name"]
            for row in connection.execute("pragma table_info(provider_raw_archive_issues)").fetchall()
        }
    assert {"provider_raw_archive_issues", "data_sync_runs", "asset_capabilities"} <= tables
    assert {"status", "resolution_code", "resolution_run_id", "resolved_at"} <= issue_columns


def test_native_silver_daily_layout_is_read_without_copy(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    target = tmp_path / "silver" / "daily" / "current" / "trade_date=20260811" / "data.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "ts_code": ["000001.SZ"], "trade_date": ["20260811"],
            "open": [11.1], "high": [11.3], "low": [11.0], "close": [11.26],
            "pre_close": [11.2], "pct_chg": [0.54], "vol": [100.0], "amount": [1000.0],
            "adj_factor": [139.008], "turnover_rate": [0.3],
        }
    ).write_parquet(target)

    rows = market_lake.query_rows(
        kind="bars", source="tushare", columns="symbol,trade_date,close",
        predicates=("symbol=?",), parameters=("000001",),
    )

    assert rows == [{"symbol": "000001", "trade_date": "2026-08-11", "close": 11.26}]


def test_single_file_index_layout_uses_file_date_coverage(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    target = tmp_path / "gold" / "qlib_staging" / "full" / "SH000300.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "date": ["2026-08-10", "2026-08-11"],
            "symbol": ["SH000300", "SH000300"],
            "open": [4000.0, 4010.0],
            "high": [4020.0, 4030.0],
            "low": [3990.0, 4000.0],
            "close": [4010.0, 4020.0],
            "volume": [100.0, 120.0],
        }
    ).write_parquet(target)

    manifest = market_lake.adopt_legacy_files(
        kind="bars",
        asset_class="index",
        market="china",
        venue="china",
        resolution="daily",
        data_type="trade",
        adjust="raw",
        source="tushare",
    )

    assert manifest["files"][0]["year"] == 2026
    assert manifest["files"][0]["firstTimestamp"] == "2026-08-10"
    assert manifest["files"][0]["lastTimestamp"] == "2026-08-11"


def test_native_auxiliary_layouts_are_discovered_without_custom_manifest(tmp_path, monkeypatch):
    """The local bronze/silver layers must not depend on a ``kind=`` tree."""
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    target = tmp_path / "bronze" / "tushare" / "current" / "adj_factor" / "trade_date=20260811" / "data.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame({"ts_code": ["000001.SZ"], "trade_date": ["20260811"], "adj_factor": [139.008]}).write_parquet(target)

    scopes = market_lake.matching_scopes(
        kind="adjustment_factor", asset_class="equity", market="china", source="tushare",
    )
    assert len(scopes) == 1
    rows = market_lake.query_matching(
        kind="adjustment_factor", asset_class="equity", market="china", source="tushare",
        columns="symbol,trade_date,adj_factor", predicates=("symbol=?",), parameters=("000001",),
    )
    assert rows == [{"symbol": "000001", "trade_date": "2026-08-11", "adj_factor": 139.008}]


def test_native_incremental_write_replaces_partition_and_retains_revision(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    target = tmp_path / "silver" / "daily" / "current" / "trade_date=20260811" / "data.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame(
        {
            "ts_code": ["000001.SZ"], "trade_date": ["20260811"],
            "open": [11.1], "high": [11.3], "low": [11.0], "close": [11.2],
            "pre_close": [11.1], "pct_chg": [0.9], "vol": [100.0], "amount": [1000.0],
            "adj_factor": [139.0], "turnover_rate": [0.3],
        }
    ).write_parquet(target)

    result = market_lake.upsert_rows(
        [{"symbol": "000001", "trade_date": "2026-08-11", "close": 11.26}],
        kind="bars", source="tushare",
    )

    assert result["changedRows"] == 1
    assert pl.read_parquet(target).filter(pl.col("ts_code") == "000001.SZ").item(0, "close") == 11.26
    assert list((tmp_path / "bronze" / "tushare" / "revisions" / "lean_bars").rglob("data.parquet"))


def test_native_replay_does_not_create_a_revision(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    row = {"symbol": "000001", "trade_date": "2026-08-11", "close": 11.26}
    (tmp_path / "silver" / "daily" / "current" / "trade_date=20260811").mkdir(parents=True)

    first = market_lake.upsert_rows([row], kind="bars", source="tushare")
    second = market_lake.upsert_rows([row], kind="bars", source="tushare")

    assert first["changedRows"] == 1
    assert second["changedRows"] == 0
    revisions = tmp_path / "bronze" / "tushare" / "revisions"
    assert not (revisions / "lean_daily").exists()
    assert not (revisions / "lean_bars").exists()


def test_provider_bronze_partition_replay_is_a_noop_and_correction_is_versioned(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    columns = ("ts_code", "trade_date", "net_mf_amount")
    first = market_lake.write_tushare_bronze_partition(
        "moneyflow", "2026-08-17",
        [{"ts_code": "000001.SZ", "trade_date": "20260817", "net_mf_amount": 10.0}],
        columns=columns,
    )
    replay = market_lake.write_tushare_bronze_partition(
        "moneyflow", "2026-08-17",
        [{"ts_code": "000001.SZ", "trade_date": "20260817", "net_mf_amount": 10.0}],
        columns=columns,
    )
    corrected = market_lake.write_tushare_bronze_partition(
        "moneyflow", "2026-08-17",
        [{"ts_code": "000001.SZ", "trade_date": "20260817", "net_mf_amount": 11.0}],
        columns=columns,
    )

    assert first["changed"] is True
    assert replay["changed"] is False
    assert corrected["changed"] is True
    revisions = tmp_path / "bronze" / "tushare" / "revisions" / "moneyflow"
    assert list(revisions.rglob("data.parquet"))


def test_tushare_current_directory_mtime_tracks_publish_and_replay(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    columns = ("ts_code", "trade_date", "close")
    rows = [{"ts_code": "000001.SZ", "trade_date": "20260901", "close": 11.2}]
    market_lake.write_tushare_bronze_partition("daily", "2026-09-01", rows, columns=columns)
    current = tmp_path / "bronze" / "tushare" / "current"
    dataset = current / "daily"
    os.utime(current, (1, 1))
    os.utime(dataset, (1, 1))

    market_lake.write_tushare_bronze_partition("daily", "2026-09-01", rows, columns=columns)

    assert current.stat().st_mtime > 1
    assert dataset.stat().st_mtime > 1


def test_tushare_extended_directory_mtime_tracks_publish_and_replay(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    columns = ("ts_code", "ann_date", "cash_div")
    rows = [{"ts_code": "000001.SZ", "ann_date": "20260101", "cash_div": 0.1}]
    market_lake.write_tushare_extended_bronze_partition(
        "dividend", "000001.SZ", rows, columns=columns
    )
    current = tmp_path / "bronze" / "tushare" / "current"
    extended = current / "extended"
    dataset = extended / "dividend"
    os.utime(current, (1, 1))
    os.utime(extended, (1, 1))
    os.utime(dataset, (1, 1))

    market_lake.write_tushare_extended_bronze_partition(
        "dividend", "000001.SZ", rows, columns=columns
    )

    assert current.stat().st_mtime > 1
    assert extended.stat().st_mtime > 1
    assert dataset.stat().st_mtime > 1


def test_extended_symbol_partition_is_normalized_and_current_remains_published(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    columns = ("ts_code", "ann_date", "cash_div")
    first = market_lake.write_tushare_extended_bronze_partition(
        "dividend", "000001.SZ",
        [{"ts_code": "000001.SZ", "ann_date": "20260101", "cash_div": 0.1}],
        columns=columns,
    )
    corrected = market_lake.write_tushare_extended_bronze_partition(
        "dividend", "000001_SZ",
        [{"ts_code": "000001.SZ", "ann_date": "20260101", "cash_div": 0.2}],
        columns=columns,
    )

    current = tmp_path / "bronze" / "tushare" / "current" / "extended" / "dividend" / "trade_date=000001_SZ"
    assert first["changed"] is True
    assert corrected["changed"] is True
    assert (current / "data.parquet").is_file()
    assert not (current.parent / "trade_date=000001.SZ").exists()
    assert pl.read_parquet(current / "data.parquet").item(0, "cash_div") == 0.2
    assert list((tmp_path / "bronze" / "tushare" / "revisions" / "extended" / "dividend").rglob("data.parquet"))


def test_extended_replay_records_freshness_without_creating_a_revision(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    columns = ("ts_code", "end_date", "revenue")
    rows = [{"ts_code": "000001.SZ", "end_date": "20260630", "revenue": 1.0}]
    market_lake.write_tushare_extended_bronze_partition(
        "income_vip", "20260630", rows, columns=columns, metadata={"ingest_run_id": "first"}
    )
    replay = market_lake.write_tushare_extended_bronze_partition(
        "income_vip", "20260630", rows, columns=columns, metadata={"ingest_run_id": "replay"}
    )

    manifest = json.loads(
        (tmp_path / "bronze/tushare/current/extended/income_vip/trade_date=20260630/manifest.json").read_text()
    )
    assert replay["changed"] is False
    assert replay["checked"] is True
    assert manifest["last_checked_run_id"] == "replay"
    assert manifest["last_checked_at_utc"]
    assert not list((tmp_path / "bronze/tushare/revisions/extended/income_vip").rglob("data.parquet"))


def test_extended_vip_writer_accepts_late_nan_after_null_schema_prefix(tmp_path, monkeypatch):
    from app.services import market_lake

    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    rows = [{"ts_code": "000001.SZ", "metric": None} for _ in range(101)]
    rows.append({"ts_code": "000001.SZ", "metric": float("nan")})

    result = market_lake.write_tushare_extended_bronze_partition(
        "balancesheet_vip", "20260630", rows, columns=("ts_code", "metric")
    )

    target = tmp_path / "bronze/tushare/current/extended/balancesheet_vip/trade_date=20260630/data.parquet"
    assert result["changed"] is True
    assert pl.read_parquet(target).null_count().item(0, "metric") == 102
