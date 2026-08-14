from pathlib import Path


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.domain.assets as assets_module
    import app.lean as lean_module
    import app.services.csi300_data_pipeline as pipeline_module

    data_dir = tmp_path / "Data"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(pipeline_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(lean_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(lean_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(assets_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(assets_module, "REPO_ROOT", tmp_path)
    db_module.init_db()
    return data_dir


class FakeCsi300Adapter:
    def trade_calendar(self, start_date, end_date, exchange="SSE"):
        return [
            {"trade_date": "2024-01-02", "is_open": True},
            {"trade_date": "2024-01-03", "is_open": True},
            {"trade_date": "2024-01-04", "is_open": True},
        ]

    def index_weight_rows(self, index_code, start_date, end_date):
        return [{"universe_code": "CSI300", "symbol": "600519", "trade_date": "2024-01-02", "weight": 4.2}]

    def stock_basic(self, list_statuses=None):
        return [
            {
                "symbol": "600519",
                "name": "贵州茅台",
                "exchange": "SSE",
                "listed_date": "2001-08-27",
                "status": "listed",
                "industry": "Food",
            }
        ]

    def daily_rows(self, symbol, start_date, end_date, adjust="raw"):
        if symbol == "000300":
            return [
                {"date": "2024-01-02", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000, "adj_factor": 1.0},
                {"date": "2024-01-03", "open": 100, "high": 102, "low": 100, "close": 101, "volume": 1000, "adj_factor": 1.0},
                {"date": "2024-01-04", "open": 101, "high": 103, "low": 101, "close": 102, "volume": 1000, "adj_factor": 1.0},
            ]
        return [
            {
                "date": "2024-01-02",
                "open": 10,
                "high": 10.2,
                "low": 9.8,
                "close": 10,
                "volume": 1000,
                "prev_close": 9.9,
                "adj_factor": 1.0,
            },
            {
                "date": "2024-01-04",
                "open": 10,
                "high": 10.5,
                "low": 9.9,
                "close": 10.2,
                "volume": 1200,
                "prev_close": 10,
                "adj_factor": 1.0,
            },
        ]

    def suspend_rows(self, symbol, start_date, end_date):
        return [{"symbol": symbol, "suspend_date": "2024-01-03", "resume_date": "2024-01-04"}]

    def daily_basic_rows(self, symbol, start_date, end_date):
        return [{"symbol": symbol, "trade_date": "2024-01-02", "factors": {"pe_ttm": 20.0, "pb": 5.0}, "source": "tushare:daily_basic"}]

    def dividend_rows(self, symbol, start_date, end_date):
        return [{"symbol": symbol, "ex_date": "2024-01-03", "action_type": "dividend", "cash_dividend": 1.0, "source": "tushare:dividend"}]

    def income_rows(self, symbol, start_date, end_date):
        return [
            {
                "symbol": symbol,
                "statement_type": "income",
                "report_date": "2023-12-31",
                "announce_date": "2024-04-02",
                "effective_date": "2024-04-03",
                "fields": {"revenue": 100.0},
                "source": "tushare:income",
            }
        ]

    def balancesheet_rows(self, symbol, start_date, end_date):
        return []

    def cashflow_rows(self, symbol, start_date, end_date):
        return []

    def fina_indicator_rows(self, symbol, start_date, end_date):
        return []


def test_csi300_pipeline_imports_core_research_data_without_synthesizing_suspend_bar(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db
    from app.services.ashare_repository import (
        assert_ashare_ready,
        corporate_actions,
        index_weights,
        trade_status_as_of,
        upsert_security,
        upsert_universe_membership,
        universe_as_of,
    )
    from app.services.csi300_data_pipeline import PIPELINE_SOURCE, run_csi300_research_import
    from app.services.pit_data import financial_factors_as_of

    # The research importer deliberately refuses to infer PIT membership from
    # same-day index weights. Seed the independently effective-dated fixture
    # that a real membership source must publish before the price import runs.
    upsert_security(
        symbol="600519",
        name="贵州茅台",
        exchange="SSE",
        listed_date="2001-08-27",
        industry="Food",
    )
    upsert_universe_membership(
        "CSI300",
        "600519",
        "2024-01-02",
        None,
        source="unit:pit-membership",
        announce_date="2024-01-02",
        effective_date="2024-01-02",
    )

    result = run_csi300_research_import(
        {
            "mode": "backfill",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "limit": 1,
            "adapter": FakeCsi300Adapter(),
            "datasets": "research-core",
            "overwrite": True,
        }
    )

    assert result["qa"]["passed"] is True
    assert result["coverage"]["successSymbols"] == 2
    assert result["coverage"]["suspendedRows"] == 1
    assert Path(result["artifacts"][0]).exists()
    assert [item["symbol"] for item in universe_as_of("CSI300", "2024-01-04")] == ["600519"]
    assert index_weights("CSI300", "2024-01-02")[0]["weight"] == 4.2
    assert trade_status_as_of(["600519"], "2024-01-03")["600519"]["is_suspended"] is True
    assert corporate_actions("600519", "2024-01-01", "2024-01-31")[0]["cash_dividend"] == 1.0
    assert financial_factors_as_of(["600519"], "2024-04-03", ["revenue"])["600519"]["revenue"]["value"] == 100.0

    from app.services import market_lake
    factor = market_lake.query_matching(
        kind="daily_basic", columns="pe_ttm", predicates=("symbol='600519'",), limit=1,
    )[0]
    suspended_bar = market_lake.query_matching(
        kind="bars", columns="close,volume", predicates=("symbol='600519'", "trade_date='2024-01-03'"),
    )
    assert factor["pe_ttm"] == 20.0
    assert suspended_bar == []
    assert_ashare_ready("600519", "2024-01-02", "2024-01-04", source=PIPELINE_SOURCE)


def test_csi300_pipeline_dry_run_does_not_write_database(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db
    from app.services.csi300_data_pipeline import run_csi300_research_import

    result = run_csi300_research_import(
        {
            "mode": "backfill",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "limit": 1,
            "adapter": FakeCsi300Adapter(),
            "datasets": "research-core",
            "dryRun": True,
        }
    )

    assert result["batchId"] == "dry-run"
    with db() as connection:
        batches = connection.execute("select count(*) as count from data_import_batches").fetchone()["count"]
        weights = connection.execute("select count(*) as count from index_weights").fetchone()["count"]
    from app.services import market_lake
    bars = len(market_lake.query_matching(kind="bars", columns="symbol"))
    assert batches == 0
    assert bars == 0
    assert weights == 0


def test_csi300_pipeline_research_only_refresh_does_not_fetch_or_write_daily_bars(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)

    from app.db import db
    from app.services.ashare_repository import upsert_security, upsert_universe_membership
    from app.services.csi300_data_pipeline import run_csi300_research_import

    upsert_security(
        symbol="600519",
        name="贵州茅台",
        exchange="SSE",
        listed_date="2001-08-27",
    )
    upsert_universe_membership(
        "CSI300",
        "600519",
        "2024-01-02",
        None,
        source="unit",
        announce_date="2024-01-02",
        effective_date="2024-01-02",
    )

    class ResearchOnlyAdapter(FakeCsi300Adapter):
        def daily_rows(self, symbol, start_date, end_date, adjust="raw"):
            raise AssertionError("daily_rows must not be called for a research-only refresh")

    result = run_csi300_research_import(
        {
            "mode": "backfill",
            "start": "2024-01-02",
            "end": "2024-12-31",
            "limit": 1,
            "adapter": ResearchOnlyAdapter(),
            "datasets": "daily_basic,financials",
        }
    )

    assert result["qa"]["passed"] is True
    assert result["coverage"]["marketRows"] == 0
    assert result["coverage"]["factorValues"] == 2
    assert result["coverage"]["financialStatements"] == 1
    with db() as connection:
        facts = connection.execute("select count(*) as count from financial_facts").fetchone()["count"]
    from app.services import market_lake
    bars = len(market_lake.query_matching(kind="bars", columns="symbol"))
    assert bars == 0
    assert facts == 1
