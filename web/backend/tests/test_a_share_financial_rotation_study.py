from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "examples" / "a_share_financial_rotation_tushare" / "a_share_financial_rotation_study.py"
SPEC = importlib.util.spec_from_file_location("a_share_financial_rotation_study", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
study = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = study
SPEC.loader.exec_module(study)


def test_normalize_index_daily_prefers_close_over_rounded_pct_change() -> None:
    raw = pd.DataFrame(
        {
            "trade_date": ["20260701", "20260702"],
            "close": [101.2345, 99.8765],
            "pre_close": [100.0, 101.2345],
            "pct_chg": [1.2345, -1.3415],
        }
    )

    normalized = study.normalize_index_daily(raw, "TEST.SH")

    assert normalized.loc[0, "ret"] == pytest.approx(0.012345)
    assert normalized.loc[1, "ret"] == pytest.approx(99.8765 / 101.2345 - 1.0)
    assert "return_diff_bps" in normalized


def test_compound_resample_labels_last_actual_observation() -> None:
    index = pd.to_datetime(["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"])
    panel = pd.DataFrame({"bank": [0.01, -0.02, 0.03, 0.01]}, index=index)
    panel.index.name = "trade_date"

    weekly = study.compound_resample(panel, "weekly")
    monthly = study.compound_resample(panel, "monthly")

    expected = np.prod(1.0 + panel["bank"]) - 1.0
    assert weekly.index[-1] == pd.Timestamp("2026-07-30")
    assert monthly.index[-1] == pd.Timestamp("2026-07-30")
    assert weekly.iloc[-1, 0] == pytest.approx(expected)
    assert monthly.iloc[-1, 0] == pytest.approx(expected)


def test_threshold_stats_separate_absolute_and_relative_defense() -> None:
    index = pd.bdate_range("2026-01-01", periods=40)
    market = pd.Series(np.tile([-0.02, 0.02], 20), index=index)
    financial = pd.Series(np.tile([-0.01, 0.01], 20), index=index)
    panel = pd.DataFrame({"bank": financial, "hs300": market})

    rows = study.compute_threshold_stats(panel, "bank", "hs300", "daily")
    zero = next(row for row in rows if row.threshold == "zero")

    assert zero.fin_up_when_market_down_rate == 0.0
    assert zero.fin_outperform_when_market_down_rate == 1.0
    assert zero.fin_down_when_market_up_rate == 0.0
    assert zero.fin_underperform_when_market_up_rate == 1.0


def test_sample_window_sensitivity_preserves_53_and_60_month_windows() -> None:
    index = pd.date_range("2021-08-31", periods=60, freq="ME")
    values = np.linspace(-0.03, 0.03, 60)
    panel = pd.DataFrame(
        {
            "sse": values,
            "hs300": values * 1.1,
            "chinext": values[::-1],
            "bank": values * 0.5,
            "insurance": values * 1.2,
        },
        index=index,
    )

    pair, rotation = study.build_sample_window_sensitivity(panel)

    assert set(pair.groupby("sample_window")["n_obs"].first()) == {53, 60}
    assert set(rotation.groupby("sample_window")["n_obs"].first()) == {53, 60}
