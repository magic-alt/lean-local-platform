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

    response = TestClient(app).get(
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

    assert response.status_code == 200
    payload = response.json()
    assert payload["providerMode"] == "auto"
    assert payload["providerSource"] == "akshare"
    assert payload["count"] == 1
    assert payload["sourceAttempts"][0]["source"] == "akshare"
