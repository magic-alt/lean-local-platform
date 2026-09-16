from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.services import strategies
from app.services.etf_rotation_certification import (
    build_certification_report,
    run_regression_matrix,
    static_equal_weight_baseline,
    trading_session_due_indexes,
    validate_parameters,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = REPO_ROOT / "strategies" / "templates" / "etf_rotation"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "etf_rotation_certification.v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _row(matrix: dict, scenario_id: str) -> dict:
    return next(row["result"] for row in matrix["rows"] if row["id"] == scenario_id)


def test_etf_rotation_manifest_has_strict_certification_schema():
    manifest = json.loads((TEMPLATE_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 2
    assert manifest["markets"] == ["usa"]
    definitions = {item["key"]: item for item in manifest["parameters"]}
    for key in (
        "selectionCount",
        "volatilityLookback",
        "targetVolatility",
        "maxWeight",
        "maxTurnover",
        "commissionPerOrder",
        "slippageBps",
        "costModelId",
    ):
        assert key in definitions
        assert definitions[key]["required"] is True
    for key in (
        "selectionCount",
        "volatilityLookback",
        "targetVolatility",
        "maxWeight",
        "maxTurnover",
    ):
        assert "min" in definitions[key]
        assert "max" in definitions[key]
    assert manifest["minimumData"]["normalization"] == "adjusted"
    assert manifest["costModel"]["pnlAdjustmentInStrategy"] is False
    assert manifest["certification"]["deterministicTieBreak"] == (
        "momentum_desc_then_ticker_asc"
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("lookback", 1),
        ("rebalanceDays", 0),
        ("selectionCount", 0),
        ("volatilityLookback", 253),
        ("targetVolatility", float("nan")),
        ("maxWeight", 1.1),
        ("maxTurnover", 0.0),
        ("commissionPerOrder", -1),
        ("slippageBps", 101),
    ],
)
def test_etf_rotation_parameter_ranges_fail_closed(key, value):
    parameters = _fixture()["parameters"]
    with pytest.raises(ValueError):
        validate_parameters({**parameters, key: value}, symbol_count=3)


def test_etf_rotation_selection_count_cannot_exceed_universe():
    parameters = _fixture()["parameters"]
    with pytest.raises(ValueError, match="exceeds symbol count"):
        validate_parameters({**parameters, "selectionCount": 4}, symbol_count=3)


def test_etf_rotation_template_renders_deterministically():
    first = strategies.render_python_template(
        "EtfRotationCertifiedAlgorithm",
        "etf_rotation",
    )
    second = strategies.render_python_template(
        "EtfRotationCertifiedAlgorithm",
        "etf_rotation",
    )
    assert first == second
    ast.parse(first)
    assert "ConstantFeeModel" in first
    assert "ConstantSlippageModel" in first
    assert "DataNormalizationMode.ADJUSTED" in first
    assert "_sessions_since_rebalance" in first
    assert "momentum, annualized_volatility" in first
    assert "requested_turnover > self.max_turnover" in first
    assert "ETF_ROTATION_SUMMARY" in first
    assert "portfolio.cash -=" not in first


def test_etf_rotation_regression_matrix_is_deterministic_and_covers_edge_cases():
    fixture = _fixture()
    first = run_regression_matrix(fixture)
    second = run_regression_matrix(fixture)
    assert first == second
    assert first["fingerprint"] == second["fingerprint"]

    tie = _row(first, "deterministic_tie_break")
    assert tie["selected"] == ["QQQ", "SPY"]
    assert tie["appliedTurnover"] == pytest.approx(0.25)

    zero_vol = _row(first, "zero_volatility_exclusion")
    assert zero_vol["exclusions"]["SPY"] == "invalid_or_zero_volatility"

    missing = _row(first, "insufficient_history_exclusion")
    assert missing["exclusions"]["QQQ"] == "insufficient_momentum_history"

    risk_off = _row(first, "zero_candidate_risk_off")
    assert risk_off["selected"] == []
    assert risk_off["failureReasons"] == ["zero_eligible_candidates"]
    assert risk_off["appliedTurnover"] == pytest.approx(0.25)
    assert risk_off["grossExposure"] == pytest.approx(0.30)

    suspension = _row(first, "suspension_preserves_frozen_weight")
    assert suspension["exclusions"]["SPY"] == "not_tradable"
    assert suspension["targets"]["SPY"] == pytest.approx(0.40)
    assert suspension["grossExposure"] <= 1.0 + 1e-12

    corporate_action = _row(first, "adjusted_corporate_action_boundary")
    assert corporate_action["failureReasons"] == []


def test_rebalance_clock_counts_fresh_trading_sessions_not_calendar_days():
    fixture = _fixture()["tradingCalendarFixture"]
    assert trading_session_due_indexes(
        fixture["freshSessionFlags"],
        rebalance_days=fixture["rebalanceDays"],
    ) == fixture["expectedDueIndexes"]


def test_static_weight_baseline_is_deterministic():
    first = static_equal_weight_baseline(
        ["SPY", "QQQ", "IWM"],
        current_weights={},
        max_turnover=1.0,
    )
    second = static_equal_weight_baseline(
        ["IWM", "SPY", "QQQ"],
        current_weights={},
        max_turnover=1.0,
    )
    assert first == second
    assert first["selected"] == ["IWM", "QQQ", "SPY"]
    assert sum(first["targets"].values()) == pytest.approx(1.0)


def test_certification_report_emits_metrics_and_machine_readable_failures():
    fixture = _fixture()["certificationFixture"]
    report = build_certification_report(
        candidate=fixture["candidate"],
        baseline=fixture["baseline"],
        gates=fixture["gates"],
        deterministic_fingerprints=fixture["deterministicFingerprints"],
    )
    assert report["passed"] is True
    assert report["failureReasons"] == []
    assert set(report["candidate"]["metrics"]) == {
        "sharpe",
        "maxDrawdown",
        "turnover",
        "tradeCount",
    }

    failed = build_certification_report(
        candidate=fixture["candidate"],
        baseline=fixture["baseline"],
        gates={**fixture["gates"], "minimumSharpe": 2.0},
        deterministic_fingerprints=["run-a", "run-b"],
    )
    assert failed["passed"] is False
    assert "deterministic_rerun_match" in failed["failureReasons"]
    assert "minimum_sharpe" in failed["failureReasons"]
