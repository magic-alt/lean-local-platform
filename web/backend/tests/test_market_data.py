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


def test_query_sqlite_bars_reads_local_ashare_table(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into ashare_daily_bars
                (symbol, trade_date, open, high, low, close, volume, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("000001", "2026-07-03", 10.29, 10.40, 10.18, 10.29, 86332664, "akshare", "batch-1", "now"),
        )

    from app.services.market_data import query_sqlite_bars

    result = query_sqlite_bars(
        asset_class="equity",
        symbol="SZ000001",
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


def test_data_query_api_selects_sqlite_source(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into ashare_daily_bars
                (symbol, trade_date, open, high, low, close, volume, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("600519", "2026-07-03", 1450.0, 1470.0, 1440.0, 1460.0, 1000, "akshare", "batch-1", "now"),
        )

    from app.main import app

    client = TestClient(app)
    response = client.get(
        "/api/data/query",
        params={
            "source": "sqlite",
            "assetClass": "equity",
            "symbol": "SH600519",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "database"
    assert payload["count"] == 1
    assert payload["items"][0]["timestamp"] == "2026-07-03"
    assert payload["items"][0]["close"] == 1460.0
