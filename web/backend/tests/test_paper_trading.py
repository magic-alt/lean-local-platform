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


def import_rows_for_symbol(symbol: str):
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.1", "high": "10.6", "low": "10.0", "close": "10.2", "volume": "100000"},
        {"date": "2024-01-04", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.4", "volume": "100000"},
    ]
    return import_ashare_research_data(
        symbol=symbol,
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


def import_benchmark_rows():
    import app.db as db_module

    with db_module.db() as connection:
        for trade_date, close in (("2024-01-03", 100.0), ("2024-01-04", 101.0)):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                     data_type, open, high, low, close, volume, adjust, source, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "idx-000300",
                    "000300",
                    "equity",
                    "china",
                    "china",
                    trade_date,
                    "daily",
                    "trade",
                    close,
                    close,
                    close,
                    close,
                    1000000,
                    "raw",
                    "unit",
                    "now",
                ),
            )


def test_paper_daily_match_creates_order_position_and_snapshot(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()
    import_benchmark_rows()

    from app.services.paper import create_session, create_signal, list_daily_reports, list_orders, list_positions, list_snapshots, match_daily_orders

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
    reports = list_daily_reports(session["id"])
    assert reports[-1]["report"]["tradeDate"] == "2024-01-04"
    assert reports[-1]["trades"][0]["status"] == "filled"
    assert reports[-1]["positions"][0]["symbol"] == "600519"
    assert reports[-1]["snapshot"]["equity"] > 0
    assert reports[-1]["qa"]["passed"] is True
    report = reports[-1]["report"]
    assert report["initialCash"] == 100000
    assert report["cash"] == reports[-1]["snapshot"]["cash"]
    assert report["NAV"] == reports[-1]["snapshot"]["equity"]
    assert report["benchmark"]["symbol"] == "000300"
    assert report["benchmark"]["close"] == 101.0
    assert round(report["benchmark"]["dailyReturn"], 6) == 0.01
    assert report["cumulativeReturn"] is not None
    assert report["excessReturn"] is not None
    assert len(report["fingerprint"]) == 64
    assert report["dataSourceStatus"]["benchmark"]["source"] == "unit"
    assert report["positionWeights"][0]["symbol"] == "600519"


def test_paper_constraints_reject_blacklist_watchlist_cash_floor_and_missing_status(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.paper import create_session, create_signal, match_daily_orders

    blacklist = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "blacklist": "600519"})
    create_signal(blacklist["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(blacklist["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "blacklisted"

    watchlist = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "watchlist": "000001"})
    create_signal(watchlist["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(watchlist["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "not_in_watchlist"

    observe_only = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "observeOnlySymbols": "600519"})
    create_signal(observe_only["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(observe_only["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "observe_only"

    cash_floor = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "minCash": 100000})
    create_signal(cash_floor["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(cash_floor["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "cash_floor"

    max_positions = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "maxPositions": 0})
    create_signal(max_positions["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(max_positions["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "max_positions"

    missing_status = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    create_signal(missing_status["id"], trade_date="2024-01-02", side="buy", target_percent=1)
    import app.db as db_module

    with db_module.db() as connection:
        connection.execute("delete from ashare_trade_status where symbol = ? and trade_date = ?", ("600519", "2024-01-03"))
    assert match_daily_orders(missing_status["id"], "2024-01-03", auto_signal=False)["orders"][0]["reason"] == "trade_status_missing"


def test_paper_constraints_cap_weight_and_block_st_buy(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.ashare_repository import import_trade_status
    from app.services.paper import create_session, create_signal, match_daily_orders

    capped = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "maxPositionWeight": 0.1})
    create_signal(capped["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    capped_order = match_daily_orders(capped["id"], "2024-01-04", auto_signal=False)["orders"][0]
    assert capped_order["status"] == "rejected"
    assert capped_order["reason"] == "max_position_weight"

    import_trade_status(
        [
            {
                "symbol": "600519",
                "tradeDate": "2024-01-04",
                "isSt": True,
                "canBuy": True,
                "canSell": True,
            }
        ],
        source="official-unit",
    )
    st_blocked = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    create_signal(st_blocked["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(st_blocked["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "st_blocked"


def test_paper_multi_symbol_session_fills_then_rejects_max_positions(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows_for_symbol("600519")
    import_rows_for_symbol("000001")

    from app.services.paper import create_session, create_signal, list_positions, match_daily_orders

    session = create_session(
        {
            "symbol": "600519",
            "symbols": ["600519", "000001"],
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "maxPositions": 1,
            "maxPositionWeight": 0.4,
        }
    )
    create_signal(session["id"], trade_date="2024-01-03", side="buy", symbol="600519", target_percent=0.4)
    create_signal(session["id"], trade_date="2024-01-03", side="buy", symbol="000001", target_percent=0.4)

    orders = match_daily_orders(session["id"], "2024-01-04", auto_signal=False)["orders"]

    assert orders[0]["symbol"] == "600519"
    assert orders[0]["status"] == "filled"
    assert orders[1]["symbol"] == "000001"
    assert orders[1]["status"] == "rejected"
    assert orders[1]["reason"] == "max_positions"
    assert [position["symbol"] for position in list_positions(session["id"])] == ["600519"]
