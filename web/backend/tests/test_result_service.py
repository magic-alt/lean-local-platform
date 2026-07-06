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
    assert len(payload["equity_curve"]) == 2
    assert len(payload["drawdown_curve"]) == 2
    assert payload["orders"][0]["symbol"] == "SPY"


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
    assert "job-1/artifacts/artifact-manifest.json" in keys
    assert "job-1/artifacts/config.json" in keys
