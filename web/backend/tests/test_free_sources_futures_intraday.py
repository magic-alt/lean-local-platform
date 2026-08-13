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


def test_intraday_import_writes_market_intraday_bars(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services import market_lake
    from app.services.intraday import import_intraday_bars

    result = import_intraday_bars(
        [
            {"timestamp": "2026-07-03 09:35:00", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000},
            {"timestamp": "2026-07-03 09:40:00", "open": 10.5, "high": 11.5, "low": 10, "close": 11, "volume": 1200},
        ],
        symbol="600519",
        asset_class="equity",
        market="china",
        venue="china",
        frequency="5m",
        source="unit",
    )

    assert result["count"] == 2
    count = market_lake.aggregate(
        kind="bars", asset_class="equity", market="china", venue="china",
        resolution="5m", data_type="trade", source="unit", columns="count(*) as count",
    )["count"]
    assert count == 2


def test_tqsdk_normalizer_and_futures_main_mapping(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)

    from app.services.futures import import_contracts, import_daily_bars, refresh_main_mapping
    from app.services.tqsdk_adapter import contract_code_from_tq_symbol, exchange_from_tq_symbol, normalize_tqsdk_kline_rows

    assert contract_code_from_tq_symbol("DCE.m2409") == "M2409"
    assert exchange_from_tq_symbol("KQ.m@DCE.m") == "DCE"
    rows = normalize_tqsdk_kline_rows(
        "DCE.m2409",
        [{"datetime": "2024-01-03 00:00:00", "open": "3500", "high": "3510", "low": "3490", "close": "3505", "volume": "100", "close_oi": "1500"}],
    )
    assert rows[0]["contract_code"] == "M2409"
    assert rows[0]["open_interest"] == "1500"

    import_contracts(
        [
            {"contract_code": "M2405", "product": "M", "exchange": "DCE", "last_trade_date": "2024-05-15"},
            {"contract_code": "M2409", "product": "M", "exchange": "DCE", "last_trade_date": "2024-09-15"},
        ],
        source="unit",
    )
    import_daily_bars(
        [
            {"contract_code": "M2405", "trade_date": "2024-01-03", "close": 3500, "volume": 10000, "open_interest": 900},
            {"contract_code": "M2409", "trade_date": "2024-01-03", "close": 3600, "volume": 8000, "open_interest": 1500},
        ],
        source="unit",
    )

    result = refresh_main_mapping(product="M", exchange="DCE", start_date="2024-01-03", end_date="2024-01-03")

    assert result["count"] == 1
    with db_module.db() as connection:
        row = connection.execute("select * from futures_main_mapping where product = 'M'").fetchone()
    assert row["main_symbol"] == "M2409"
