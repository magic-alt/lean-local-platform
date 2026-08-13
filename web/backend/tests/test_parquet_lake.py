from __future__ import annotations

import polars as pl


def _native_daily(root, symbol: str = "000001.SZ"):
    target = root / "silver" / "daily" / "current" / "trade_date=20260703" / "data.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        {
            "ts_code": [symbol], "trade_date": ["20260703"],
            "open": [10.0], "high": [11.0], "low": [9.0], "close": [10.5],
            "pre_close": [10.0], "pct_chg": [5.0], "vol": [1000.0], "amount": [10000.0],
            "adj_factor": [1.0], "turnover_rate": [1.0],
        }
    ).write_parquet(target)
    return target


def test_adopt_registers_existing_native_lake_without_export(tmp_path, monkeypatch):
    from app.db import init_db
    from app.services import market_lake, parquet_lake

    init_db()
    _native_daily(tmp_path)
    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path)

    result = parquet_lake.export_market_daily_bars(source="tushare")

    assert result["rowCount"] == 1
    assert result["fileCount"] == 1
    assert result["files"][0]["relativePath"].endswith("trade_date=20260703/data.parquet")


def test_duckdb_query_reads_native_parquet_authority(tmp_path, monkeypatch):
    from app.db import init_db
    from app.services import market_lake, parquet_lake

    init_db()
    _native_daily(tmp_path, "600519.SH")
    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path)

    result = parquet_lake.query_duckdb_bars(
        asset_class="equity", symbol="600519", market="china", venue="china",
        resolution="daily", data_type="trade", provider_source="tushare",
        allow_research_source=True,
    )

    assert result["enabled"] is True
    assert result["source"] == "parquet"
    assert result["effectiveEngine"] == "duckdb"
    assert result["count"] == 1
    assert result["items"][0]["close"] == 10.5


def test_dataset_listing_discovers_native_scope(tmp_path, monkeypatch):
    from app.services import market_lake, parquet_lake

    _native_daily(tmp_path)
    monkeypatch.setattr(market_lake, "PARQUET_DIR", tmp_path)
    monkeypatch.setattr(parquet_lake, "PARQUET_DIR", tmp_path)

    datasets = parquet_lake.list_datasets()

    assert len(datasets) == 1
    assert datasets[0]["source"] == "tushare"
    assert datasets[0]["row_count"] == 1


def test_removed_database_export_routes_are_absent():
    from app.main import app

    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    assert ("/api/data/parquet/export", "POST") not in routes
    assert ("/api/data/parquet/rebuild", "POST") not in routes
