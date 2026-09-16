from __future__ import annotations

import ast
import json

import pytest

from app.services import etf_rotation_certification_campaign as campaign
from app.services import strategies
from app.services.etf_rotation_execution_attribution import build_execution_attribution


def _campaign_config() -> dict:
    return {
        "projectId": "etf-project",
        "dataReleaseId": "ds_real_pinned_001",
        "symbols": ["SPY", "QQQ", "IWM"],
        "start": "2020-01-02",
        "end": "2024-12-31",
        "cash": 100000,
        "parameters": {
            "lookback": 63,
            "rebalanceDays": 21,
            "selectionCount": 2,
            "volatilityLookback": 60,
            "targetVolatility": 0.1,
            "maxWeight": 0.6,
            "maxTurnover": 0.25,
            "commissionPerOrder": 1.0,
            "slippageBps": 2.0,
            "costModelId": "lean-constant-fee-slippage-v1",
        },
        "walkForward": {
            "universeVersion": "us-etf-core-v1",
            "adjustmentContract": "lean-adjusted-v1",
            "featurePipelineVersion": "etf-rotation-v2",
            "trainYears": 2,
            "testYears": 1,
            "validationMonths": 6,
        },
    }


def test_campaign_freezes_explicit_release_and_never_selects_latest(monkeypatch):
    monkeypatch.setattr(
        campaign,
        "get_project",
        lambda project_id: {
            "id": project_id,
            "config": {
                "templateKey": "etf_rotation",
                "market": "usa",
                "parameters": {},
            },
        },
    )
    monkeypatch.setattr(
        campaign,
        "get_data_release",
        lambda release_id: {
            "id": release_id,
            "status": "active",
            "market": "usa",
            "coverage_start": "2019-01-01",
            "coverage_end": "2025-12-31",
        },
    )
    frozen = campaign._normalize_config(_campaign_config())
    assert frozen["dataReleaseId"] == "ds_real_pinned_001"
    assert frozen["parameters"]["dataReleaseId"] == "ds_real_pinned_001"
    assert frozen["symbols"] == ["SPY", "QQQ", "IWM"]

    invalid = _campaign_config()
    invalid.pop("dataReleaseId")
    with pytest.raises(ValueError, match="dataReleaseId is required"):
        campaign._normalize_config(invalid)


def test_campaign_rejects_non_etf_project_and_non_us_release(monkeypatch):
    config = _campaign_config()
    monkeypatch.setattr(
        campaign,
        "get_project",
        lambda _project_id: {"config": {"templateKey": "buy_hold", "market": "usa"}},
    )
    with pytest.raises(ValueError, match="templateKey=etf_rotation"):
        campaign._normalize_config(config)

    monkeypatch.setattr(
        campaign,
        "get_project",
        lambda project_id: {
            "id": project_id,
            "config": {"templateKey": "etf_rotation", "market": "usa", "parameters": {}},
        },
    )
    monkeypatch.setattr(
        campaign,
        "get_data_release",
        lambda release_id: {
            "id": release_id,
            "status": "active",
            "market": "china",
            "coverage_start": "2019-01-01",
            "coverage_end": "2025-12-31",
        },
    )
    with pytest.raises(ValueError, match="requires a USA DataRelease"):
        campaign._normalize_config(config)


def test_static_equal_weight_baseline_is_independent_lean_template():
    rendered = strategies.render_python_template(
        "EtfCertificationStaticBaseline",
        "etf_static_equal_weight",
    )
    ast.parse(rendered)
    assert "DataNormalizationMode.ADJUSTED" in rendered
    assert "ConstantFeeModel" in rendered
    assert "ConstantSlippageModel" in rendered
    assert "etf_static_equal_weight_initial_allocation" in rendered
    assert 'self.plot("Baseline", "GrossExposure", 1.0)' in rendered
    manifest = strategies.get_template("etf_static_equal_weight")
    assert manifest["markets"] == ["usa"]
    assert manifest["certification"]["role"] == "static_equal_weight_baseline"


def test_execution_attribution_uses_real_result_observables(tmp_path):
    raw_path = tmp_path / "result.json"
    raw_path.write_text(
        json.dumps(
            {
                "Charts": {
                    "Rotation": {
                        "Series": {
                            "GrossExposure": {
                                "Values": [
                                    {"x": 1, "y": 0.8},
                                    {"x": 2, "y": 0.6},
                                ]
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    run = {
        "parameters": {
            "initialCash": 100000,
            "slippageBps": 2.0,
        }
    }
    result = {
        "summary_metrics": {},
        "statistics": {
            "Sharpe Ratio": "1.25",
            "Drawdown": "12.00%",
            "Portfolio Turnover": "35.00%",
            "Total Trades": "7",
            "Total Fees": "$12.50",
            "Estimated Strategy Capacity": "$2,000,000",
        },
        "performance": {},
        "orders": [
            {
                "status": "filled",
                "quantity": 100,
                "fillPrice": 100,
            }
        ],
        "trades": [],
        "drawdown_curve": [],
        "raw_result_path": str(raw_path),
    }
    built = build_execution_attribution(run, result)
    assert built["complete"] is True
    assert built["metrics"] == {
        "sharpe": pytest.approx(1.25),
        "maxDrawdown": pytest.approx(0.12),
        "turnover": pytest.approx(0.35),
        "tradeCount": 7,
    }
    attribution = built["executionAttribution"]
    assert attribution["fees"] == pytest.approx(12.5)
    assert attribution["slippage"] == pytest.approx(2.0)
    assert attribution["cashDrag"] == pytest.approx(0.3)
    assert attribution["capacityImpact"] == pytest.approx(0.05)
    assert attribution["complete"] is True


def test_execution_attribution_fails_closed_when_capacity_is_missing(tmp_path):
    raw_path = tmp_path / "result.json"
    raw_path.write_text(
        json.dumps(
            {
                "Charts": {
                    "Rotation": {
                        "Series": {
                            "GrossExposure": {"Values": [{"x": 1, "y": 0.9}]}
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    built = build_execution_attribution(
        {"parameters": {"initialCash": 100000, "slippageBps": 2.0}},
        {
            "statistics": {
                "Sharpe Ratio": "1.0",
                "Drawdown": "10%",
                "Portfolio Turnover": "20%",
                "Total Trades": "3",
                "Total Fees": "$3",
            },
            "summary_metrics": {},
            "performance": {},
            "orders": [{"status": "filled", "quantity": 10, "fillPrice": 100}],
            "raw_result_path": str(raw_path),
        },
    )
    assert built["complete"] is False
    assert built["executionAttribution"]["capacityImpact"] is None
    assert built["executionAttribution"]["complete"] is False
