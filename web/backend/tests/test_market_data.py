import pytest
from fastapi.testclient import TestClient


def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    return db_module


def test_batch_daily_writer_reuses_existing_instrument_id(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    from app.services.market_repository import upsert_instrument, upsert_market_daily_bars_batch

    existing_id = upsert_instrument(
        symbol="000001",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
    )
    result = upsert_market_daily_bars_batch(
        [
            {
                "symbol": "000001",
                "trade_date": "2026-07-17",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1000,
            }
        ],
        source="tushare",
        bulk=True,
    )

    with db_module.db() as connection:
        row = connection.execute(
            "select instrument_id from market_daily_bars where symbol='000001'"
        ).fetchone()
    assert result == {"count": 1, "symbols": 1}
    assert row["instrument_id"] == existing_id


def test_query_database_bars_reads_local_market_daily_table(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into instruments
                (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange, venue, status, metadata_json, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-000001",
                "000001",
                "000001",
                "平安银行",
                "equity",
                "china",
                "SZ",
                "china",
                "active",
                "{}",
                "unit",
                "now",
                "now",
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type, open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-000001",
                "000001",
                "equity",
                "china",
                "china",
                "2026-07-03",
                "daily",
                "trade",
                10.29,
                10.40,
                10.18,
                10.29,
                86332664,
                100000,
                "raw",
                "akshare",
                "batch-1",
                "now",
            ),
        )

    from app.services.market_data import query_database_bars

    result = query_database_bars(
        asset_class="equity",
        symbol="SZ000001",
        market="china",
        venue="china",
        resolution="daily",
        data_type="trade",
    )

    assert result["enabled"] is True
    assert result["source"] == "database"
    assert result["count"] == 1
    assert result["items"][0] == {
        "timestamp": "2026-07-03",
        "open": 10.29,
        "high": 10.40,
        "low": 10.18,
        "close": 10.29,
        "volume": 86332664.0,
        "source": "akshare",
    }


def test_data_query_api_selects_database_source(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into instruments
                (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange, venue, status, metadata_json, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519",
                "600519",
                "600519",
                "贵州茅台",
                "equity",
                "china",
                "SH",
                "china",
                "active",
                "{}",
                "unit",
                "now",
                "now",
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type, open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519",
                "600519",
                "equity",
                "china",
                "china",
                "2026-07-03",
                "daily",
                "trade",
                1450.0,
                1470.0,
                1440.0,
                1460.0,
                1000,
                100000,
                "raw",
                "akshare",
                "batch-1",
                "now",
            ),
        )

    from app.main import app

    client = TestClient(app)
    response = client.get(
        "/api/data/query",
        params={
            "source": "database",
            "assetClass": "equity",
            "symbol": "SH600519",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
            "providerSource": "akshare",
            "allowResearchSource": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["count"] == 1
    assert payload["items"][0]["timestamp"] == "2026-07-03"
    assert payload["items"][0]["close"] == 1460.0


def test_data_query_api_auto_provider_uses_fallback_chain(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into instruments
                (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange, venue, status, metadata_json, source, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519",
                "600519",
                "600519",
                "贵州茅台",
                "equity",
                "china",
                "SH",
                "china",
                "active",
                "{}",
                "unit",
                "now",
                "now",
            ),
        )
        connection.execute(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type, open, high, low, close, volume, amount, adjust, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "inst-600519",
                "600519",
                "equity",
                "china",
                "china",
                "2026-06-03",
                "daily",
                "trade",
                1450.0,
                1470.0,
                1440.0,
                1460.0,
                1000,
                100000,
                "raw",
                "akshare",
                "batch-1",
                "now",
            ),
        )

    from app.main import app

    client = TestClient(app)
    blocked = client.get(
        "/api/data/query",
        params={
            "source": "database",
            "assetClass": "equity",
            "symbol": "SH600519",
            "market": "china",
            "venue": "china",
            "startDate": "2026-06-01",
            "endDate": "2026-06-30",
            "providerSource": "auto",
        },
    )
    assert blocked.status_code == 400

    response = client.get(
        "/api/data/query",
        params={
            "source": "database",
            "assetClass": "equity",
            "symbol": "SH600519",
            "market": "china",
            "venue": "china",
            "startDate": "2026-06-01",
            "endDate": "2026-06-30",
            "providerSource": "auto",
            "allowResearchSource": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["providerMode"] == "auto"
    assert payload["providerSource"] == "akshare"
    assert payload["count"] == 1
    assert payload["sourceAttempts"][0]["source"] == "tushare"
    assert payload["sourceAttempts"][1]["source"] == "akshare"


def test_clickhouse_mirror_splits_rows_into_partition_safe_five_year_blocks(monkeypatch):
    from app.services import market_data

    inserts = []

    class Client:
        def insert(self, table, rows, column_names):
            inserts.append((table, list(rows), column_names))

    monkeypatch.setattr(market_data, "enabled", lambda: True)
    monkeypatch.setattr(market_data, "ensure_schema", lambda: True)
    monkeypatch.setattr(market_data, "_client", lambda *args, **kwargs: Client())
    monkeypatch.setattr(market_data, "set_dependency_status", lambda *args, **kwargs: None)

    result = market_data.mirror_rows(
        {"symbol": "600519", "asset_class": "equity", "market": "china", "source": "tushare"},
        [
            {"date": "2000-01-03", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"},
            {"date": "2004-12-31", "open": "2", "high": "2", "low": "2", "close": "2", "volume": "2"},
            {"date": "2005-01-04", "open": "3", "high": "3", "low": "3", "close": "3", "volume": "3"},
        ],
    )

    assert result == {"enabled": True, "inserted": 3, "skipped": 0, "batches": 2}
    assert [len(item[1]) for item in inserts] == [2, 1]


def test_clickhouse_schema_uses_year_partition(monkeypatch):
    from app.services import market_data

    commands: list[str] = []

    class Client:
        def command(self, sql):
            commands.append(sql)

        def query(self, sql):
            class Result:
                result_rows = [["toYear(timestamp)"]]

            return Result()

    monkeypatch.setattr(market_data, "_SCHEMA_READY", False)
    monkeypatch.setattr(market_data, "enabled", lambda: True)
    monkeypatch.setattr(market_data, "_client", lambda *args, **kwargs: Client())

    assert market_data.ensure_schema() is True
    assert "PARTITION BY toYear(timestamp)" in commands[1]


def test_clickhouse_schema_rejects_legacy_month_partition(monkeypatch):
    from app.services import market_data

    class Client:
        def command(self, sql):
            return None

        def query(self, sql):
            class Result:
                result_rows = [["toYYYYMM(timestamp)"]]

            return Result()

    monkeypatch.setattr(market_data, "_SCHEMA_READY", False)
    monkeypatch.setattr(market_data, "enabled", lambda: True)
    monkeypatch.setattr(market_data, "_client", lambda *args, **kwargs: Client())

    with pytest.raises(RuntimeError, match="clickhouse_schema_migration_required"):
        market_data.ensure_schema()


def test_clickhouse_mirror_batches_multiple_assets_into_shared_inserts(monkeypatch):
    from app.services import market_data

    inserts = []

    class Client:
        def insert(self, table, rows, column_names):
            inserts.append((table, list(rows), column_names))

    monkeypatch.setattr(market_data, "enabled", lambda: True)
    monkeypatch.setattr(market_data, "ensure_schema", lambda: True)
    monkeypatch.setattr(market_data, "_client", lambda *args, **kwargs: Client())
    monkeypatch.setattr(market_data, "set_dependency_status", lambda *args, **kwargs: None)
    row = {"date": "2026-07-17", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}

    results = market_data.mirror_rows_batch(
        [
            ({"symbol": "600519", "market": "china", "source": "tushare"}, [row]),
            ({"symbol": "000001", "market": "china", "source": "tushare"}, [row]),
        ]
    )

    assert len(inserts) == 1
    assert len(inserts[0][1]) == 2
    assert [result["inserted"] for result in results] == [1, 1]
    assert [result["batches"] for result in results] == [1, 1]


def test_clickhouse_symbol_replace_deletes_then_reloads_canonical(monkeypatch):
    from app.services import market_data

    commands = []
    mirrored = []

    class Client:
        def query(self, sql):
            class Result:
                result_rows = [[3]]

            return Result()

        def command(self, sql):
            commands.append(sql)

    monkeypatch.setattr(market_data, "enabled", lambda: True)
    monkeypatch.setattr(market_data, "ensure_schema", lambda: True)
    monkeypatch.setattr(market_data, "_client", lambda *args, **kwargs: Client())
    monkeypatch.setattr(
        market_data,
        "query_database_bars",
        lambda **kwargs: {
            "items": []
            if kwargs["symbol"] == "000300"
            else [{"date": "2026-07-22", "open": "1", "high": "1", "low": "1", "close": "1", "volume": "1"}]
        },
    )
    monkeypatch.setattr(
        market_data,
        "mirror_rows_batch",
        lambda entries: mirrored.extend(entries) or [{"inserted": len(rows)} for _, rows in entries],
    )

    result = market_data.replace_china_equity_symbols_from_canonical(["SH600519", "000300"])

    assert result["deleted"] == 3
    assert result["inserted"] == 1
    assert result["symbols"] == ["000300", "600519"]
    assert "mutations_sync=2" in commands[0]
    assert [metadata["symbol"] for metadata, _ in mirrored] == ["600519"]
