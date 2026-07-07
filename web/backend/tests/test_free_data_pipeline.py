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
    return db_module


def test_import_ashare_daily_sample_orchestrates_import_compare_and_parquet(monkeypatch):
    from app.services import free_data_pipeline

    calls = []

    def fake_fetch(symbol, provider, **kwargs):
        calls.append((symbol, provider, kwargs["start_date"], kwargs["end_date"], kwargs["adjust"]))
        return {"symbol": symbol, "source": provider, "rows": 2}

    def fake_compare(**kwargs):
        return {"symbol": kwargs["symbol"], "severity": "ok", "sources": kwargs["sources"]}

    def fake_export(**kwargs):
        return {"rowCount": 4, "source": kwargs["source"]}

    monkeypatch.setattr(free_data_pipeline, "fetch_and_import_symbol", fake_fetch)
    monkeypatch.setattr(free_data_pipeline, "compare_ashare_daily_sources", fake_compare)
    monkeypatch.setattr(free_data_pipeline, "export_market_daily_bars", fake_export)

    result = free_data_pipeline.import_ashare_daily_sample(
        symbols=["sh600519"],
        providers=["akshare", "baostock"],
        primary_provider="akshare",
        start_date="2026-01-01",
        end_date="2026-01-05",
    )

    assert result["symbols"] == ["600519"]
    assert result["providers"] == ["akshare", "baostock"]
    assert result["importCount"] == 2
    assert result["errorCount"] == 0
    assert result["qualityReports"][0]["sources"] == ["akshare", "baostock"]
    assert result["parquet"]["source"] == "akshare"
    assert calls[0] == ("600519", "akshare", "2026-01-01", "2026-01-05", "raw")


def test_free_sample_cli_exit_code_allows_non_primary_provider_gap():
    from scripts.import_ashare_free_sample import exit_code_for_result

    result = {
        "importCount": 2,
        "errorCount": 1,
        "errors": [{"symbol": "600519", "provider": "adata", "error": "empty_dataset"}],
    }

    assert exit_code_for_result(result, "akshare") == 0
    result["errors"].append({"symbol": "600519", "provider": "akshare", "error": "provider_failed"})
    assert exit_code_for_result(result, "akshare") == 2


def test_adata_and_baostock_provider_imports_write_canonical_tables(tmp_path, monkeypatch):
    db_module = configure_temp_platform(tmp_path, monkeypatch)

    from app.services import data as data_module

    def fake_rows(symbol, start=None, end=None, adjust="raw"):
        assert symbol == "600519"
        assert start == "2026-01-02"
        assert end == "2026-01-05"
        assert adjust == "raw"
        return [
            {"date": "2026-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10.1", "volume": "1000"},
            {"date": "2026-01-05", "open": "10.2", "high": "10.6", "low": "10.0", "close": "10.4", "volume": "1200"},
        ]

    monkeypatch.setattr(data_module, "fetch_adata_rows", fake_rows)
    monkeypatch.setattr(data_module, "fetch_baostock_rows", fake_rows)

    for provider in ("adata", "baostock"):
        asset = data_module.fetch_and_import_symbol(
            "600519",
            provider,
            market="china",
            asset_class="equity",
            venue="china",
            start_date="2026-01-02",
            end_date="2026-01-05",
            adjust="raw",
            overwrite=True,
        )
        assert asset["provider"] == provider
        assert asset["research_tables"]["daily_bars"] == 2

    with db_module.db() as connection:
        rows = connection.execute(
            """
            select source, count(*) as rows
            from ashare_daily_bars
            where symbol = '600519'
            group by source
            order by source
            """
        ).fetchall()
        market_rows = connection.execute(
            """
            select source, count(*) as rows
            from market_daily_bars
            where symbol = '600519' and asset_class = 'equity' and market = 'china'
            group by source
            order by source
            """
        ).fetchall()

    assert [(row["source"], row["rows"]) for row in rows] == [("adata", 2), ("baostock", 2)]
    assert [(row["source"], row["rows"]) for row in market_rows] == [("adata", 2), ("baostock", 2)]
