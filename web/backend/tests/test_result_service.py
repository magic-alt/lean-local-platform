import json

from app.services.result_service import parse_result_payload


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
