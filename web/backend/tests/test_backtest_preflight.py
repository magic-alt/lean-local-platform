from app.services.backtest_preflight import prepare_backtest_request


def test_preflight_repairs_symbol_and_benchmark_with_selected_source(monkeypatch):
    import app.services.backtest_preflight as preflight

    ready = {"600460": False, "000300": False}
    repaired = []

    monkeypatch.setattr(
        preflight,
        "_source",
        lambda request, parameters: ("tushare", {"source": "tushare"}),
    )
    monkeypatch.setattr(
        preflight,
        "_coverage",
        lambda symbol, parameters, source: {
            "symbol": symbol,
            "source": source,
            "rows": 10 if ready[symbol] else 0,
            "statusRows": 0,
            "firstDate": "2024-01-02" if ready[symbol] else None,
            "lastDate": "2024-01-04" if ready[symbol] else None,
        },
    )

    def target_gate(parameters, source):
        if not ready["600460"]:
            raise RuntimeError("target missing")

    def benchmark_gate(parameters, source):
        if not ready["000300"]:
            raise RuntimeError("benchmark missing")

    def repair(symbol, parameters, source, role):
        assert source == "tushare"
        assert role in {"symbol", "benchmark"}
        ready[symbol] = True
        repaired.append(symbol)
        return {"rows": 10, "first_date": "2024-01-02", "last_date": "2024-01-04", "batch_id": symbol}

    monkeypatch.setattr(preflight, "_target_gate", target_gate)
    monkeypatch.setattr(preflight, "_benchmark_gate", benchmark_gate)
    monkeypatch.setattr(preflight, "_repair_symbol", repair)
    monkeypatch.setattr(preflight, "quality_gate_range", lambda symbol, start, end: {"passed": True, "blockingReports": []})

    result = prepare_backtest_request(
        {
            "symbol": "600460",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 800000,
            "source": "tushare",
            "parameters": {"benchmarkSymbol": "000300"},
        }
    )

    assert repaired == ["600460", "000300"]
    assert result["parameters"]["source"] == "tushare"
    assert result["preflight"]["ready"] is True
    assert result["preflight"]["repaired"] == ["symbol", "benchmark"]


def test_tushare_benchmark_repair_uses_explicit_index_endpoint(monkeypatch):
    import app.services.benchmark as benchmark
    import app.services.tushare_adapter as tushare_adapter

    calls = []

    class FakeAdapter:
        def index_daily_rows(self, symbol, start_date, end_date):
            calls.append((symbol, start_date, end_date))
            return [{"date": "2024-01-02", "open": 3500, "high": 3510, "low": 3490, "close": 3505, "volume": 1}]

    monkeypatch.setattr(tushare_adapter, "TushareAdapter", FakeAdapter)
    monkeypatch.setattr(
        benchmark,
        "import_benchmark_rows",
        lambda **kwargs: {"rows": len(kwargs["rows"]), "source": kwargs["source"], "symbol": kwargs["symbol"]},
    )

    result = benchmark.fetch_and_import_benchmark(
        "000300",
        "tushare",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )

    assert calls == [("000300", "2024-01-01", "2024-01-31")]
    assert result == {"rows": 1, "source": "tushare", "symbol": "000300"}


def test_hongkong_preflight_uses_tushare_and_market_rules(monkeypatch):
    import app.services.backtest_preflight as preflight

    monkeypatch.setattr(preflight, "_source", lambda request, parameters: ("tushare", {"source": "tushare"}))
    monkeypatch.setattr(
        preflight,
        "_coverage",
        lambda symbol, parameters, source: {
            "symbol": symbol,
            "source": source,
            "rows": 20,
            "statusRows": 0,
            "firstDate": "2024-01-02",
            "lastDate": "2024-01-31",
        },
    )
    monkeypatch.setattr(preflight, "_target_gate", lambda parameters, source: None)
    monkeypatch.setattr(preflight, "_benchmark_gate", lambda parameters, source: None)
    monkeypatch.setattr(preflight, "get_instrument", lambda *args, **kwargs: {"lot_size": 100})

    result = prepare_backtest_request(
        {
            "symbol": "00700",
            "assetClass": "equity",
            "market": "hongkong",
            "start": "2024-01-02",
            "end": "2024-01-31",
            "cash": 500000,
            "source": "tushare",
        },
        repair=False,
    )

    parameters = result["parameters"]
    assert parameters["hkRules"] is True
    assert parameters["benchmarkSymbol"] == "02800"
    assert parameters["commissionRate"] == 0.0003
    assert parameters["minCommission"] == 3.0
    assert parameters["lotSize"] == 100
    assert parameters["nextOpenGapBufferBps"] == 2000.0
    assert result["preflight"]["effectiveSource"] == "tushare"
