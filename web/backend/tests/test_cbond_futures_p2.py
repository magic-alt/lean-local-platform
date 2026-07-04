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


def test_cbond_double_low_pool_excludes_active_call_risk(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.cbond import (
        call_risk_monitor,
        double_low_pool,
        import_call_events,
        import_cbond_daily,
        import_cbond_terms,
    )

    import_cbond_terms(
        [
            {"bond_code": "113001", "bond_name": "Safe Bond", "stock_symbol": "600001", "conversion_price": 10},
            {"bond_code": "123001", "bond_name": "Call Bond", "stock_symbol": "300001", "conversion_price": 20},
        ],
        source="unit",
    )
    import_cbond_daily(
        [
            {"bond_code": "113001", "trade_date": "2024-01-03", "close": 110, "stock_close": 10},
            {"bond_code": "123001", "trade_date": "2024-01-03", "close": 105, "stock_close": 20},
        ],
        source="unit",
    )
    import_call_events(
        [
            {
                "bond_code": "123001",
                "announce_date": "2024-01-02",
                "status": "announced",
                "last_trade_date": "2024-02-01",
            }
        ],
        source="unit",
    )

    risk = call_risk_monitor("2024-01-03")
    assert [item["bond_code"] for item in risk["items"]] == ["123001"]

    pool = double_low_pool(as_of_date="2024-01-03", max_double_low=130, exclude_call_risk=True)
    assert [item["bond_code"] for item in pool["items"]] == ["113001"]
    assert round(pool["items"][0]["double_low"], 6) == 120


def test_futures_main_contract_and_agri_monitor_use_open_interest(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.futures import agri_main_monitor, import_contracts, import_daily_bars, main_contract

    import_contracts(
        [
            {
                "contract_code": "M2405",
                "product": "M",
                "exchange": "DCE",
                "listed_date": "2023-01-01",
                "last_trade_date": "2024-05-15",
                "multiplier": 10,
            },
            {
                "contract_code": "M2409",
                "product": "M",
                "exchange": "DCE",
                "listed_date": "2023-01-01",
                "last_trade_date": "2024-09-15",
                "multiplier": 10,
            },
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

    item = main_contract("M", "2024-01-03")
    assert item is not None
    assert item["contract_code"] == "M2409"
    assert item["daysToExpiry"] > 0

    monitor = agri_main_monitor("2024-01-03", ["M"])
    assert monitor["missing"] == []
    assert [row["contract_code"] for row in monitor["items"]] == ["M2409"]
