import json

from app.services.result_service import parse_result_payload, persist_result


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
