import json
import math
from datetime import datetime, timezone

import pytest


def ts(value: str) -> float:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def test_parse_result_payload_adds_performance_analytics(tmp_path):
    from app.services.result_service import parse_result_payload

    result_path = tmp_path / "result.json"
    payload = {
        "statistics": {
            "Compounding Annual Return": "12%",
            "Drawdown": "3%",
            "Total Orders": "2",
        },
        "charts": {
            "Strategy Equity": {
                "series": {
                    "Equity": {
                        "values": [
                            [ts("2024-01-02T00:00:00"), 100000, 100000, 100000, 100000],
                            [ts("2024-01-31T00:00:00"), 105000, 105000, 105000, 105000],
                            [ts("2024-02-29T00:00:00"), 110000, 110000, 110000, 110000],
                        ]
                    }
                }
            },
            "Benchmark": {"series": {"Benchmark": {"values": [[ts("2024-01-02T00:00:00"), 100], [ts("2024-02-29T00:00:00"), 104]]}}},
            "Drawdown": {"series": {"Equity Drawdown": {"values": [[ts("2024-02-01T00:00:00"), -3.0]]}}},
        },
        "profitLoss": {"2024-02-29T00:00:00Z": 9000},
        "orderEvents": [
            {
                "status": "filled",
                "symbolValue": "600519",
                "time": ts("2024-01-10T00:00:00"),
                "fillQuantity": 100,
                "fillPrice": 100,
                "orderFeeAmount": 10,
            },
            {
                "status": "filled",
                "symbolValue": "600519",
                "time": ts("2024-02-10T00:00:00"),
                "fillQuantity": -100,
                "fillPrice": 110,
                "orderFeeAmount": 10,
            },
        ],
        "orders": {},
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    parsed = parse_result_payload(result_path, None, {"symbol": "600519", "parameters": {"market": "china"}})

    performance = parsed["performance"]
    assert parsed["statistics"]["Calmar Ratio"] == "4.000"
    assert performance["monthly_returns"][0]["period"] == "2024-01"
    assert performance["yearly_returns"][0]["return"] == pytest.approx(0.1)
    assert performance["trade_pnl_summary"]["count"] == 1
    assert performance["trade_pnl"][0]["holding_days"] == 31
    assert round(performance["excess_return"], 6) == 0.06
    assert parsed["summary_metrics"]["Benchmark Return"] == pytest.approx(0.04)
    assert parsed["summary_metrics"]["Excess Return"] == pytest.approx(0.06)
    assert parsed["summary_metrics"]["Benchmark Metric Status"] == "insufficient_aligned_points_for_alpha_beta"


def test_parse_result_payload_replaces_constant_benchmark_from_cache(tmp_path, monkeypatch):
    import app.lean_engine.results as results_module
    from app.services.result_service import parse_result_payload

    result_path = tmp_path / "result.json"
    payload = {
        "statistics": {"Total Orders": "1"},
        "charts": {
            "Strategy Equity": {
                "series": {
                    "Equity": {
                        "values": [
                            [ts("2024-01-02T00:00:00"), 100000, 100000, 100000, 100000],
                            [ts("2024-01-03T00:00:00"), 101000, 101000, 101000, 101000],
                            [ts("2024-01-04T00:00:00"), 102000, 102000, 102000, 102000],
                        ]
                    }
                }
            },
            "Benchmark": {
                "series": {
                    "Benchmark": {
                        "values": [
                            [ts("2024-01-02T00:00:00"), 3431.11],
                            [ts("2024-01-03T00:00:00"), 3431.11],
                            [ts("2024-01-04T00:00:00"), 3431.11],
                        ]
                    }
                }
            },
        },
        "orders": {},
    }
    result_path.write_text(json.dumps(payload), encoding="utf-8")

    def fake_price_series(symbol, *args, **kwargs):
        if symbol == "000300":
            return [
                {"time": "2024-01-02T00:00:00+00:00", "value": 100.0},
                {"time": "2024-01-03T00:00:00+00:00", "value": 102.0},
                {"time": "2024-01-04T00:00:00+00:00", "value": 104.0},
            ]
        return []

    monkeypatch.setattr(results_module, "read_lean_daily_price_series", fake_price_series)

    parsed = parse_result_payload(
        result_path,
        None,
        {
            "symbol": "600519",
            "parameters": {
                "market": "china",
                "benchmarkMarket": "china",
                "benchmarkSymbol": "000300",
                "start": "2024-01-02",
                "end": "2024-01-04",
            },
        },
    )

    assert parsed["charts"]["benchmark"][-1]["value"] == 104.0
    assert parsed["summary_metrics"]["Benchmark Return"] == pytest.approx(0.04)
    assert parsed["summary_metrics"]["Benchmark Metric Status"] == "benchmark_return_available_from_lean_data_cache"


def test_performance_analytics_recomputes_sharpe_and_flags_short_window():
    from app.analyzers.performance_analyzer import performance_analytics

    chart_data = {
        "series": {
            "equity": [
                {"time": "2024-01-02T04:00:00+00:00", "value": 100.0},
                {"time": "2024-01-02T07:00:00+00:00", "value": 101.0},
                {"time": "2024-01-03T07:00:00+00:00", "value": 103.0},
                {"time": "2024-01-04T07:00:00+00:00", "value": 102.0},
                {"time": "2024-01-05T07:00:00+00:00", "value": 106.0},
            ],
            "price": [
                {"time": "2024-01-02T21:00:00+00:00", "value": 10.0},
                {"time": "2024-01-03T21:00:00+00:00", "value": 10.2},
                {"time": "2024-01-04T21:00:00+00:00", "value": 10.1},
                {"time": "2024-01-05T21:00:00+00:00", "value": 10.5},
            ],
            "benchmark": [],
        },
        "seriesSources": {},
    }
    returns = [103 / 101 - 1.0, 102 / 103 - 1.0, 106 / 102 - 1.0]
    mean = sum(returns) / len(returns)
    volatility = math.sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))

    performance = performance_analytics({"Sharpe Ratio": "24.827"}, chart_data, [], {})

    assert performance["sharpe_recomputed_from_equity"] == pytest.approx(mean / volatility * math.sqrt(252))
    assert performance["sharpe_recomputed_sample_count"] == 3
    assert performance["sharpe_recomputed_date_points"] == 4
    assert performance["sharpe_recomputed_calendar_source"] == "price_series"
    assert performance["short_window_unstable"] is True
    assert performance["sharpe_recompute_status"] == "computed_with_warnings"
    assert "short_window_unstable" in performance["sharpe_metric_warnings"]
    assert "lean_sharpe_diverges_from_equity_recompute" in performance["sharpe_metric_warnings"]


def test_performance_analytics_handles_zero_volatility_without_misleading_sharpe():
    from app.analyzers.performance_analyzer import performance_analytics

    chart_data = {
        "series": {
            "equity": [
                {"time": "2024-01-02T07:00:00+00:00", "value": 100.0},
                {"time": "2024-01-03T07:00:00+00:00", "value": 101.0},
                {"time": "2024-01-04T07:00:00+00:00", "value": 102.01},
            ],
            "price": [],
            "benchmark": [],
        },
        "seriesSources": {},
    }

    performance = performance_analytics({"Sharpe Ratio": "1.0"}, chart_data, [], {})

    assert performance["sharpe_recomputed_from_equity"] is None
    assert performance["sharpe_recompute_status"] == "zero_return_volatility"
    assert performance["sharpe_recomputed_sample_count"] == 2
