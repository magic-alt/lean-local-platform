import pytest

from app.research.factor_pipeline import (
    construct_factor_portfolio,
    factor_templates,
    process_factor_rows,
)


def test_factor_pipeline_normalizes_and_neutralizes_group_and_size():
    rows = [
        {"symbol": "A", "value": 1, "industry": "bank", "size": 1},
        {"symbol": "B", "value": 3, "industry": "bank", "size": 2},
        {"symbol": "C", "value": 2, "industry": "tech", "size": 1},
        {"symbol": "D", "value": 6, "industry": "tech", "size": 2},
    ]

    result = process_factor_rows(
        rows,
        normalization="zscore",
        neutralize_groups=["industry"],
        neutralize_exposures=["size"],
    )

    assert result["count"] == 4
    assert sum(item["score"] for item in result["items"]) == pytest.approx(0)
    assert factor_templates()["robustness"]["cost_stress_grid"]["values"][-1] == 2.0


def test_long_short_portfolio_respects_gross_net_and_caps():
    result = construct_factor_portfolio(
        [{"symbol": chr(65 + index), "score": float(6 - index)} for index in range(6)],
        method="long_short",
        top_n=2,
        bottom_n=2,
        gross_exposure=1,
        net_exposure=0,
        max_weight=0.3,
    )

    assert result["grossExposure"] == pytest.approx(1)
    assert result["netExposure"] == pytest.approx(0)
    assert max(abs(value) for value in result["weights"].values()) <= 0.3
