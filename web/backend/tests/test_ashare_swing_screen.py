from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


def configure(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.projects as projects_module
    import app.services.research_snapshots as snapshots_module
    import app.services.market_lake as market_lake
    import app.api.research as research_api
    import hashlib

    db_path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db_module, "DATABASE_URL", "sqlite:///{db_path}".format(db_path=db_path))
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "SQLITE_TEST_BACKEND_ENABLED", True)
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(market_lake, "PARQUET_DIR", Path(tmp_path.anchor) / "tmp" / "q" / hashlib.md5(str(tmp_path).encode("utf-8")).hexdigest()[:8])

    original_scope = market_lake._scope

    def safe_scope(**kwargs):
        scope = original_scope(**kwargs)
        scope["source"] = str(scope.get("source", "")).replace(":", "_")
        return scope

    monkeypatch.setattr(market_lake, "_scope", safe_scope)
    monkeypatch.setattr(snapshots_module, "RESEARCH_DIR", tmp_path / "research")
    if hasattr(research_api, "RESEARCH_DIR"):
        monkeypatch.setattr(research_api, "RESEARCH_DIR", tmp_path / "research")
    db_module.init_db()
    return db_module

def orderly_history() -> pd.DataFrame:
    size = 520
    index = np.arange(size)
    close = 20 * (1 + 0.00045 * index) * (1 + 0.04 * np.sin(index / 13))
    sequence = np.array([0.98, 0.97, 0.98, 0.96, 0.97, 0.95, 0.96, 0.94, 0.95, 0.935, 0.945, 0.94, 0.948, 0.944, 0.952])
    peak = max(close[-60 : -len(sequence)])
    close[-len(sequence) :] = peak * sequence
    volume = np.full(size, 20_000_000.0)
    volume[-5:] = 15_000_000.0
    return pd.DataFrame(
        {
            "close_qfq": close,
            "high_qfq": close * 1.012,
            "low_qfq": close * 0.988,
            "volume": volume,
            "amount": np.full(size, 500_000_000.0),
        }
    )


def test_orderly_pullback_features_distinguish_current_and_path_drawdown():
    from app.services.ashare_swing_screen import ScreenRules, calculate_stock_features

    features = calculate_stock_features(orderly_history(), ScreenRules())

    assert features is not None
    assert features["technical_pass"] is True
    assert features["entry_ready"] is True
    assert features["triggered"] is True
    assert features["reclaim_ma10"] is True
    assert -0.10 <= features["current_drawdown_60"] <= -0.04
    assert features["max_drawdown_60"] < features["current_drawdown_60"]
    assert features["pullback_age"] >= 3
    assert 40 <= features["rsi14"] <= 58


def test_fast_crash_is_rejected_before_entry_classification():
    from app.services.ashare_swing_screen import ScreenRules, calculate_stock_features

    history = orderly_history()
    history.loc[history.index[-5] :, "close_qfq"] *= np.linspace(1.0, 0.72, 5)
    history.loc[history.index[-5] :, "high_qfq"] = history.loc[history.index[-5] :, "close_qfq"] * 1.012
    history.loc[history.index[-5] :, "low_qfq"] = history.loc[history.index[-5] :, "close_qfq"] * 0.988

    features = calculate_stock_features(history, ScreenRules())

    assert features is not None
    assert features["technical_pass"] is False
    assert features["entry_ready"] is False
    assert features["first_rejection"] in {"worst_3d", "worst_5d", "worst_10d"}


def test_pullback_runs_keep_current_episode_out_of_historical_p80():
    from app.services.ashare_swing_screen import pullback_run_statistics

    current_age, p80, completed = pullback_run_statistics(
        pd.Series([False, True, True, False, True, True, True, False, True, True])
    )

    assert current_age == 2
    assert completed == 2
    assert p80 == pytest.approx(2.8)


def _seed_screen_data(db_module):
    from app.db import db, utc_now
    from app.services import market_lake

    dates = pd.bdate_range(end="2026-07-31", periods=520).strftime("%Y-%m-%d").tolist()
    histories = {
        "600036": orderly_history(),
        "601166": orderly_history().assign(
            close_qfq=lambda frame: frame["close_qfq"] / frame["close_qfq"].iloc[-1] * 18.5,
        ),
        "600111": orderly_history().assign(
            close_qfq=lambda frame: frame["close_qfq"] / frame["close_qfq"].iloc[-1] * 60.0,
        ),
    }
    for frame in histories.values():
        frame["high_qfq"] = frame["close_qfq"] * 1.012
        frame["low_qfq"] = frame["close_qfq"] * 0.988
    now = utc_now()
    with db() as connection:
        connection.execute(
            "insert into trade_calendar (market,trade_date,is_open,source) values ('china','2026-07-31',1,'tushare')"
        )
        for symbol, name in (("600036", "招商银行"), ("601166", "兴业银行"), ("600111", "北方稀土")):
            connection.execute(
                """
                insert into securities
                    (symbol,name,exchange,market,listed_date,status,is_st,created_at,updated_at)
                values (?,?,?,'china','2000-01-01','listed',0,?,?)
                """,
                (symbol, name, "SSE", now, now),
            )
            connection.execute(
                """
                insert into universe_membership
                    (universe_code,symbol,start_date,announce_date,effective_date,source,batch_id)
                values ('ALL_A',?,'2000-01-01','2000-01-01','2000-01-01','tushare:stock_basic','unit')
                """,
                (symbol,),
            )
            connection.execute(
                """
                insert into security_name_history
                    (id,symbol,name,start_date,is_st,source,payload_hash,created_at)
                values (?,?,?,'2000-01-01',0,'tushare:namechange',?,?)
                """,
                (f"name-{symbol}", symbol, name, symbol * 10 + "abcd", now),
            )
            market_lake.upsert_rows(
                [{"symbol": symbol, "trade_date": "2026-07-31", "can_buy": True, "can_sell": True,
                  "batch_id": "unit", "updated_at": now}],
                kind="trade_status", asset_class="equity", market="china", venue="china",
                resolution="daily", data_type="status", source="tushare:stk_limit",
            )
            market_lake.upsert_rows(
                [{"symbol": symbol, "trade_date": "2026-07-31", "pe_ttm": 8.0,
                  "total_mv_cny": 300_000_000_000.0, "batch_id": "unit", "created_at": now}],
                kind="daily_basic", asset_class="equity", market="china", venue="china",
                resolution="daily", data_type="metric", source="tushare:daily_basic",
            )
            connection.executemany(
                """
                insert into financial_facts
                    (symbol,field_name,report_date,announce_date,effective_date,value,unit,source,batch_id,created_at)
                values (?,?,'2026-03-31','2026-04-30','2026-04-30',?,'CNY','tushare:income','unit',?)
                """,
                [
                    (symbol, "n_income_attr_p", 10_000_000_000.0, now),
                    (symbol, "profit_dedt", 9_000_000_000.0, now),
                ],
            )
            frame = histories[symbol]
            bars = []
            factors = []
            for row_index, trade_date in enumerate(dates):
                close = float(frame["close_qfq"].iloc[row_index])
                bars.append({"instrument_id": f"inst-{symbol}", "symbol": symbol,
                             "trade_date": trade_date, "open": close,
                             "high": float(frame["high_qfq"].iloc[row_index]),
                             "low": float(frame["low_qfq"].iloc[row_index]), "close": close,
                             "volume": float(frame["volume"].iloc[row_index]),
                             "amount": float(frame["amount"].iloc[row_index]),
                             "batch_id": "unit", "created_at": now})
                factors.append({"symbol": symbol, "trade_date": trade_date, "adj_factor": 1.0,
                                "batch_id": "unit"})
            market_lake.upsert_rows(
                bars, kind="bars", asset_class="equity", market="china", venue="china",
                resolution="daily", data_type="trade", adjust="raw", source="tushare",
            )
            market_lake.upsert_rows(
                factors, kind="adjustment_factor", asset_class="equity", market="china", venue="china",
                resolution="daily", data_type="factor", adjust="raw", source="tushare",
            )


def test_async_screen_run_writes_auditable_artifacts_and_snapshot(tmp_path, monkeypatch):
    db_module = configure(tmp_path, monkeypatch)
    _seed_screen_data(db_module)
    from app.services import research_runs, research_snapshots

    scope = {
        "asset": {"assetClass": "equity", "market": "china", "venue": "china", "resolution": "daily", "dataType": "trade"},
        "selection": {"type": "universe", "values": ["ALL_A"]},
        "time": {"startDate": "2024-01-01", "endDate": "2026-07-31", "asOfDate": "2026-07-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }
    preview = research_runs.preview("ashare-swing-candidates", scope, {"minHistoryBars": 500})
    assert preview["blocking"] == []
    run = research_runs.create_run(
        template_key="ashare-swing-candidates",
        name="unit screen",
        scope=scope,
        parameters={"minHistoryBars": 500, "topN": 10, "caseSymbols": ["600036", "600111"]},
    )
    assert run["status"] == "queued"

    finished = research_runs.execute_analysis_run(run["id"])

    assert finished["status"] == "success"
    result = finished["result"]
    assert result["summary"]["universeCount"] == 3
    assert result["summary"]["bucketA"] >= 1
    assert {item["key"] for item in result["artifacts"]} == {
        "report",
        "candidatesCsv",
        "auditCsv",
        "auditParquet",
        "manifest",
    }
    report = research_runs.artifact_path(run["id"], "report")
    assert "研究优先级筛选，不是买入评级" in report.read_text(encoding="utf-8")
    with pytest.raises(KeyError):
        research_runs.artifact_path(run["id"], "../manifest")

    snapshot = research_snapshots.create_run_snapshot(run["id"])
    snapshot_root = tmp_path / "research" / "snapshots" / snapshot["snapshotId"]
    assert (snapshot_root / "screen-audit.parquet").is_file()
    assert snapshot["researchRunId"] == run["id"]


def test_research_api_execution_routes_removed_after_contract_convergence(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from fastapi.testclient import TestClient
    from app.main import app

    payload = {
        "asset": {
            "assetClass": "equity",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
        },
        "selection": {"type": "universe", "values": ["ALL_A"]},
        "time": {"startDate": "2024-01-01", "endDate": "2026-07-31", "asOfDate": "2026-07-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }

    response = TestClient(app).post(
        "/api/research/runs",
        json={"template": "ashare-swing-candidates", "scope": payload, "parameters": {"minHistoryBars": 500}},
    )
    assert response.status_code == 404

def test_case_catalog_creates_audit_notebook(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.services import examples

    examples._catalog.cache_clear()
    result = examples.instantiate_example("research", "ashare-swing-candidates")
    notebook = Path(result["project"]["project_path"]) / "notebooks" / "ashare-swing-candidates.ipynb"
    payload = json.loads(notebook.read_text(encoding="utf-8"))

    assert result["project"]["config"]["exampleDefaults"]["researchTemplateKey"] == "ashare-swing-candidates"
    assert any("screen-audit.parquet" in "".join(cell.get("source") or []) for cell in payload["cells"])


def test_screen_backfill_accepts_governed_on_demand_inputs_and_normalizes_name_history(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.db import db
    from app.services import data_sync

    run = data_sync.create_sync_run(
        requested=["namechange", "daily_basic", "income", "fina_indicator"],
        mode="screen_backfill",
        request_scope={"type": "ashare_swing_screen", "universeCode": "ALL_A", "asOfDate": "2026-07-31"},
    )
    assert run["mode"] == "screen_backfill"
    assert {item["dataset_key"] for item in run["items"]} == {"namechange", "daily_basic", "income", "fina_indicator"}
    with pytest.raises(ValueError, match="only accepts A-share screening datasets"):
        data_sync.create_sync_run(
            requested=["hk_daily"],
            mode="screen_backfill",
            request_scope={"type": "ashare_swing_screen", "universeCode": "ALL_A", "asOfDate": "2026-07-31"},
        )

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "namechange")
    data_sync._normalize_optional(
        spec,
        [
            {
                "symbol": "600036",
                "name": "招商银行",
                "start_date": "2002-04-09",
                "end_date": None,
                "is_st": False,
                "source": "tushare:namechange",
            }
        ],
        "unit",
    )
    with db() as connection:
        row = connection.execute("select name,is_st from security_name_history where symbol='600036'").fetchone()
    assert dict(row) == {"name": "招商银行", "is_st": 0}


def test_screen_backfill_executes_on_demand_and_bounds_provider_history(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch)
    from app.db import db, utc_now
    from app.services import data_sync

    class FakePro:
        @staticmethod
        def call_counts():
            return {}

    class FakeAdapter:
        pro = FakePro()

        def __init__(self):
            self.starts: list[str] = []

        def namechange_rows(self, symbol):
            return [
                {
                    "symbol": symbol,
                    "name": "招商银行",
                    "start_date": "2002-04-09",
                    "end_date": None,
                    "is_st": False,
                    "source": "tushare:namechange",
                }
            ]

        def daily_basic_rows(self, symbol, start_date, end_date):
            self.starts.append(start_date)
            return [
                {
                    "symbol": symbol,
                    "trade_date": end_date,
                    "factors": {"pe_ttm": 8.0, "total_mv_cny": 300_000_000_000.0},
                    "source": "tushare:daily_basic",
                }
            ]

    data_sync.ensure_catalog()
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into securities
                (symbol,name,exchange,market,listed_date,status,is_st,created_at,updated_at)
            values ('600036','招商银行','SSE','china','2002-04-09','listed',0,?,?)
            """,
            (now, now),
        )
        connection.execute(
            "insert into trade_calendar (market,trade_date,is_open,source) values ('china','2026-07-31',1,'tushare')"
        )
        connection.execute(
            "update provider_dataset_catalog set permission_status='available' where dataset_key in ('namechange','daily_basic')"
        )

    monkeypatch.setattr(data_sync, "_permission_probe_keys", lambda selected: set())
    monkeypatch.setattr(data_sync, "audit_existing_data", lambda: {})
    adapter = FakeAdapter()
    scope = {
        "type": "ashare_swing_screen",
        "universeCode": "ALL_A",
        "asOfDate": "2026-07-31",
        "minHistoryBars": 500,
    }

    name_run = data_sync.create_sync_run(requested=["namechange"], mode="screen_backfill", request_scope=scope)
    name_result = data_sync.run_sync(name_run["id"], adapter=adapter)
    assert name_result["status"] == "success", json.dumps(name_result, ensure_ascii=False, default=str)
    with db() as connection:
        name = connection.execute("select name from security_name_history where symbol='600036'").fetchone()
    assert name["name"] == "招商银行"

    basic_run = data_sync.create_sync_run(requested=["daily_basic"], mode="screen_backfill", request_scope=scope)
    basic_result = data_sync.run_sync(basic_run["id"], adapter=adapter)
    assert basic_result["status"] == "success", json.dumps(basic_result, ensure_ascii=False, default=str)
    assert adapter.starts == ["2024-03-23"]

