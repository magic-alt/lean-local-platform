import json
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
