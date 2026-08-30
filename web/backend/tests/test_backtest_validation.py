import pytest

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


def test_ashare_rule_contract_covers_thirteen_execution_controls():
    rules = backtest_validation._ashare_market_rules(
        {
            "lotSize": 100,
            "commissionRate": 0.0001,
            "stampTaxSell": 0.0005,
            "slippageBps": 5,
            "adjust": "raw",
            "executionPolicy": "next_open",
            "allowStBuy": False,
        }
    )
    controls = {
        "t_plus_one": rules["tPlusOne"],
        "lot_size": rules["lotSize"] == 100,
        "suspension": rules["suspendedBlocked"],
        "st": rules["stBuyBlocked"],
        "limit_up": rules["limitUpBuyBlocked"],
        "limit_down": rules["limitDownSellBlocked"],
        "commission": rules["feeModel"]["commissionRate"] == 0.0001,
        "stamp_tax": rules["feeModel"]["stampTaxSell"] == 0.0005,
        "slippage": rules["slippageModel"]["slippageBps"] == 5,
        "adjustment": rules["adjustmentMode"] == "raw",
        "corporate_actions": rules["corporateActionsRequired"],
        "delisting": rules["delistedBlocked"],
        "next_open": rules["executionPolicy"] == "next_open",
    }

    assert len(controls) == 13
    assert all(controls.values())


@pytest.mark.parametrize(
    ("scenario", "expected_gate"),
    [
        ("missing_calendar", "ashare_reference_coverage"),
        ("missing_suspension", "ashare_reference_coverage"),
        ("missing_st", "ashare_reference_coverage"),
        ("missing_corporate_actions", "ashare_reference_coverage"),
        ("control_plane_parquet_mismatch", "production_source_certification"),
        ("derived_cache_stale", "production_source_certification"),
        ("timezone_cross_date", "ashare_timezone_consistency"),
    ],
)
def test_production_backtest_fails_closed_for_seven_constructed_gaps(
    monkeypatch,
    scenario,
    expected_gate,
):
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
        lambda *args, **kwargs: {
            "id": "batch",
            "status": "success",
            "qa_report": {"passed": True},
        },
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
    reference_issues = {
        "missing_calendar": ["trade_calendar_missing"],
        "missing_suspension": ["suspended_trade_status_missing"],
        "missing_st": ["security_master_st_missing"],
        "missing_corporate_actions": ["corporate_actions_missing"],
    }.get(scenario, [])
    from app.services import data_coverage as coverage_service

    monkeypatch.setattr(
        coverage_service,
        "ashare_coverage",
        lambda **kwargs: {
            "reference": {
                "passed": not reference_issues,
                "severity": "critical" if reference_issues else "ok",
                "issues": reference_issues,
            }
        },
    )
    certification = {
        "source": "tushare",
        "environment": "production",
        "isProduction": True,
        "isCertified": True,
        "qaStatus": "ok",
    }
    if scenario == "control_plane_parquet_mismatch":
        certification["qaStatus"] = "manifest_mismatch"
    elif scenario == "derived_cache_stale":
        certification["qaStatus"] = "stale"
    parameters = {
        "ticker": "600519",
        "benchmarkSymbol": "000300",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "source": "tushare",
        "start": "2024-01-02",
        "end": "2024-01-03",
        "marketTimezone": "UTC" if scenario == "timezone_cross_date" else "Asia/Shanghai",
    }
    result = backtest_validation.build_backtest_validation(
        parameters,
        {
            "datasetCertification": certification,
            "data": {
                "benchmark": {
                    "row_count": 2,
                    "first_date": "2024-01-02",
                    "last_date": "2024-01-03",
                }
            },
        },
    )

    assert result["passed"] is False
    gate = next(item for item in result["gates"] if item["name"] == expected_gate)
    assert gate["passed"] is False
