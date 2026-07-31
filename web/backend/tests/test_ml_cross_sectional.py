from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from app.db import db, init_db
from app.ml.cross_sectional import (
    FEATURE_COLUMNS,
    add_forward_labels,
    assess_quality,
    build_price_features,
    build_walk_forward_plan,
    candidate_grid,
    prediction_metrics,
)
from app.ml.training import final_training_dates
from app.services import research_runs


def _weekdays(start: date, end: date) -> list[str]:
    values = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def test_walk_forward_plan_purges_and_freezes_final_year():
    plan = build_walk_forward_plan(_weekdays(date(2014, 1, 1), date(2025, 12, 31)))

    assert plan["purgeTradingDays"] == 5
    assert plan["embargoTradingDays"] == 5
    assert plan["holdout"]["start"].startswith("2024-12")
    assert plan["folds"]
    assert all(fold["testEnd"] < plan["holdout"]["start"] for fold in plan["folds"])


def test_final_holdout_training_purges_labels_and_caps_recent_history():
    dates = _weekdays(date(2019, 1, 1), date(2025, 12, 31))
    selected = final_training_dates(dates, purge_days=5)

    assert len(selected) == 252 * 5
    assert selected[-1] == dates[-6]


def test_price_features_and_label_use_next_open_not_signal_close():
    rows = []
    benchmark = []
    for index, day in enumerate(_weekdays(date(2024, 1, 1), date(2024, 4, 30))):
        rows.append({
            "symbol": "000001", "trade_date": day, "open": 10 + index,
            "high": 11 + index, "low": 9 + index, "close": 10.5 + index,
            "volume": 1000.0, "amount": 10000.0 + index, "adj_factor": 1.0,
            "turnover_rate": 1.0,
        })
        benchmark.append({"trade_date": day, "open": 100 + index, "close": 100.5 + index, "adj_factor": 1.0})
    frame = build_price_features(pl.DataFrame(rows))
    labelled = add_forward_labels(frame, pl.DataFrame(benchmark))
    first = labelled.row(0, named=True)
    expected = __import__("math").log((15.5) / 11.0) - __import__("math").log((105.5) / 101.0)

    assert len(FEATURE_COLUMNS) == 32
    assert abs(first["label_return"] - expected) < 1e-12
    assert first["relevance"] is None  # one security is below the 150-name daily contract


def test_cross_sectional_relevance_excludes_non_members_without_losing_price_history():
    dates = _weekdays(date(2024, 1, 1), date(2024, 1, 12))
    rows = []
    for symbol_index in range(300):
        for day_index, day in enumerate(dates):
            rows.append({
                "symbol": f"{symbol_index:06d}", "trade_date": day,
                "open": 10.0, "close": 10.0 + symbol_index / 1000 + day_index / 100,
                "adj_factor": 1.0, "is_member": symbol_index < 150,
            })
    benchmark = pl.DataFrame([
        {"trade_date": day, "open": 100.0, "close": 100.0, "adj_factor": 1.0}
        for day in dates
    ])
    labelled = add_forward_labels(pl.DataFrame(rows), benchmark, eligibility_column="is_member")
    first_day = labelled.filter(pl.col("trade_date") == dates[0])

    assert first_day.filter(pl.col("is_member"))["relevance"].value_counts().sort("relevance")["count"].to_list() == [30] * 5
    assert first_day.filter(~pl.col("is_member"))["relevance"].null_count() == 150


def test_prediction_metrics_and_quality_are_separate_from_technical_success():
    rows = []
    for day in ("2025-01-02", "2025-01-03"):
        for index in range(100):
            rows.append({"trade_date": day, "label_return": index / 1000, "score": float(index)})
    metrics = prediction_metrics(rows)
    quality = assess_quality(metrics, metrics)

    assert metrics["meanRankIc"] == 1.0
    assert metrics["q5MinusQ1"] > 0
    assert quality["advisory"] is True
    assert quality["qualified"] is False  # zero IC dispersion cannot establish ICIR
    assert len(candidate_grid()) == 8


def test_ml_research_run_is_queued_with_training_metadata():
    init_db()
    scope = {
        "asset": {"assetClass": "equity", "market": "china", "venue": "china", "resolution": "daily", "dataType": "trade"},
        "selection": {"type": "universe", "values": ["CSI300"]},
        "time": {"startDate": "2015-01-01", "endDate": "2025-12-31", "asOfDate": "2025-12-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }
    run = research_runs.create_run(
        template_key="ml-cross-sectional-ranker", name="ranker", scope=scope,
        parameters={"startDate": "2015-01-01", "endDate": "2025-12-31"},
    )

    assert run["status"] == "queued"
    assert run["mlResearch"]["stage"] == "queued"
    with db() as connection:
        tables = {row["name"] for row in connection.execute("select name from sqlite_master where type='table'").fetchall()}
    assert {"ml_feature_sets", "ml_training_runs", "ml_training_trials", "security_name_history", "industry_membership"} <= tables


def test_ml_research_rejects_scope_that_disagrees_with_fixed_contract():
    scope = {
        "asset": {"assetClass": "equity", "market": "china", "venue": "china", "resolution": "daily", "dataType": "trade"},
        "selection": {"type": "symbols", "values": ["000001"]},
        "time": {"startDate": "2015-01-01", "endDate": "2025-12-31", "asOfDate": "2025-12-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }

    with pytest.raises(ValueError, match="selection.type=universe"):
        research_runs.create_run(
            template_key="ml-cross-sectional-ranker", name="invalid", scope=scope,
            parameters={"startDate": "2015-01-01", "endDate": "2025-12-31"},
        )
