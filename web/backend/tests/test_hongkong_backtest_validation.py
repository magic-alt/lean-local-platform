from app.services.backtest_validation import build_backtest_validation


def test_hongkong_validation_records_execution_rules(monkeypatch):
    import app.services.backtest_validation as validation

    monkeypatch.setattr(
        validation,
        "market_data_coverage",
        lambda *args, **kwargs: {"bar_count": 20, "first_date": "2024-01-02", "last_date": "2024-01-31"},
    )
    monkeypatch.setattr(
        validation,
        "end_coverage_status",
        lambda market, requested, actual: {"passed": bool(actual), "actualLastDate": actual},
    )
    parameters = {
        "ticker": "00700",
        "assetClass": "equity",
        "market": "hongkong",
        "venue": "hongkong",
        "start": "2024-01-02",
        "end": "2024-01-31",
        "source": "tushare",
        "benchmarkSymbol": "02800",
        "commissionRate": 0.0003,
        "minCommission": 3.0,
        "stampTaxBuy": 0.001,
        "stampTaxSell": 0.001,
        "sfcLevyRate": 0.000027,
        "afrcLevyRate": 0.0000015,
        "exchangeTradingFeeRate": 0.0000565,
        "settlementFeeRate": 0.000042,
        "feeScheduleVersion": "hkex-2026",
        "lotSize": 100,
        "slippageBps": 5.0,
    }
    fingerprint = {
        "data": {
            "benchmark": {
                "row_count": 20,
                "first_date": "2024-01-02",
                "last_date": "2024-01-31",
            }
        }
    }

    result = build_backtest_validation(parameters, fingerprint)

    assert result["passed"] is True
    assert result["marketRules"]["cashAccount"] is True
    assert result["marketRules"]["shortSellingAllowed"] is False
    assert result["marketRules"]["sameDaySellAllowed"] is True
    assert result["marketRules"]["lotSize"] == 100
    assert result["marketRules"]["feeModel"]["scheduleVersion"] == "hkex-2026"
