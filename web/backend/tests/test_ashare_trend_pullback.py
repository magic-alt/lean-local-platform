from __future__ import annotations

import gzip
import json
from datetime import date, timedelta
from pathlib import Path

import pytest


def _configure(tmp_path, monkeypatch):
    import app.db as db_module

    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db_module, "DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", True)
    db_module.init_db()
    return db_module


def _seed(db_module):
    dates = []
    current = date(2016, 1, 4)
    while len(dates) < 40:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    with db_module.db() as connection:
        connection.execute(
            """
            insert into securities
                (symbol,name,exchange,market,listed_date,status,is_st,created_at,updated_at)
            values ('000001','One','SZSE','china','2000-01-01','listed',0,'2016-01-01','2016-01-01')
            """
        )
        connection.executemany(
            "insert into trade_calendar(market,trade_date,is_open,source,batch_id) values ('china',?,1,'unit','batch')",
            [(value,) for value in dates],
        )
        connection.execute(
            """
            insert into industry_membership
                (id,symbol,industry_code,industry_name,taxonomy,level_no,in_date,out_date,source,payload_hash,created_at)
            values ('i1','000001','801010','Agriculture','SW2021',1,'2010-01-01',null,'unit','hash','2016-01-01')
            """
        )
        connection.executemany(
            """
            insert into ashare_daily_bars
                (symbol,trade_date,open,high,low,close,volume,amount,adj_factor,adjust,source,batch_id,created_at)
            values ('000001',?,10,11,9,10,1000000,60000000,1,'raw','unit','batch','2016-01-01')
            """,
            [(value,) for value in dates],
        )
        connection.executemany(
            """
            insert into adjustment_factors(symbol,trade_date,adj_factor,source,batch_id)
            values ('000001',?,1,'tushare','batch')
            """,
            [(value,) for value in dates],
        )
    return dates


def test_snapshot_is_deterministic_and_contains_pit_inputs(tmp_path, monkeypatch):
    db_module = _configure(tmp_path, monkeypatch)
    dates = _seed(db_module)
    from app.services.ashare_trend_pullback import write_trend_pullback_snapshot

    parameters = {
        "start": dates[20],
        "end": dates[-1],
        "source": "unit",
        "universeCode": "CSI300",
        "modelVariant": "B",
        "universeSchedule": json.dumps(
            [{"symbol": "000001", "startDate": dates[20], "endDate": None}]
        ),
        "fundamentalSchedule": "[]",
    }
    first = write_trend_pullback_snapshot(tmp_path / "run-one", parameters)
    second = write_trend_pullback_snapshot(tmp_path / "run-two", parameters)
    assert first["sha256"] == second["sha256"]
    assert first["coverage"]["industryCoverage"] == 1.0
    with gzip.open(first["path"], "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["schemaVersion"] == 1
    assert payload["rebalanceDates"]
    assert payload["factorChanges"]["000001"] == [{"date": dates[0], "value": 1.0}]
    assert payload["liquidityByRebalanceDate"]["000001"]


def test_snapshot_blocks_pre_2016_and_c_without_fundamentals(tmp_path, monkeypatch):
    db_module = _configure(tmp_path, monkeypatch)
    dates = _seed(db_module)
    from app.core.errors import LeanWebError
    from app.services.ashare_trend_pullback import build_trend_pullback_snapshot

    base = {
        "end": dates[-1],
        "source": "unit",
        "universeCode": "CSI300",
        "universeSchedule": json.dumps([{"symbol": "000001", "startDate": dates[0], "endDate": None}]),
        "fundamentalSchedule": "[]",
    }
    with pytest.raises(LeanWebError, match="2016-01-01"):
        build_trend_pullback_snapshot({**base, "start": "2015-01-01", "modelVariant": "A"})
    with pytest.raises(LeanWebError, match="pit_fundamentals_missing"):
        build_trend_pullback_snapshot({**base, "start": dates[20], "modelVariant": "C"})


def test_template_and_execution_contract_are_renderable():
    from app.services.ashare_execution import ASHARE_EXECUTION_HELPER_SOURCE
    from app.services.strategies import get_template, render_python_template

    template = get_template("ashare_trend_pullback_portfolio")
    assert template["tradable"] is True
    assert template["admissionEligible"] is True
    assert template["requiredResolution"] == "daily"
    assert "ashare_pit_input_snapshot" in template["requiredAdmissionGates"]
    code = render_python_template("TrendPullbackAlgorithm", template["key"])
    compile(code, "trend-pullback.py", "exec")
    compile(ASHARE_EXECUTION_HELPER_SOURCE, "ashare_execution.py", "exec")
    assert "target_percent_moo" in code
    assert "market_on_open_order" in ASHARE_EXECUTION_HELPER_SOURCE
    assert "limit_up_open" in ASHARE_EXECUTION_HELPER_SOURCE


def test_decision_report_extraction(tmp_path):
    from app.lean_engine.trend_pullback import extract_trend_pullback_report

    results = tmp_path / "results"
    results.mkdir()
    (results / "stdout.log").write_text(
        'LEAN_TREND_PULLBACK_SUMMARY|{"date":"2026-01-09","selected":["000001"]}\n'
        'LEAN_TREND_PULLBACK|{"date":"2026-01-09","symbol":"000001","score":0.8}\n',
        encoding="utf-8",
    )
    report = extract_trend_pullback_report(results)
    assert report is not None
    payload = json.loads(Path(report).read_text(encoding="utf-8"))
    assert payload["decisions"][0]["symbol"] == "000001"


def test_execution_validation_recognizes_next_open_and_t_plus_one(tmp_path):
    from app.services.backtest_execution_validation import audit_backtest_execution

    result = tmp_path / "run.json"
    result.write_text(
        json.dumps(
            {
                "statistics": {"End Equity": "100100", "Drawdown": "0.01"},
                "state": {},
                "charts": {
                    "Strategy Equity": {
                        "series": {"Equity": {"values": [[1704326400, 100100]]}}
                    }
                },
                "orders": {
                    "1": {
                        "id": 1,
                        "symbol": {"value": "000001"},
                        "tag": 'ASHARE_TREND|{"signalDate":"2024-01-03"}',
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "run-order-events.json").write_text(
        json.dumps(
            [
                {
                    "orderId": 1,
                    "status": "filled",
                    "symbolValue": "000001",
                    "fillQuantity": 100,
                    "fillPrice": 10,
                    "orderFeeAmount": 1,
                    "utcTime": "2024-01-04T01:30:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "stdout.log").write_text(
        "AShare execution account type: cash; short selling disabled.\n"
        "ASHARE_TREND_PULLBACK signal=close order=next_open variant=B snapshot=abc\n"
        "Debug: 2024-01-04 Algorithm Id: unit completed\n",
        encoding="utf-8",
    )
    validation = audit_backtest_execution(
        result,
        {
            "strategyTemplateKey": "ashare_trend_pullback_portfolio",
            "assetClass": "equity",
            "market": "china",
            "initialCash": 100000,
            "end": "2024-01-04",
        },
        {"data": {"endCoverage": {"actualLastDate": "2024-01-04"}}},
    )
    gates = {gate["name"]: gate for gate in validation["gates"]}
    assert gates["ashare_next_open_execution"]["passed"] is True
    assert gates["ashare_t_plus_one"]["passed"] is True
