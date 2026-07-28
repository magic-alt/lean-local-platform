import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

if os.environ.get("RUN_LEAN_DOCKER_INTEGRATION") != "1":
    pytest.skip("Set RUN_LEAN_DOCKER_INTEGRATION=1 to run Docker LEAN integration tests.", allow_module_level=True)


def _configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.domain.assets as assets_module
    import app.lean as lean_module

    data_dir = tmp_path / "Data"
    runtime_dir = tmp_path / "runtime"
    monkeypatch.setattr(db_module, "DB_PATH", runtime_dir / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(db_module, "RUNS_DIR", runtime_dir / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", runtime_dir / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", runtime_dir / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", runtime_dir / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", runtime_dir / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", runtime_dir / "reports")
    monkeypatch.setattr(lean_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(lean_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lean_module, "OBJECT_STORE_DIR", runtime_dir / "object-store")
    monkeypatch.setattr(assets_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(assets_module, "REPO_ROOT", tmp_path)
    db_module.init_db()
    return data_dir, runtime_dir


def _ts_date(value):
    return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()


def test_real_lean_blocks_ashare_limit_suspend_and_tplus1(tmp_path, monkeypatch):
    _configure_temp_platform(tmp_path, monkeypatch)

    from app.runners.lean_runner import LeanRunner
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10.00", "high": "10.00", "low": "10.00", "close": "10.00", "volume": "100000", "isLimitUp": True, "canBuy": False},
        {"date": "2024-01-03", "open": "10.20", "high": "10.60", "low": "10.10", "close": "10.50", "volume": "100000", "canBuy": True, "canSell": True},
        {"date": "2024-01-04", "open": "10.60", "high": "10.80", "low": "10.50", "close": "10.60", "volume": "100000", "canBuy": True, "canSell": True},
        {"date": "2024-01-05", "open": "10.00", "high": "10.00", "low": "10.00", "close": "10.00", "volume": "100000", "isLimitDown": True, "canBuy": True, "canSell": False},
        {"date": "2024-01-08", "open": "10.30", "high": "10.40", "low": "10.10", "close": "10.30", "volume": "100000", "canBuy": True, "canSell": True},
        {"date": "2024-01-09", "open": "10.20", "high": "10.30", "low": "10.00", "close": "10.20", "volume": "100000", "canBuy": True, "canSell": True},
        {"date": "2024-01-10", "open": "10.10", "high": "10.20", "low": "10.00", "close": "10.10", "volume": "100000", "isSuspended": True, "canBuy": False, "canSell": False},
    ]
    import_ashare_research_data(
        symbol="600001",
        provider="unit",
        market="china",
        rows=rows,
        source="unit-official",
        overwrite=True,
        adjust="raw",
        outputsize="",
        asset_class="equity",
        venue="china",
        resolution="daily",
        data_type="trade",
        start_date=None,
        end_date=None,
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text(
        """
from AlgorithmImports import *
from datetime import datetime
from ashare_execution import AShareExecutionHelper, apply_ashare_models


class P0IntegrationAlgorithm(QCAlgorithm):
    def initialize(self):
        Market.Add("china", 101)
        self.set_start_date(2024, 1, 2)
        self.set_end_date(2024, 1, 10)
        self.set_account_currency("CNY")
        self.set_cash(100000)
        self.set_brokerage_model(BrokerageName.DEFAULT, AccountType.CASH)
        equity = self.add_equity("600001", Resolution.DAILY, "china", data_normalization_mode=DataNormalizationMode.RAW)
        self.symbol = equity.symbol
        self.set_benchmark(lambda time: 1)
        apply_ashare_models(self, equity)
        self.helper = AShareExecutionHelper(self, self.get_parameter("ashareStatusFile", "/Lean/Run/ashare_trade_status.json"))

    def on_data(self, data):
        if not data.contains_key(self.symbol):
            return
        bar = data[self.symbol]
        if bool(getattr(bar, "is_fill_forward", getattr(bar, "IsFillForward", False))):
            return
        day = self.time.strftime("%Y-%m-%d")
        if day == "2024-01-02":
            self.helper.target_percent(self.symbol, 1)
        elif day == "2024-01-03":
            self.helper.target_percent(self.symbol, 1)
        elif day == "2024-01-04":
            self.helper.exit(self.symbol)
        elif day == "2024-01-05":
            self.helper.exit(self.symbol)
        elif day == "2024-01-08":
            self.helper.exit(self.symbol)
        elif day == "2024-01-10":
            self.helper.target_percent(self.symbol, 1)

    def on_order_event(self, order_event):
        self.helper.on_order_event(order_event)
        self.debug(str(order_event))
""",
        encoding="utf-8",
    )

    run_dir = tmp_path / "runtime" / "runs" / "p0-lean-integration"
    parameters = {
        "ticker": "600001",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2024-01-02",
        "end": "2024-01-10",
        "cash": 100000,
        "ashareRules": True,
        "ashareStatusFile": "/Lean/Run/ashare_trade_status.json",
        "lotSize": 100,
        "commissionRate": 0.0001,
        "minCommission": 5.0,
        "stampTaxSell": 0.0005,
        "transferFeeRate": 0.00001,
        "slippageBps": 0.0,
        "initialCash": 100000,
        "initial_cash": 100000,
    }
    output_lines = []
    output = LeanRunner(timeout_seconds=120).run_backtest(
        "p0-lean-integration",
        parameters,
        run_dir,
        output_callback=output_lines.append,
        algorithm_path=project_dir / "main.py",
        algorithm_class="P0IntegrationAlgorithm",
        language="Python",
        project_dir=project_dir,
    )

    assert output["exit_code"] == 0
    assert output["result_json_path"]

    order_events_path = Path(output["results_dir"]) / "p0-lean-integration-order-events.json"
    events = json.loads(order_events_path.read_text(encoding="utf-8"))
    if isinstance(events, dict):
        events = list(events.values())
    filled = [event for event in events if str(event.get("status")).lower() == "filled"]
    assert [event["direction"] for event in filled] == ["buy", "sell"]
    assert _ts_date(filled[0]["time"]) == "2024-01-04"
    assert _ts_date(filled[1]["time"]) == "2024-01-09"

    log_text = (run_dir / "results" / "log.txt").read_text(encoding="utf-8", errors="replace")
    assert "AShare buy blocked 600001 limit_up_or_blocked" in log_text
    assert "AShare sell blocked 600001 t_plus_1" in log_text
    assert "AShare sell blocked 600001 limit_down_or_blocked" in log_text
    assert "AShare buy blocked 600001 suspended" in log_text


def test_real_lean_runs_index_screening_and_writes_report_artifacts(tmp_path, monkeypatch):
    _configure_temp_platform(tmp_path, monkeypatch)

    from app.runners.lean_runner import LeanRunner
    from app.services.data import import_ashare_research_data
    from app.services.strategies import render_python_template

    def daily_rows(symbol: str):
        rows = []
        cursor = date(2024, 1, 2)
        index = 0
        while cursor <= date(2024, 6, 28):
            if cursor.weekday() < 5:
                if symbol == "600001":
                    close = 10.0 + index * 0.08
                elif symbol == "000001":
                    close = 12.0 - index * 0.015
                else:
                    close = 3500.0 + index * 1.5
                rows.append(
                    {
                        "date": cursor.isoformat(),
                        "open": f"{close * 0.998:.4f}",
                        "high": f"{close * 1.01:.4f}",
                        "low": f"{close * 0.99:.4f}",
                        "close": f"{close:.4f}",
                        "volume": "1000000",
                        "canBuy": True,
                        "canSell": True,
                    }
                )
                index += 1
            cursor += timedelta(days=1)
        return rows

    for symbol in ("000001", "600001", "000300"):
        import_ashare_research_data(
            symbol=symbol,
            provider="unit",
            market="china",
            rows=daily_rows(symbol),
            source="unit-official",
            overwrite=True,
            adjust="raw",
            outputsize="",
            asset_class="equity",
            venue="china",
            resolution="daily",
            data_type="trade",
            start_date=None,
            end_date=None,
        )

    project_dir = tmp_path / "screening-project"
    project_dir.mkdir()
    (project_dir / "main.py").write_text(
        render_python_template("AshareIndexScreeningIntegrationAlgorithm", "ashare_index_screening"),
        encoding="utf-8",
    )
    universe_schedule = [
        {"symbol": "000001", "startDate": "2024-01-02", "endDate": None, "weight": 0.5},
        {"symbol": "600001", "startDate": "2024-01-02", "endDate": None, "weight": 0.5},
    ]
    fundamental_schedule = [
        {
            "symbol": "000001",
            "effectiveDate": "2024-01-02",
            "metrics": {"roe": 0.03, "revenueGrowth": -0.05, "debtRatio": 0.82, "pe": 80.0},
        },
        {
            "symbol": "600001",
            "effectiveDate": "2024-01-02",
            "metrics": {"roe": 0.22, "revenueGrowth": 0.18, "debtRatio": 0.35, "pe": 20.0},
        },
    ]
    run_dir = tmp_path / "runtime" / "runs" / "screening-lean-integration"
    parameters = {
        "ticker": "000001",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2024-01-02",
        "end": "2024-06-28",
        "cash": 1_000_000,
        "initialCash": 1_000_000,
        "initial_cash": 1_000_000,
        "benchmarkSymbol": "000300",
        "universeCode": "CSI300",
        "universeSymbols": ["000001", "600001"],
        "universeSchedule": json.dumps(universe_schedule, separators=(",", ":")),
        "fundamentalSchedule": json.dumps(fundamental_schedule, separators=(",", ":")),
        "fastPeriod": 20,
        "slowPeriod": 60,
        "rsiPeriod": 14,
        "topN": 1,
        "technicalThreshold": 70,
        "fundamentalThreshold": 60,
        "minFundamentalFields": 2,
        "ashareRules": True,
        "ashareStatusFile": "/Lean/Run/ashare_trade_status.json",
        "commissionRate": 0.0001,
        "minCommission": 5.0,
        "stampTaxSell": 0.0005,
        "transferFeeRate": 0.00001,
        "slippageBps": 0.0,
    }

    output = LeanRunner(timeout_seconds=180).run_backtest(
        "screening-lean-integration",
        parameters,
        run_dir,
        output_callback=lambda _line: None,
        algorithm_path=project_dir / "main.py",
        algorithm_class="AshareIndexScreeningIntegrationAlgorithm",
        language="Python",
        project_dir=project_dir,
    )

    assert output["exit_code"] == 0
    assert output["result_json_path"]
    assert output["report_html_path"]
    screening_path = Path(output["results_dir"]) / "screening-report.json"
    screening = json.loads(screening_path.read_text(encoding="utf-8"))
    by_symbol = {item["symbol"]: item for item in screening["items"]}
    assert by_symbol["600001"]["trend"] == "持续上涨"
    assert by_symbol["600001"]["suitableToBuy"] is True
    assert by_symbol["000001"]["suitableToBuy"] is False
    assert screening["summary"]["selected"] == ["600001"]
    assert screening["summary"]["asOfDate"] == "2024-06-28"
    assert screening["summary"]["tradeSimulation"] is False
    events_path = Path(output["results_dir"]) / "screening-lean-integration-order-events.json"
    events = json.loads(events_path.read_text(encoding="utf-8")) if events_path.exists() else []
    if isinstance(events, dict):
        events = list(events.values())
    filled = [
        event for event in events
        if str(event.get("status")).lower() == "filled"
    ]
    assert filled == []
    assert "指数成分股技术面与基本面筛选" in Path(output["report_html_path"]).read_text(encoding="utf-8")
