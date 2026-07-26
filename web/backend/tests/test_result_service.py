import json

import pytest

from app.services.result_service import parse_result_payload, persist_result


def test_extract_chart_data_includes_candles_volume_and_strategy_indicators(tmp_path, monkeypatch):
    import app.lean_engine.results as results_module

    result_json = tmp_path / "chart.json"
    result_json.write_text(
        json.dumps(
            {
                "charts": {
                    "Strategy Equity": {"series": {"Equity": {"values": [[1704153600, 100000]]}}},
                    "RSI": {"series": {"RSI": {"values": [[1704153600, 28.5]]}}},
                    "EMA": {
                        "series": {
                            "Fast": {"values": [[1704153600, 10.2]]},
                            "Slow": {"values": [[1704153600, 10.0]]},
                        }
                    },
                },
                "orders": {
                    "1": {
                        "quantity": 100,
                        "lastFillTime": "2024-01-02T07:00:00Z",
                        "symbol": {"value": "600460"},
                        "price": 10.15,
                        "status": 3,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        results_module,
        "read_lean_daily_candle_series",
        lambda *args, **kwargs: [
            {
                "time": "2024-01-02T21:00:00+00:00",
                "open": 10.0,
                "high": 10.3,
                "low": 9.9,
                "close": 10.2,
                "volume": 123456,
            }
        ],
    )

    chart = results_module.extract_chart_data(
        result_json,
        symbol="600460",
        market="china",
        start="2024-01-02",
        end="2024-01-02",
    )

    assert chart["candles"][0]["volume"] == 123456
    assert chart["series"]["price"] == [{"time": "2024-01-02T21:00:00+00:00", "value": 10.2}]
    assert {(item["chart"], item["name"]) for item in chart["indicators"]} == {
        ("EMA", "Fast"),
        ("EMA", "Slow"),
        ("RSI", "RSI"),
    }
    assert chart["orderMarkers"][0]["priceValue"] == 10.15


def test_extract_chart_data_rebases_equity_and_benchmark_for_comparison(tmp_path, monkeypatch):
    import app.lean_engine.results as results_module

    result_json = tmp_path / "comparison.json"
    result_json.write_text(
        json.dumps(
            {
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[1704153600, 100000], [1704240000, 110000]]}
                        }
                    },
                    "Benchmark": {
                        "series": {
                            "Benchmark": {"values": [[1704153600, 500], [1704240000, 525]]}
                        }
                    },
                },
                "orders": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(results_module, "read_lean_daily_candle_series", lambda *args, **kwargs: [])

    chart = results_module.extract_chart_data(result_json, benchmark_symbol="SPY")

    assert [point["value"] for point in chart["series"]["cumulativeReturn"]] == pytest.approx([0.0, 0.1])
    assert [point["value"] for point in chart["series"]["benchmarkReturn"]] == pytest.approx([0.0, 0.05])
    assert chart["seriesSources"]["benchmarkStatus"] == "available"
    assert chart["metadata"]["comparisonBasis"] == "cumulative_return"


def test_extract_chart_data_does_not_plot_zero_only_benchmark(tmp_path, monkeypatch):
    import app.lean_engine.results as results_module

    result_json = tmp_path / "missing-benchmark.json"
    result_json.write_text(
        json.dumps(
            {
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[1704153600, 100000], [1704240000, 101000]]}
                        }
                    },
                    "Benchmark": {
                        "series": {
                            "Benchmark": {"values": [[1704153600, 0], [1704240000, 0]]}
                        }
                    },
                },
                "orders": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(results_module, "read_lean_daily_candle_series", lambda *args, **kwargs: [])
    monkeypatch.setattr(results_module, "read_lean_daily_price_series", lambda *args, **kwargs: [])

    chart = results_module.extract_chart_data(result_json, benchmark_symbol="SPY")

    assert chart["series"]["benchmarkReturn"] == []
    assert chart["seriesSources"]["benchmarkStatus"] == "unavailable"


def test_parse_result_payload_extracts_core_sections(tmp_path):
    result_json = tmp_path / "job.json"
    result_json.write_text(
        json.dumps(
            {
                "statistics": {
                    "Net Profit": "12.3%",
                    "Sharpe Ratio": "1.42",
                    "Total Orders": "2",
                },
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[0, 100000], [86400, 101000]]},
                            "Return": {"values": [[0, 0], [86400, 0.01]]},
                        }
                    },
                    "Drawdown": {
                        "series": {
                            "Equity Drawdown": {"values": [[0, 0], [86400, -0.02]]}
                        }
                    },
                },
                "orders": {
                    "1": {
                        "quantity": 10,
                        "lastFillTime": "1970-01-01T00:00:00+00:00",
                        "symbol": {"value": "SPY"},
                        "price": 100,
                        "tag": "entry",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = parse_result_payload(result_json, run={"parameters": {}})

    assert payload["summary_metrics"]["Net Profit"] == "12.3%"
    assert payload["statistics"]["Sharpe Ratio"] == "1.42"
    assert payload["summary_metrics"]["Sharpe Sample Count"] == 1
    assert payload["summary_metrics"]["Short Window Unstable"] is True
    assert payload["performance"]["sharpe_recompute_status"] == "insufficient_return_points"
    assert len(payload["equity_curve"]) == 2
    assert len(payload["drawdown_curve"]) == 2
    assert payload["orders"][0]["symbol"] == "SPY"


def test_parse_result_payload_filters_unfilled_orders(tmp_path):
    result_json = tmp_path / "job-filter.json"
    result_json.write_text(
        json.dumps(
            {
                "statistics": {
                    "Net Profit": "12.3%",
                    "Sharpe Ratio": "1.42",
                    "Total Orders": "3",
                },
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[0, 100000], [86400, 101000]]},
                            "Return": {"values": [[0, 0], [86400, 0.01]]},
                        }
                    },
                    "Drawdown": {
                        "series": {
                            "Equity Drawdown": {"values": [[0, 0], [86400, -0.02]]}
                        }
                    },
                },
                "orders": {
                    "1": {"quantity": 10, "lastFillTime": "1970-01-01T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 100, "tag": "filled", "status": 3},
                    "2": {"quantity": 10, "time": "1970-01-02T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 0, "tag": "rejected", "status": 7},
                    "3": {"quantity": -10, "time": "1970-01-03T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 101, "tag": "filled", "status": "filled"},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = parse_result_payload(result_json, run={"parameters": {}})

    assert payload["summary_metrics"]["Net Profit"] == "12.3%"
    assert len(payload["orders"]) == 2
    assert [order["status"] for order in payload["orders"]] == [3, "filled"]
    assert all(order["status"] not in {7, "invalid", "submitted", "rejected"} for order in payload["orders"])


def test_parse_result_payload_filters_string_status_codes(tmp_path):
    result_json = tmp_path / "job-filter-status.json"
    result_json.write_text(
        json.dumps(
            {
                "statistics": {
                    "Net Profit": "4%",
                    "Sharpe Ratio": "0.9",
                    "Total Orders": "3",
                },
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[0, 100000], [86400, 101000]]},
                            "Return": {"values": [[0, 0], [86400, 0.01]]},
                        }
                    },
                    "Drawdown": {
                        "series": {
                            "Equity Drawdown": {"values": [[0, 0], [86400, -0.02]]}
                        }
                    },
                },
                "orders": {
                    "1": {"quantity": 8, "time": "1970-01-01T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 100, "status": "3"},
                    "2": {"quantity": 8, "time": "1970-01-02T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 101, "status": "7"},
                    "3": {"quantity": -8, "time": "1970-01-03T00:00:00+00:00", "symbol": {"value": "SPY"}, "price": 102, "status": "3"},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = parse_result_payload(result_json, run={"parameters": {}})

    assert payload["summary_metrics"]["Net Profit"] == "4%"
    assert len(payload["orders"]) == 2
    assert payload["orders"][0]["status"] == 3
    assert payload["orders"][1]["status"] == 3


def test_parse_result_payload_infers_holdings_from_filled_orders(tmp_path):
    result_json = tmp_path / "job-holdings.json"
    result_json.write_text(
        json.dumps(
            {
                "statistics": {
                    "Net Profit": "10%",
                    "Sharpe Ratio": "1.0",
                    "Total Orders": "3",
                },
                "charts": {
                    "Strategy Equity": {
                        "series": {
                            "Equity": {"values": [[0, 100000], [86400, 101000]]},
                            "Return": {"values": [[0, 0], [86400, 0.01]]},
                        }
                    },
                    "Drawdown": {"series": {"Equity Drawdown": {"values": [[0, 0], [86400, -0.02]]}},
                    },
                },
                "orders": {
                    "1": {
                        "quantity": 10,
                        "lastFillTime": "1970-01-01T00:00:00+00:00",
                        "symbol": {"value": "SPY"},
                        "price": 100,
                        "tag": "",
                        "status": 3,
                    },
                    "2": {
                        "quantity": -4,
                        "time": "1970-01-02T00:00:00+00:00",
                        "symbol": {"value": "SPY"},
                        "price": 101,
                        "tag": "",
                        "status": 3,
                    },
                    "3": {
                        "quantity": 4,
                        "lastFillTime": "1970-01-03T00:00:00+00:00",
                        "symbol": {"value": "SPY"},
                        "price": 102,
                        "tag": "",
                        "status": 3,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    payload = parse_result_payload(result_json, run={"parameters": {"start": "1970-01-01", "end": "1970-01-02"}})
    holdings = payload["holdings"]

    assert holdings and len(holdings) == 1
    holding = holdings[0]
    assert holding["symbol"] == "SPY"
    assert holding["quantity"] == 10  # 10 in - 4 + 4
    assert round(holding["averagePrice"], 6) == 100.8


def test_persist_result_archives_raw_lean_artifacts(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    result_json = tmp_path / "job-1.json"
    summary_json = tmp_path / "job-1-summary.json"
    result_json.write_text(
        json.dumps(
            {
                "statistics": {"Net Profit": "1%"},
                "charts": {
                    "Strategy Equity": {
                        "series": {"Equity": {"values": [[0, 100000], [86400, 101000]]}}
                    }
                },
                "orders": {},
            }
        ),
        encoding="utf-8",
    )
    summary_json.write_text(json.dumps({"statistics": {"Sharpe Ratio": "1.0"}}), encoding="utf-8")
    (tmp_path / "job-1-order-events.json").write_text("[]", encoding="utf-8")
    (tmp_path / "job-1-log.txt").write_text("lean log", encoding="utf-8")
    (tmp_path / "stdout.log").write_text("docker stdout", encoding="utf-8")
    (tmp_path / "artifact-manifest.json").write_text("{}", encoding="utf-8")
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    (work_dir / "config.json").write_text("{}", encoding="utf-8")

    saved = persist_result(
        "job-1",
        result_json,
        summary_json,
        {
            "results_dir": str(tmp_path),
            "work_dir": str(work_dir),
            "parameters": {},
            "validation": {"passed": True, "severity": "ok"},
            "experiment": {"runId": "job-1", "parameters": {"sha256": "abc"}},
        },
    )

    assert saved["raw_result_object_id"]
    assert saved["summary_object_id"]
    assert saved["performance"]["validation"]["passed"] is True
    assert saved["performance"]["experiment"]["runId"] == "job-1"
    artifact_objects = saved["performance"]["artifact_objects"]
    assert {item["kind"] for item in artifact_objects} >= {
        "lean-result",
        "lean-summary",
        "lean-order-events",
        "lean-log",
        "lean-stdout",
        "artifact-manifest",
        "lean-config",
    }
    with db_module.db() as connection:
        rows = connection.execute(
            "select object_key from stored_objects where namespace = ? order by object_key",
            ("backtest-results",),
        ).fetchall()
    keys = {row["object_key"] for row in db_module.rows_to_dicts(rows)}
    assert "job-1/artifacts/job-1-order-events.json" in keys
    assert "job-1/artifacts/stdout.log" in keys
    assert "job-1/artifacts/artifact-manifest.json" in keys
    assert "job-1/artifacts/config.json" in keys
