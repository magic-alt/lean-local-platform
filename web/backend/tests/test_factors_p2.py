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


def seed_factor_dataset():
    from app.services.ashare_repository import (
        upsert_daily_bars,
        upsert_security,
        upsert_trade_calendar,
        upsert_universe_membership,
    )

    symbols = ["000001", "000002", "000003"]
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    for symbol in symbols:
        upsert_security(symbol=symbol, name=symbol, listed_date="2020-01-01")
        upsert_universe_membership("ALL_A", symbol, "2020-01-01", None, source="unit")
    upsert_trade_calendar("china", dates, source="unit")
    closes = {
        "000001": [10.0, 11.0, 12.1],
        "000002": [10.0, 10.0, 9.0],
        "000003": [10.0, 9.0, 8.1],
    }
    rows = []
    for symbol, values in closes.items():
        for trade_date, close in zip(dates, values):
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": 1000,
                }
            )
    upsert_daily_bars(rows, source="unit", batch_id="factor-bars", adjust="raw")


def test_daily_basic_bulk_writer_expands_normalized_provider_rows(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    from app.research import factors
    from app.services import market_lake

    symbol_calls = 0
    date_calls = 0
    normalize_symbol = factors._symbol
    normalize_date = factors._date

    def count_symbol(value):
        nonlocal symbol_calls
        symbol_calls += 1
        return normalize_symbol(value)

    def count_date(value):
        nonlocal date_calls
        date_calls += 1
        return normalize_date(value)

    monkeypatch.setattr(factors, "_symbol", count_symbol)
    monkeypatch.setattr(factors, "_date", count_date)

    written = factors.upsert_daily_basic_factor_values(
        [
            {
                "symbol": "000001",
                "trade_date": "2024-01-02",
                "factors": {"pe_ttm": 8.5, "pb": 0.7},
            },
            {
                "symbol": "600000",
                "trade_date": "2024-01-02",
                "factors": {"pe_ttm": 6.2},
            },
        ],
        batch_id="daily-basic-fast",
        bulk=True,
        chunk_rows=1,
    )

    assert written == 2
    assert symbol_calls == 2
    assert date_calls == 2
    rows = market_lake.query_rows(
        kind="daily_basic", data_type="metric", source="tushare:daily_basic",
        columns="symbol,trade_date,pb,pe_ttm,batch_id", order_by="symbol",
    )
    assert rows == [
        {"symbol": "000001", "trade_date": "2024-01-02", "pb": 0.7, "pe_ttm": 8.5, "batch_id": "daily-basic-fast"},
        {"symbol": "600000", "trade_date": "2024-01-02", "pb": None, "pe_ttm": 6.2, "batch_id": "daily-basic-fast"},
    ]


def test_factor_evaluation_computes_ic_rank_ic_and_quantiles(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)
    seed_factor_dataset()

    from app.research.factors import available_engines, evaluate_factor, import_factor_values

    assert available_engines()["python"] is True
    import_factor_values(
        [
            {"symbol": "000001", "trade_date": "2024-01-02", "factor_name": "momentum", "value": 3.0},
            {"symbol": "000002", "trade_date": "2024-01-02", "factor_name": "momentum", "value": 2.0},
            {"symbol": "000003", "trade_date": "2024-01-02", "factor_name": "momentum", "value": 1.0},
            {"symbol": "000001", "trade_date": "2024-01-03", "factor_name": "momentum", "value": 3.0},
            {"symbol": "000002", "trade_date": "2024-01-03", "factor_name": "momentum", "value": 1.0},
            {"symbol": "000003", "trade_date": "2024-01-03", "factor_name": "momentum", "value": 2.0},
        ],
        source="unit",
    )

    result = evaluate_factor(
        factor_name="momentum",
        universe_code="ALL_A",
        start_date="2024-01-02",
        end_date="2024-01-04",
        forward_days=1,
        quantiles=3,
    )

    assert result["id"]
    assert result["engine"] in {"python", "duckdb", "polars"}
    assert result["observations"] == 6
    assert result["mean_ic"] is not None
    assert result["mean_rank_ic"] is not None
    assert len(result["quantile_returns"]) == 3
    assert result["quantile_returns"][2]["count"] > 0
