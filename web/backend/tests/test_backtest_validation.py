from app.services import backtest_validation


def test_research_backtest_records_but_does_not_enforce_production_reference_gate(monkeypatch):
    monkeypatch.setattr(
        backtest_validation,
        "data_coverage",
        lambda *args, **kwargs: {
            "bar_count": 2,
            "market_bar_count": 2,
            "status_count": 2,
            "last_date": "2024-01-03",
            "market_last_date": "2024-01-03",
        },
    )
    monkeypatch.setattr(
        backtest_validation,
        "latest_batch_for_symbol",
        lambda *args, **kwargs: {"id": "batch", "status": "success", "qa_report": {"passed": True}},
    )
    monkeypatch.setattr(
        backtest_validation,
        "quality_gate_range",
        lambda *args, **kwargs: {"passed": True, "severity": "ok"},
    )
    monkeypatch.setattr(
        backtest_validation,
        "end_coverage_status",
        lambda *args, **kwargs: {"passed": True},
    )
    from app.services import data_coverage as coverage_service

    monkeypatch.setattr(
        coverage_service,
        "ashare_coverage",
        lambda **kwargs: {
            "reference": {"passed": False, "severity": "critical", "issues": ["pit_missing"]}
        },
    )

    result = backtest_validation.build_backtest_validation(
        {
            "ticker": "510300",
            "benchmarkSymbol": "000300",
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "source": "tushare",
            "start": "2024-01-02",
            "end": "2024-01-03",
            "allowResearchSource": True,
        },
        {
            "datasetCertification": {"source": "tushare", "isCertified": False},
            "data": {
                "benchmark": {
                    "row_count": 2,
                    "first_date": "2024-01-02",
                    "last_date": "2024-01-03",
                }
            },
        },
    )

    reference_gate = next(gate for gate in result["gates"] if gate["name"] == "ashare_reference_coverage")
    assert result["passed"] is True
    assert reference_gate["passed"] is True
    assert reference_gate["details"]["enforced"] is False
    assert reference_gate["details"]["researchOnly"] is True
