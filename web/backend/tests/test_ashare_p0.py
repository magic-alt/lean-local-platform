import json
import sys
import types
import zipfile
from datetime import datetime
from pathlib import Path

import pytest


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.domain.assets as assets_module
    import app.lean as lean_module

    data_dir = tmp_path / "Data"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(lean_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(lean_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(assets_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(assets_module, "REPO_ROOT", tmp_path)
    db_module.init_db()
    return data_dir


def sample_ashare_rows():
    return [
        {"date": "2024-01-02", "open": "10.00", "high": "10.20", "low": "9.90", "close": "10.00", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.50", "high": "11.00", "low": "10.50", "close": "11.00", "volume": "120000"},
        {"date": "2024-01-04", "open": "11.00", "high": "11.10", "low": "10.90", "close": "11.00", "volume": "0"},
    ]


def import_sample_ashare(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.benchmark import import_benchmark_rows
    from app.services.data import import_ashare_research_data

    asset = import_ashare_research_data(
        symbol="600519",
        provider="test",
        market="china",
        rows=sample_ashare_rows(),
        source="test",
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
    import_benchmark_rows(
        symbol="000300",
        source="test",
        rows=[
            {"date": "2024-01-02", "open": "3500", "high": "3510", "low": "3490", "close": "3505", "volume": "1000"},
            {"date": "2024-01-03", "open": "3506", "high": "3520", "low": "3500", "close": "3518", "volume": "1100"},
            {"date": "2024-01-04", "open": "3518", "high": "3530", "low": "3510", "close": "3522", "volume": "1200"},
        ],
    )
    return asset


def test_ashare_import_writes_research_tables_and_restores_asof_universe(tmp_path, monkeypatch):
    asset = import_sample_ashare(tmp_path, monkeypatch)

    from app.services.ashare_repository import is_tradeable, universe_as_of

    assert asset["batch_id"]
    assert asset["qa_report"]["passed"] is True
    assert Path(tmp_path / "Data" / "equity" / "china" / "daily" / "600519.zip").exists()
    universe = universe_as_of("ALL_A", "2024-01-04")
    assert [item["symbol"] for item in universe] == ["600519"]
    can_buy, reason = is_tradeable("600519", "2024-01-03", "buy")
    assert can_buy is False
    assert reason == "blocked_buy"
    can_sell, reason = is_tradeable("600519", "2024-01-04", "sell")
    assert can_sell is False
    assert reason == "suspended"


def test_incremental_ashare_import_rebuilds_lean_zip_from_full_database_history(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.data import import_ashare_research_data

    import_ashare_research_data(
        symbol="600519",
        provider="test",
        market="china",
        rows=[
            {
                "date": "2024-01-05",
                "open": "11.20",
                "high": "11.50",
                "low": "11.00",
                "close": "11.30",
                "volume": "130000",
            }
        ],
        source="test",
        overwrite=True,
        adjust="raw",
        outputsize="",
        asset_class="equity",
        venue="china",
        resolution="daily",
        data_type="trade",
        start_date="2024-01-05",
        end_date="2024-01-05",
    )

    zip_path = tmp_path / "Data" / "equity" / "china" / "daily" / "600519.zip"
    with zipfile.ZipFile(zip_path) as archive:
        lines = archive.read("600519.csv").decode("utf-8").splitlines()
    assert len(lines) == 4
    assert lines[0].startswith("20240102")
    assert lines[-1].startswith("20240105")

    from app.services.db_object_store import latest_object

    stored = latest_object("lean-data-files", "equity/china/daily/600519.zip")
    assert stored
    assert stored["sha256"]


def test_ashare_quality_report_blocks_duplicate_dates(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.data import import_ashare_research_data
    from app.services.data_quality import DataQualityError
    from app.services.ashare_repository import list_import_batches

    rows = sample_ashare_rows()
    rows.append({**rows[-1]})
    with pytest.raises(DataQualityError):
        import_ashare_research_data(
            symbol="600519",
            provider="test",
            market="china",
            rows=rows,
            source="test",
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

    latest = list_import_batches()[0]
    assert latest["status"] == "failed"
    assert latest["qa_report"]["passed"] is False
    assert "duplicate_dates" in ";".join(latest["qa_report"]["errors"])


def test_backtest_creation_injects_ashare_rules_after_preflight(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    import app.services.backtest_service as backtest_service
    import app.services.tasks as task_service

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
            "fast": 1,
            "slow": 2,
            "extra": {
                "maxPositionWeight": 0.2,
                "minCash": 1000,
                "blacklist": "000001,600000",
            },
        }
    )

    assert job["parameters"]["ashareRules"] is True
    assert job["parameters"]["lotSize"] == 100
    assert job["parameters"]["ashareStatusFile"] == "/Lean/Run/ashare_trade_status.json"
    assert job["parameters"]["benchmarkSymbol"] == "000300"
    assert job["parameters"]["benchmarkMarket"] == "china"
    assert job["parameters"]["executionPolicy"] == "next_open"
    assert job["parameters"]["maxPositionWeight"] == 0.2
    assert job["parameters"]["minCash"] == 1000.0
    assert job["parameters"]["cashBuffer"] == 1000.0
    assert job["parameters"]["blacklist"] == ["000001", "600000"]
    assert job["parameters"]["constraintVersion"] == 1
    assert job["fingerprint"]["parameters_sha256"]
    assert "git_commit" in job["fingerprint"]
    assert job["fingerprint"]["benchmark_rows"] == 3
    assert job["fingerprint"]["lean_zip_sha256"]
    assert job["fingerprint"]["factor_file_sha256"]


def test_backtest_preflight_counts_distinct_bar_dates_across_sources(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.data import import_ashare_research_data

    import_ashare_research_data(
        symbol="600519",
        provider="sina",
        market="china",
        rows=sample_ashare_rows(),
        source="sina",
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

    import app.services.backtest_service as backtest_service
    import app.services.tasks as task_service

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
        }
    )

    assert job["status"] == "created"


def test_backtest_preflight_falls_back_when_trade_calendar_missing_but_bars_exist(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    import app.db as db_module
    import app.services.backtest_service as backtest_service
    import app.services.tasks as task_service

    with db_module.db() as connection:
        connection.execute("delete from trade_calendar where market = 'china'")

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
        }
    )

    assert job["status"] == "created"


def test_backtest_creation_allows_missing_local_ashare_cache_for_worker_restore(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    zip_path = tmp_path / "Data" / "equity" / "china" / "daily" / "600519.zip"
    zip_path.unlink()

    import app.services.backtest_service as backtest_service
    import app.services.tasks as task_service

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
        }
    )

    assert job["status"] == "created"


def test_backtest_creation_blocks_missing_benchmark(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    import app.services.backtest_service as backtest_service
    from app.lean import LeanPlatformError

    with pytest.raises(LeanPlatformError, match="benchmark_missing:999999"):
        backtest_service.create_backtest_job(
            {
                "symbol": "600519",
                "assetClass": "equity",
                "market": "china",
                "start": "2024-01-02",
                "end": "2024-01-04",
                "cash": 100000,
                "parameters": {"benchmarkSymbol": "999999"},
            }
        )


def test_backtest_creation_blocks_critical_quality_report(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    import app.db as db_module
    import app.services.backtest_service as backtest_service
    from app.lean import LeanPlatformError

    with db_module.db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id, report_type, asset_class, market, symbol, start_date, end_date,
                 sources_json, severity, result_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qa-critical-1",
                "ashare_daily_multisource",
                "equity",
                "china",
                "600519",
                "2024-01-03",
                "2024-01-03",
                json.dumps(["unit"]),
                "critical",
                json.dumps({"issue": "price_mismatch"}),
                "now",
            ),
        )

    with pytest.raises(LeanPlatformError, match="qa_failed:qa-critical-1"):
        backtest_service.create_backtest_job(
            {
                "symbol": "600519",
                "assetClass": "equity",
                "market": "china",
                "start": "2024-01-02",
                "end": "2024-01-04",
                "cash": 100000,
            }
        )


def test_benchmark_rows_import_to_market_bars_and_lean_cache(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.services.benchmark import import_benchmark_rows
    from app.services.market_data import query_database_bars

    result = import_benchmark_rows(
        symbol="000300",
        source="akshare",
        rows=[
            {"date": "2024-01-02", "open": "3500", "high": "3510", "low": "3490", "close": "3505", "volume": "1000"},
            {"date": "2024-01-03", "open": "3506", "high": "3520", "low": "3500", "close": "3518", "volume": "1100"},
        ],
    )

    assert result["symbol"] == "000300"
    assert result["rows"] == 2
    bars = query_database_bars(symbol="000300", venue="china", start_date="2024-01-02", end_date="2024-01-03")
    assert bars["count"] == 2
    assert (tmp_path / "Data" / "equity" / "china" / "daily" / "000300.zip").exists()


def test_run_fingerprint_includes_git_parameters_data_and_cache(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.lean_cache import ensure_ashare_lean_cache
    from app.services.run_fingerprint import build_run_fingerprint

    parameters = {
        "ticker": "600519",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2024-01-02",
        "end": "2024-01-04",
        "adjust": "raw",
        "source": "test",
    }
    cache = ensure_ashare_lean_cache("600519", source="test", adjust="raw")
    fingerprint = build_run_fingerprint(
        run_id="run-1",
        parameters=parameters,
        docker_image="quantconnect/lean:latest",
        lean_cache=cache,
    )

    assert fingerprint["parametersHash"]
    assert fingerprint["parameters_sha256"] == fingerprint["parametersHash"]
    assert "git_commit" in fingerprint
    assert "git_dirty" in fingerprint
    assert fingerprint["strategy_file_sha256"] is None
    assert fingerprint["data"]["marketDailyBars"]["row_count"] == 3
    assert fingerprint["market_daily_bars_count"] == 3
    assert fingerprint["trade_status_count"] == 3
    assert fingerprint["leanCache"]["files"]["daily"]["sha256"]
    assert fingerprint["lean_zip_sha256"]
    assert fingerprint["factor_file_sha256"]
    assert fingerprint["docker_image"] == "quantconnect/lean:latest"
    assert "docker_image_digest" in fingerprint
    assert fingerprint["python_version"]
    assert fingerprint["requirements_hash"]


def test_lean_cache_restores_missing_zip_from_stored_object(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.lean_cache import ensure_ashare_lean_cache

    zip_path = tmp_path / "Data" / "equity" / "china" / "daily" / "600519.zip"
    original = zip_path.read_bytes()
    zip_path.unlink()

    cache = ensure_ashare_lean_cache("600519", source="test", adjust="raw")

    assert zip_path.exists()
    assert zip_path.read_bytes() == original
    assert cache["files"]["daily"]["object_id"]


def test_ashare_execution_artifacts_include_status_payload(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.ashare_execution import write_ashare_execution_artifacts

    artifacts = write_ashare_execution_artifacts(
        tmp_path / "runs" / "job-1",
        {
            "ashareRules": True,
            "ticker": "600519",
            "start": "2024-01-02",
            "end": "2024-01-04",
        },
    )

    assert artifacts is not None
    status_path = Path(artifacts["status"])
    helper_path = Path(artifacts["helper"])
    assert "AShareExecutionHelper" in helper_path.read_text(encoding="utf-8")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["600519"]["2024-01-03"]["can_buy"] is False


def test_security_master_restores_history_and_filters_new_and_delisted(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.services.ashare_repository import import_security_master, is_tradeable, tradable_universe_as_of, universe_as_of

    import_security_master(
        [
            {"symbol": "600001", "name": "Old Listed", "listed_date": "2020-01-01", "status": "listed"},
            {"symbol": "000002", "name": "Delisted Later", "listed_date": "2024-01-03", "delisted_date": "2024-01-05"},
            {"symbol": "300001", "name": "New Listed", "listed_date": "2024-01-04", "status": "listed"},
            {"symbol": "600999", "name": "ST Name", "listed_date": "2020-01-01", "status": "listed", "is_st": True},
        ],
        source="unit",
    )

    assert [item["symbol"] for item in universe_as_of("ALL_A", "2024-01-02")] == ["600001", "600999"]
    assert [item["symbol"] for item in universe_as_of("ALL_A", "2024-01-04")] == ["000002", "300001", "600001", "600999"]
    assert [item["symbol"] for item in universe_as_of("ALL_A", "2024-01-05")] == ["300001", "600001", "600999"]

    tradable = tradable_universe_as_of("ALL_A", "2024-01-04", min_listed_days=2, exclude_st=True)
    assert [item["symbol"] for item in tradable] == ["600001"]
    tradable = tradable_universe_as_of("ALL_A", "2024-01-04", min_listed_days=0, exclude_st=True)
    assert [item["symbol"] for item in tradable] == ["000002", "300001", "600001"]

    can_trade, reason = is_tradeable("000002", "2024-01-02", "buy")
    assert can_trade is False
    assert reason == "not_listed"
    can_trade, reason = is_tradeable("000002", "2024-01-05", "sell")
    assert can_trade is False
    assert reason == "delisted"


def test_official_trade_status_overrides_inferred_rules_and_missing_status_rejects(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.services.ashare_repository import import_security_master, import_trade_status, is_tradeable, trade_status_as_of, upsert_trade_status

    import_security_master(
        [{"symbol": "600001", "name": "Official Status", "listed_date": "2020-01-01", "status": "listed"}],
        source="unit",
    )
    import_trade_status(
        [
            {
                "symbol": "600001",
                "tradeDate": "2024-01-02",
                "limitUp": 11.0,
                "limitDown": 9.0,
                "isLimitUp": True,
                "canBuy": False,
                "canSell": True,
            },
            {
                "symbol": "600001",
                "tradeDate": "2024-01-03",
                "isSuspended": True,
                "canBuy": False,
                "canSell": False,
            },
        ],
        source="official-unit",
    )

    status = trade_status_as_of(["600001"], "2024-01-02")["600001"]
    assert status["limit_up"] == 11.0
    assert status["can_buy"] is False
    upsert_trade_status(
        [
            {
                "symbol": "600001",
                "trade_date": "2024-01-02",
                "is_suspended": False,
                "is_limit_up": False,
                "can_buy": True,
                "can_sell": True,
            }
        ],
        source="unit:ohlcv_inferred",
        batch_id="inferred-batch",
    )
    status = trade_status_as_of(["600001"], "2024-01-02")["600001"]
    assert status["can_buy"] is False
    assert status["source"] == "official-unit"
    can_buy, reason = is_tradeable("600001", "2024-01-02", "buy")
    assert can_buy is False
    assert reason == "blocked_buy"
    can_sell, reason = is_tradeable("600001", "2024-01-03", "sell")
    assert can_sell is False
    assert reason == "suspended"
    can_buy, reason = is_tradeable("600001", "2024-01-04", "buy")
    assert can_buy is False
    assert reason == "trade_status_missing"


def test_adjustment_factors_write_factor_file_and_corporate_actions(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.services.ashare_repository import (
        corporate_actions,
        import_adjustment_factors,
        import_security_master,
        upsert_corporate_actions,
    )

    import_security_master(
        [{"symbol": "600001", "name": "Adjusted", "listed_date": "2020-01-01", "status": "listed"}],
        source="unit",
    )
    result = import_adjustment_factors(
        [
            {"symbol": "600001", "tradeDate": "2024-01-02", "adjFactor": 1.0},
            {"symbol": "600001", "tradeDate": "2024-01-03", "adjFactor": 1.2},
        ],
        source="unit",
    )

    assert result["factorFiles"]["600001"]["rows"] == 3
    factor_file = tmp_path / "Data" / "equity" / "china" / "factor_files" / "600001.csv"
    text = factor_file.read_text(encoding="utf-8")
    assert "20240102,0.8333333333,1,0" in text
    assert "20501231,1.0000000000,1,0" in text

    upsert_corporate_actions(
        [
            {
                "symbol": "600001",
                "exDate": "2024-01-03",
                "actionType": "dividend",
                "cashDividend": 1.0,
                "stockDividend": 0.1,
            }
        ],
        source="unit",
    )
    actions = corporate_actions("600001", "2024-01-01", "2024-01-31")
    assert len(actions) == 1
    assert actions[0]["cash_dividend"] == 1.0


def test_ashare_execution_helper_blocks_limits_suspend_tplus1_and_rounds_lots(tmp_path, monkeypatch):
    from app.services.ashare_execution import ASHARE_EXECUTION_HELPER_SOURCE

    algorithm_imports = types.ModuleType("AlgorithmImports")

    class FeeModel:
        pass

    class CashAmount:
        def __init__(self, amount, currency):
            self.amount = amount
            self.currency = currency

    class OrderFee:
        def __init__(self, cash_amount):
            self.cash_amount = cash_amount

    class ConstantSlippageModel:
        def __init__(self, value):
            self.value = value

    algorithm_imports.FeeModel = FeeModel
    algorithm_imports.CashAmount = CashAmount
    algorithm_imports.OrderFee = OrderFee
    algorithm_imports.ConstantSlippageModel = ConstantSlippageModel
    monkeypatch.setitem(sys.modules, "AlgorithmImports", algorithm_imports)

    namespace: dict[str, object] = {}
    exec(ASHARE_EXECUTION_HELPER_SOURCE, namespace)
    helper_class = namespace["AShareExecutionHelper"]

    status_path = tmp_path / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "600001": {
                    "2024-01-02": {"is_suspended": False, "is_limit_up": True, "can_buy": False, "can_sell": True},
                    "2024-01-03": {"is_suspended": False, "is_limit_up": False, "can_buy": True, "can_sell": True},
                    "2024-01-04": {"is_suspended": False, "can_buy": True, "can_sell": True},
                    "2024-01-05": {"is_suspended": False, "is_limit_down": True, "can_buy": True, "can_sell": False},
                    "2024-01-06": {"is_suspended": True, "can_buy": False, "can_sell": False},
                }
            }
        ),
        encoding="utf-8",
    )

    class Security:
        price = 10.0

    class Holding:
        quantity = 0

    class Portfolio(dict):
        cash = 50000.0
        total_portfolio_value = 50000.0

    class FakeAlgorithm:
        def __init__(self):
            self.time = datetime(2024, 1, 2)
            self.securities = {"600001": Security()}
            self.portfolio = Portfolio({"600001": Holding()})
            self.orders = []
            self.messages = []

        def get_parameter(self, key, default=None):
            return default

        def market_order(self, symbol, quantity):
            self.orders.append((symbol, quantity))
            self.portfolio[symbol].quantity += quantity
            return {"symbol": symbol, "quantity": quantity}

        def debug(self, message):
            self.messages.append(message)

    algo = FakeAlgorithm()
    helper = helper_class(algo, str(status_path))

    assert helper.target_percent("600001", 1) is None
    assert algo.orders == []

    algo.time = datetime(2024, 1, 3)
    helper.target_percent("600001", 1)
    assert algo.orders
    assert algo.orders[-1][1] % 100 == 0
    assert algo.orders[-1][1] > 0

    algo.time = datetime(2024, 1, 4)
    fill_event = types.SimpleNamespace(status="filled", fill_quantity=algo.orders[-1][1], symbol="600001")
    helper.on_order_event(fill_event)
    assert helper.exit("600001") is None
    algo.time = datetime(2024, 1, 5)
    assert helper.exit("600001") is None
    algo.time = datetime(2024, 1, 6)
    algo.portfolio["600001"].quantity = 0
    assert helper.target_percent("600001", 1) is None
