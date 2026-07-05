def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.domain.assets as assets_module
    import app.lean as lean_module

    data_dir = tmp_path / "Data"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(lean_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(lean_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(assets_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(assets_module, "REPO_ROOT", tmp_path)
    db_module.init_db()


def import_rows():
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.1", "high": "10.6", "low": "10.0", "close": "10.2", "volume": "100000"},
        {"date": "2024-01-04", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.4", "volume": "100000"},
    ]
    return import_ashare_research_data(
        symbol="600519",
        provider="unit",
        market="china",
        rows=rows,
        source="unit",
        overwrite=True,
        adjust="raw",
        outputsize="",
        asset_class="equity",
        venue="china",
        resolution="daily",
        data_type="trade",
        start_date=None,
        end_date=None,
    )


def test_paper_daily_match_creates_order_position_and_snapshot(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.paper import create_session, create_signal, list_orders, list_positions, list_snapshots, match_daily_orders

    session = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    signal = create_signal(
        session["id"],
        trade_date="2024-01-03",
        side="buy",
        target_percent=1,
        reason="unit_buy",
    )
    result = match_daily_orders(session["id"], "2024-01-03", auto_signal=False)
    assert result["executionPolicy"] == "next_open"
    assert result["orders"] == []

    result = match_daily_orders(session["id"], "2024-01-04", auto_signal=False)

    orders = list_orders(session["id"])
    positions = list_positions(session["id"])
    snapshots = list_snapshots(session["id"])

    assert signal["status"] == "created"
    assert result["orders"][0]["status"] == "filled"
    assert result["orders"][0]["trade_date"] == "2024-01-04"
    assert result["orders"][0]["fill_price"] == 10.2
    assert orders[0]["quantity"] % 100 == 0
    assert positions[0]["quantity"] == orders[0]["quantity"]
    assert snapshots[0]["equity"] > 0
    assert snapshots[-1]["positions"][0]["symbol"] == "600519"
