from __future__ import annotations


def test_direct_reset_cli_requires_all_three_acknowledgements(monkeypatch):
    import sys

    from scripts import mysql_storage_maintenance

    monkeypatch.setattr(sys, "argv", ["mysql_storage_maintenance.py", "direct-market-reset", "--confirm"])
    try:
        mysql_storage_maintenance.main()
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - makes an accidental safety regression explicit.
        raise AssertionError("direct-market-reset must require --no-backup and --direct-reset")


def test_market_reset_filesystem_cleanup_is_scoped_to_named_child(tmp_path):
    from app.services.storage_maintenance import _remove_directory_contents, _safe_maintenance_directory

    root = tmp_path / "Data"
    parquet = root / "parquet"
    (parquet / "nested").mkdir(parents=True)
    (parquet / "nested" / "part.parquet").write_bytes(b"data")
    (parquet / "manifest.json").write_text("{}", encoding="utf-8")
    assert _remove_directory_contents(parquet, required_leaf="parquet") == 2
    assert list(parquet.iterdir()) == []
    assert _safe_maintenance_directory(parquet, required_leaf="parquet") == parquet.resolve()
    try:
        _remove_directory_contents(root, required_leaf="parquet")
    except RuntimeError as exc:
        assert "unsafe_maintenance_directory" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the Data root must never be accepted as a cleanup target")


def test_maintenance_read_only_blocks_api_writes(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main

    monkeypatch.setattr(main, "MAINTENANCE_READ_ONLY", True)
    response = TestClient(main.app).post("/api/does-not-matter")
    assert response.status_code == 503
    assert response.json()["error_code"] == "MAINTENANCE_READ_ONLY"


def test_clickhouse_reset_is_a_noop_when_disabled(monkeypatch):
    from app.services import market_data

    monkeypatch.setattr(market_data, "CLICKHOUSE_ENABLED", False)
    assert market_data.clear_market_bars() == {"enabled": False, "cleared": False, "reason": "disabled"}


def test_filesystem_object_storage_round_trip_and_migration(tmp_path, monkeypatch):
    import app.db as db_module
    from app.services import db_object_store

    db_module.init_db()
    root = tmp_path / "external-objects"

    monkeypatch.setenv("LEAN_OBJECT_STORE_MODE", "database")
    stored = db_object_store.put_bytes("provider-raw", "daily/a.json.gz", b"payload")
    with db_module.db() as connection:
        assert connection.execute("select count(*) as n from stored_object_chunks").fetchone()["n"] == 1

    monkeypatch.setenv("LEAN_FILE_OBJECT_STORE_DIR", str(root))
    result = db_object_store.migrate_database_objects_to_filesystem(limit=10)
    assert result == {"scanned": 1, "migrated": 1}
    assert db_object_store.read_bytes(stored["id"]) == b"payload"
    with db_module.db() as connection:
        row = connection.execute("select storage_mode,metadata_json from stored_objects where id=?", (stored["id"],)).fetchone()
        assert row["storage_mode"] == "filesystem"
        assert connection.execute("select count(*) as n from stored_object_chunks").fetchone()["n"] == 0
    assert db_object_store.integrity_report()["passed"] is True


def test_daily_basic_eav_cleanup_preserves_uncovered_and_mismatched_rows():
    import app.db as db_module
    from app.services.storage_maintenance import daily_basic_eav_audit, delete_equivalent_daily_basic_eav

    db_module.init_db()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into daily_basic_values(symbol,trade_date,pe,pb,source,batch_id,created_at)
            values ('000001','2026-01-02',10,2,'tushare:daily_basic','batch','now')
            """
        )
        connection.executemany(
            """
            insert into factor_values(symbol,trade_date,factor_name,value,source,batch_id,created_at)
            values ('000001','2026-01-02',? ,?,'tushare:daily_basic','batch','now')
            """,
            [("pe", 10), ("pb", 3), ("unknown", 1)],
        )
    assert daily_basic_eav_audit() == {
        "legacy_rows": 3,
        "uncovered_rows": 0,
        "null_wide_rows": 1,
        "equivalent_rows": 1,
        "mismatched_rows": 1,
    }
    result = delete_equivalent_daily_basic_eav(batch_size=1)
    assert result["deleted"] == 1
    assert result["legacy_rows"] == 2
    assert result["mismatched_rows"] == 1


def test_raw_record_pruning_requires_a_readable_archive(monkeypatch):
    import app.db as db_module
    from app.services.db_object_store import put_bytes
    from app.services.storage_maintenance import prune_expired_provider_raw_records

    db_module.init_db()
    monkeypatch.setenv("LEAN_OBJECT_STORE_MODE", "database")
    stored = put_bytes("provider-raw", "daily/archive.json.gz", b"archive")
    with db_module.db() as connection:
        connection.execute(
            """
            insert into provider_raw_archives
            (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,archive_sha256,
             uncompressed_size,compressed_size,compression,created_at)
            values ('archive','tushare','daily','batch',?,1,'payload','archive',7,7,'gzip','2020-01-01T00:00:00+00:00')
            """,
            (stored["id"],),
        )
        connection.execute(
            """
            insert into provider_raw_records
            (provider,dataset_key,record_key,business_date,instrument_code,payload_json,content_sha256,batch_id,source_updated_at,ingested_at)
            values ('tushare','daily','record','2020-01-01','000001','','hash','batch',null,'2020-01-01T00:00:00+00:00')
            """
        )
    assert prune_expired_provider_raw_records(retention_days=180, limit=10)["deleted"] == 1
    with db_module.db() as connection:
        assert connection.execute("select count(*) as n from provider_raw_records").fetchone()["n"] == 0


def test_canonical_ashare_writes_skip_duplicate_specialized_tables():
    import app.db as db_module
    from app.services import ashare_repository

    db_module.init_db()
    ashare_repository.upsert_daily_bars(
        [{"symbol": "000001", "trade_date": "2026-01-02", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 100}],
        source="tushare",
        batch_id="batch",
        adjust="raw",
        bulk=True,
    )
    ashare_repository.upsert_trade_status(
        [{"symbol": "000001", "trade_date": "2026-01-02", "is_st": True, "is_limit_up": True}],
        source="tushare",
        batch_id="batch",
        bulk=True,
    )
    with db_module.db() as connection:
        legacy = connection.execute(
            """
            select count(*) as n from sqlite_master
            where type in ('table','view') and name in ('ashare_daily_bars','ashare_trade_status')
            """
        ).fetchone()
        assert legacy["n"] == 0
        status = connection.execute(
            "select is_st,is_limit_up from market_trade_status where symbol='000001' and trade_date='2026-01-02'"
        ).fetchone()
        assert status["is_st"] == 1
        assert status["is_limit_up"] == 1
