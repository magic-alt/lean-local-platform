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
