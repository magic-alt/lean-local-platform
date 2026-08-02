import http.client
import sys

import pytest


def test_walkforward_acceptance_api_retries_transient_disconnect(monkeypatch):
    from scripts import run_lean_paper_walkforward_acceptance as acceptance

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status":"ok"}'

    attempts = iter([http.client.RemoteDisconnected(), Response()])

    def urlopen(*_args, **_kwargs):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(acceptance.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(acceptance.time, "sleep", lambda _seconds: None)

    assert acceptance._api(
        "http://127.0.0.1:8000",
        "GET",
        "/api/health",
        timeout=1,
    ) == (200, {"status": "ok"})


def test_lean_order_status_is_normalized_for_paper_reports():
    from app.services.paper import _paper_order_status

    assert _paper_order_status(3) == "filled"
    assert _paper_order_status("2") == "partially_filled"
    assert _paper_order_status("Filled") == "filled"


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


def import_rows():
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.1", "high": "10.6", "low": "10.0", "close": "10.2", "volume": "100000"},
        {"date": "2024-01-04", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.4", "volume": "100000"},
        {"date": "2024-01-05", "open": "10.4", "high": "10.9", "low": "10.3", "close": "10.6", "volume": "100000"},
    ]
    return import_ashare_research_data(
        symbol="600519",
        provider="unit",
        market="china",
        rows=rows,
        source="akshare",
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


def import_rows_for_symbol(symbol: str):
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.1", "high": "10.6", "low": "10.0", "close": "10.2", "volume": "100000"},
        {"date": "2024-01-04", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.4", "volume": "100000"},
        {"date": "2024-01-05", "open": "10.4", "high": "10.9", "low": "10.3", "close": "10.6", "volume": "100000"},
    ]
    return import_ashare_research_data(
        symbol=symbol,
        provider="unit",
        market="china",
        rows=rows,
        source="akshare",
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


def import_benchmark_rows():
    import app.db as db_module

    with db_module.db() as connection:
        for trade_date, close in (("2024-01-03", 100.0), ("2024-01-04", 101.0), ("2024-01-05", 102.0)):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id, symbol, asset_class, market, venue, trade_date, resolution,
                     data_type, open, high, low, close, volume, adjust, source, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "idx-000300",
                    "000300",
                    "equity",
                    "china",
                    "china",
                    trade_date,
                    "daily",
                    "trade",
                    close,
                    close,
                    close,
                    close,
                    1000000,
                    "raw",
                    "akshare",
                    "now",
                ),
            )


def test_paper_daily_match_creates_order_position_and_snapshot(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()
    import_benchmark_rows()

    from app.services.paper import create_session, create_signal, list_daily_reports, list_orders, list_positions, list_snapshots, match_daily_orders

    session = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    signal = create_signal(
        session["id"],
        trade_date="2024-01-03",
        side="buy",
        target_percent=1,
        reason="unit_buy",
    )
    result = match_daily_orders(session["id"], "2024-01-03", auto_signal=False)
    assert result["executionPolicy"] == "next_open"
    assert result["orders"] == []

    result = match_daily_orders(session["id"], "2024-01-04", auto_signal=False)

    orders = list_orders(session["id"])
    positions = list_positions(session["id"])
    snapshots = list_snapshots(session["id"])

    assert signal["status"] == "created"
    assert result["orders"][0]["status"] == "filled"
    assert result["orders"][0]["trade_date"] == "2024-01-04"
    assert result["orders"][0]["fill_price"] == 10.2
    assert orders[0]["quantity"] % 100 == 0
    assert positions[0]["quantity"] == orders[0]["quantity"]
    assert snapshots[0]["equity"] > 0
    assert snapshots[-1]["positions"][0]["symbol"] == "600519"
    reports = list_daily_reports(session["id"])
    assert reports[-1]["report"]["tradeDate"] == "2024-01-04"
    assert reports[-1]["trades"][0]["status"] == "filled"
    assert reports[-1]["positions"][0]["symbol"] == "600519"
    assert reports[-1]["snapshot"]["equity"] > 0
    assert reports[-1]["qa"]["passed"] is True
    report = reports[-1]["report"]
    assert report["initialCash"] == 100000
    assert report["cash"] == reports[-1]["snapshot"]["cash"]
    assert report["NAV"] == reports[-1]["snapshot"]["equity"]
    assert report["benchmark"]["symbol"] == "000300"
    assert report["benchmark"]["close"] == 101.0
    assert round(report["benchmark"]["dailyReturn"], 6) == 0.01
    assert report["cumulativeReturn"] is not None
    assert report["excessReturn"] is not None
    assert len(report["fingerprint"]) == 64
    assert report["dataSourceStatus"]["benchmark"]["source"] == "akshare"
    assert report["positionWeights"][0]["symbol"] == "600519"
    assert report["schemaVersion"] == 1
    assert reports[-1]["schemaVersion"] == 1
    assert reports[-1]["tradeDate"] == "2024-01-04"
    assert reports[-1]["executionPolicy"] == "next_open"
    assert reports[-1]["positionWeights"][0]["symbol"] == "600519"


def test_paper_session_rejects_same_close_and_removed_override(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.paper import create_session

    with pytest.raises(ValueError, match="same_close"):
        create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "executionPolicy": "same_close"})

    with pytest.raises(ValueError, match="no longer supported"):
        create_session(
            {
                "symbol": "600519",
                "assetClass": "equity",
                "market": "china",
                "executionPolicy": "next_open",
                "allowSameDayClose": True,
            }
        )


def test_paper_constraints_reject_blacklist_watchlist_cash_floor_and_missing_status(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.paper import create_session, create_signal, match_daily_orders

    blacklist = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "blacklist": "600519"})
    create_signal(blacklist["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(blacklist["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "blacklisted"

    watchlist = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "watchlist": "000001"})
    create_signal(watchlist["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(watchlist["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "not_in_watchlist"

    observe_only = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "observeOnlySymbols": "600519"})
    create_signal(observe_only["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(observe_only["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "observe_only"

    cash_floor = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "minCash": 100000})
    create_signal(cash_floor["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(cash_floor["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "cash_floor"

    max_positions = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "maxPositions": 0})
    create_signal(max_positions["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(max_positions["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "max_positions"

    missing_status = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    create_signal(missing_status["id"], trade_date="2024-01-02", side="buy", target_percent=1)
    import app.db as db_module

    with db_module.db() as connection:
        connection.execute("delete from ashare_trade_status where symbol = ? and trade_date = ?", ("600519", "2024-01-03"))
    assert match_daily_orders(missing_status["id"], "2024-01-03", auto_signal=False)["orders"][0]["reason"] == "trade_status_missing"


def test_paper_constraints_cap_weight_and_block_st_buy(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.ashare_repository import import_trade_status
    from app.services.paper import create_session, create_signal, match_daily_orders

    capped = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "maxPositionWeight": 0.1})
    create_signal(capped["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    capped_order = match_daily_orders(capped["id"], "2024-01-04", auto_signal=False)["orders"][0]
    assert capped_order["status"] == "rejected"
    assert capped_order["reason"] == "max_position_weight"

    exact_cap = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "maxPositionWeight": 0.1})
    create_signal(exact_cap["id"], trade_date="2024-01-03", side="buy", target_percent=0.1)
    exact_cap_order = match_daily_orders(exact_cap["id"], "2024-01-04", auto_signal=False)["orders"][0]
    assert exact_cap_order["status"] == "filled"

    import_trade_status(
        [
            {
                "symbol": "600519",
                "tradeDate": "2024-01-04",
                "isSt": True,
                "canBuy": True,
                "canSell": True,
            }
        ],
        source="official-unit",
    )
    st_blocked = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    create_signal(st_blocked["id"], trade_date="2024-01-03", side="buy", target_percent=1)
    assert match_daily_orders(st_blocked["id"], "2024-01-04", auto_signal=False)["orders"][0]["reason"] == "st_blocked"


def test_paper_multi_symbol_session_fills_then_rejects_max_positions(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows_for_symbol("600519")
    import_rows_for_symbol("000001")

    from app.services.paper import create_session, create_signal, list_positions, match_daily_orders

    session = create_session(
        {
            "symbol": "600519",
            "symbols": ["600519", "000001"],
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "maxPositions": 1,
            "maxPositionWeight": 0.4,
        }
    )
    create_signal(session["id"], trade_date="2024-01-03", side="buy", symbol="600519", target_percent=0.4)
    create_signal(session["id"], trade_date="2024-01-03", side="buy", symbol="000001", target_percent=0.4)

    orders = match_daily_orders(session["id"], "2024-01-04", auto_signal=False)["orders"]

    assert orders[0]["symbol"] == "600519"
    assert orders[0]["status"] == "filled"
    assert orders[1]["symbol"] == "000001"
    assert orders[1]["status"] == "rejected"
    assert orders[1]["reason"] == "max_positions"
    assert [position["symbol"] for position in list_positions(session["id"])] == ["600519"]


def test_paper_v2_lean_intents_share_constraints_matching_and_ledger(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows_for_symbol("600519")
    import_rows_for_symbol("000001")

    import app.db as db_module
    from app.services import paper, paper_order_pipeline

    session = paper.create_session(
        {
            "symbol": "600519",
            "symbols": ["600519", "000001"],
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "blacklist": ["000001"],
        }
    )
    with db_module.db() as connection:
        connection.execute(
            """
            update paper_sessions
            set mode='lean_walkforward_v2',pipeline_version=2
            where id=?
            """,
            (session["id"],),
        )
    session = paper.get_session(session["id"])
    orders = [
        {
            "time": "2024-01-04T09:31:00+08:00",
            "symbol": "600519",
            "side": "buy",
            "quantity": 100,
            "price": 10.2,
            "status": "filled",
        },
        {
            "time": "2024-01-04T09:32:00+08:00",
            "symbol": "000001",
            "side": "buy",
            "quantity": 100,
            "price": 10.2,
            "status": "filled",
        },
    ]
    strategy_hash = "a" * 64
    child = {
        "id": "backtest-run-v2",
        "fingerprint": {
            "strategyFileHash": strategy_hash,
            "largeEvidence": "x" * 1000,
        },
    }

    first = paper._process_v2_lean_intents(
        session=session,
        paper_run={"id": "paper-run-v2"},
        child=child,
        orders=orders,
    )
    second = paper._process_v2_lean_intents(
        session=paper.get_session(session["id"]),
        paper_run={"id": "paper-run-v2"},
        child=child,
        orders=orders,
    )

    assert [item["status"] for item in first["orders"]] == ["filled", "rejected"]
    assert first["orders"][1]["reason"] == "blacklisted"
    assert [item["id"] for item in first["orders"]] == [item["id"] for item in second["orders"]]
    intents = paper_order_pipeline.list_intents(session["id"])
    assert len(intents) == 2
    assert {item["strategy_fingerprint"] for item in intents} == {strategy_hash}
    states = {
        item["symbol"]: paper_order_pipeline.current_state(item["id"])
        for item in intents
    }
    assert states == {"600519": "RECONCILIATION_PENDING", "000001": "REJECTED"}
    with db_module.db() as connection:
        fill_count = connection.execute("select count(*) as count from paper_order_fills").fetchone()["count"]
        ledger_count = connection.execute("select count(*) as count from paper_ledger_entries").fetchone()["count"]
        order_count = connection.execute("select count(*) as count from paper_orders").fetchone()["count"]
        checkpoint_count = connection.execute("select count(*) as count from paper_run_checkpoints").fetchone()["count"]
        ledger_entries = connection.execute(
            "select entry_type,asset,amount from paper_ledger_entries order by entry_type"
        ).fetchall()
    assert fill_count == 1
    # Opening cash plus principal, commission and position entries.  Repeating
    # the same LEAN intent must not duplicate either the fill or its fees.
    assert ledger_count == 4
    assert order_count == 2
    assert checkpoint_count == 4
    assert [(entry["entry_type"], entry["asset"]) for entry in ledger_entries] == [
        ("CASH_DEPOSIT", "cash"),
        ("COMMISSION", "cash"),
        ("POSITION_INCREASE", "equity"),
        ("TRADE_PRINCIPAL", "cash"),
    ]
    assert [entry["amount"] for entry in ledger_entries] == pytest.approx(
        [100000.0, -paper._fee(100, 10.2, "buy", session), 1020.0, -1020.0]
    )
    current = paper.get_session(session["id"])
    assert current["cash"] == pytest.approx(100000 - (100 * 10.2) - paper._fee(100, 10.2, "buy", current))
    projection = paper_order_pipeline.ledger_projection(session["id"])
    assert projection["cash"] == pytest.approx(current["cash"])
    assert projection["positions"] == [
        {
            "symbol": "600519",
            "quantity": 100.0,
            "average_price": 10.2,
            "last_buy_date": "2024-01-04",
        }
    ]

    # Session rows are read models.  A worker restart must be able to discard
    # stale rows and reconstruct the same balances without another fee entry.
    with db_module.db() as connection:
        connection.execute("update paper_sessions set cash=1 where id=?", (session["id"],))
        connection.execute("delete from paper_positions where session_id=?", (session["id"],))
    rebuilt = paper._apply_v2_ledger_projection(session["id"], "2024-01-04")
    assert rebuilt == projection
    assert paper.get_session(session["id"])["cash"] == pytest.approx(projection["cash"])
    assert [
        {key: position[key] for key in ("symbol", "quantity", "average_price", "last_buy_date")}
        for position in paper.list_positions(session["id"])
    ] == projection["positions"]
    with db_module.db() as connection:
        assert connection.execute(
            "select count(*) as count from paper_ledger_entries"
        ).fetchone()["count"] == 4


def test_paper_v2_transition_graph_rejects_illegal_state_changes(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services import paper_order_pipeline

    intent = paper_order_pipeline.record_intent(
        session_id="session",
        paper_run_id="paper-run",
        backtest_run_id="backtest-run",
        event_key="event",
        trade_date="2024-01-04",
        symbol="600519",
        side="buy",
        quantity=100,
        requested_price=10,
        raw_intent={"source": "unit"},
    )

    assert len(paper_order_pipeline.ORDER_STATES) == 13
    with pytest.raises(ValueError, match="Illegal Paper order transition"):
        paper_order_pipeline.append_transition(
            intent["id"],
            "FILLED",
            event_type="skip_constraints",
            idempotency_key="illegal",
        )


def test_paper_v2_finalize_is_requeued_after_worker_loss():
    from app.tasks.worker import (
        finalize_paper_walkforward_task,
        recover_paper_finalizations_task,
    )

    assert finalize_paper_walkforward_task.acks_late is True
    assert finalize_paper_walkforward_task.reject_on_worker_lost is True
    assert recover_paper_finalizations_task.name == "lean_web.recover_paper_finalizations"


def test_paper_finalization_recovery_dispatches_durable_run(monkeypatch):
    from app.tasks import worker

    transitions = []
    dispatched = []
    monkeypatch.setattr(
        worker.paper_service,
        "recoverable_walkforward_finalizations",
        lambda **kwargs: [
            {
                "id": "paper-run",
                "session_id": "paper-session",
                "trade_date": "2024-01-04",
            }
        ],
    )
    monkeypatch.setattr(
        worker.paper_scheduler,
        "job_for_date",
        lambda session_id, trade_date: {"id": "daily-job", "state": "RUNNING"},
    )
    def transition(job_id, state, **kwargs):
        transitions.append((job_id, state, kwargs))
        return {"id": job_id, "state": state}

    monkeypatch.setattr(worker.paper_scheduler, "transition_job", transition)

    class Result:
        id = "replacement-task"

    monkeypatch.setattr(
        worker.finalize_paper_walkforward_task,
        "apply_async",
        lambda args: dispatched.append(args) or Result(),
    )

    result = worker.recover_paper_finalizations_task(
        paper_run_id="paper-run",
        stale_seconds=0,
    )

    assert dispatched == [["paper-run"]]
    assert transitions[0][0:2] == ("daily-job", "RETRYING")
    assert transitions[1][0:2] == ("daily-job", "RUNNING")
    assert result["recovered"] == [
        {"paperRunId": "paper-run", "taskId": "replacement-task"}
    ]


def test_successful_paper_finalization_redelivery_is_noop(monkeypatch):
    from app.services import paper

    completed = {"id": "paper-run", "status": "success"}
    monkeypatch.setattr(paper, "get_walkforward_run", lambda paper_run_id: completed)
    monkeypatch.setattr(
        paper,
        "get_session",
        lambda session_id: pytest.fail("completed finalization must not re-enter"),
    )

    assert paper.finalize_walkforward_run("paper-run") == completed


def test_paper_replay_auto_signal_executes_before_generating_next_signal(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows_for_symbol("600519")
    import_benchmark_rows()

    from app.services.paper import create_session, run_replay

    session = create_session(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "benchmarkSymbol": "000300",
            "executionPolicy": "next_open",
            "fast": 1,
            "slow": 2,
            "maxPositionWeight": 0.4,
            "signalTargetPercent": 0.4,
        }
    )

    result = run_replay(session["id"], "2024-01-02", "2024-01-05", auto_signal=True)
    orders = [order for day in result["days"] for order in day["orders"]]
    signals = [signal for report in result["reports"] for signal in report["signals"]]

    assert [order["status"] for order in orders] == ["filled"]
    assert {order.get("reason") for order in orders if order.get("reason")} == set()
    assert sum(1 for signal in signals if signal["side"] == "buy") == 1
    assert result["positions"][0]["symbol"] == "600519"


def test_paper_replay_acceptance_has_fill_rejections_and_canonical_report_fields(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    for symbol in ("600519", "000001", "000002", "000003", "000004"):
        import_rows_for_symbol(symbol)
    import_benchmark_rows()

    from app.services.ashare_repository import import_trade_status
    from app.services.paper import create_session, create_signal, run_replay

    import_trade_status(
        [
            {
                "symbol": "000003",
                "tradeDate": "2024-01-04",
                "isSt": True,
                "canBuy": True,
                "canSell": True,
            }
        ],
        source="official-unit",
    )
    session = create_session(
        {
            "symbol": "600519",
            "symbols": ["600519", "000001", "000002", "000003", "000004"],
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "benchmarkSymbol": "000300",
            "executionPolicy": "next_open",
            "maxPositions": 1,
            "maxPositionWeight": 0.4,
            "blacklist": "000001",
            "observeOnlySymbols": "000002",
            "watchlist": "600519,000001,000002,000003,000004",
            "allowStBuy": False,
        }
    )
    for symbol in ("600519", "000001", "000002", "000003", "000004"):
        create_signal(session["id"], trade_date="2024-01-03", side="buy", symbol=symbol, target_percent=0.4)

    result = run_replay(session["id"], "2024-01-03", "2024-01-04", auto_signal=False)
    orders = result["days"][-1]["orders"]

    assert result["tradingDays"] == 2
    assert any(order["status"] == "filled" and order["symbol"] == "600519" for order in orders)
    reasons = {order["symbol"]: order["reason"] for order in orders if order["status"] == "rejected"}
    assert reasons == {
        "000001": "blacklisted",
        "000002": "observe_only",
        "000003": "st_blocked",
        "000004": "max_positions",
    }
    report = result["reports"][-1]
    assert report["schemaVersion"] == 1
    assert report["tradeDate"] == "2024-01-04"
    assert report["executionPolicy"] == "next_open"
    assert "pendingSignals" in report
    assert report["executionSignals"] == report["pendingSignals"]
    assert report["NAV"] == report["snapshot"]["equity"]
    assert report["benchmark"]["symbol"] == "000300"
    assert report["benchmarkSymbol"] == "000300"
    assert report["benchmarkClose"] == report["benchmark"]["close"]
    assert report["benchmarkReturn"] == report["benchmark"]["return"]
    assert set(report["rejectionReasons"]) == set(reasons.values())
    assert set(report["rejectReasons"]) == set(reasons.values())
    assert {order["symbol"] for order in report["rejectedOrders"]} == set(reasons)
    assert report["qaGateStatus"] == "ok"
    assert len(report["fingerprint"]) == 64


def test_paper_replay_acceptance_script_creates_fill_and_reject(tmp_path, monkeypatch, capsys):
    configure_temp_platform(tmp_path, monkeypatch)
    for symbol in ("600519", "000001"):
        import_rows_for_symbol(symbol)
    import_benchmark_rows()

    from scripts import run_paper_replay_acceptance

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paper_replay_acceptance.py",
            "--symbols",
            "600519,000001",
            "--benchmark",
            "000300",
            "--start-date",
            "2024-01-03",
            "--end-date",
            "2024-01-04",
            "--min-trading-days",
            "2",
        ],
    )

    assert run_paper_replay_acceptance.main() == 0
    output = capsys.readouterr().out
    assert '"fills": 1' in output
    assert '"rejects": 1' in output
    assert "blacklisted" in output


def test_paper_checkpoint_probe_filters_and_returns_current_run_status(
    tmp_path,
    monkeypatch,
):
    configure_temp_platform(tmp_path, monkeypatch)

    from fastapi.testclient import TestClient

    from app.db import db
    from app.main import app
    from app.services import paper, paper_order_pipeline

    session = paper.create_session(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
        }
    )
    with db() as connection:
        connection.execute(
            "update paper_sessions set mode='lean_walkforward_v2',pipeline_version=2 where id=?",
            (session["id"],),
        )
        connection.execute(
            """
            insert into paper_walkforward_runs
            (id,session_id,trade_date,status,created_at,started_at)
            values ('probe-run',?,'2024-01-04','running','2024-01-04T00:00:00Z','2024-01-04T00:00:00Z')
            """,
            (session["id"],),
        )
        connection.execute(
            """
            insert into paper_run_checkpoints
            (id,paper_run_id,phase,status,digest,payload_json,created_at,completed_at)
            values
            ('probe-intent','probe-run','intent_capture','completed','intent-digest','{}',
             '2024-01-04T00:00:01Z','2024-01-04T00:00:01Z'),
            ('probe-ledger','probe-run','ledger','completed','ledger-digest','{}',
             '2024-01-04T00:00:02Z','2024-01-04T00:00:02Z')
            """
        )

    rows = paper_order_pipeline.list_checkpoints(
        session["id"],
        trade_date="2024-01-04",
        phase="intent_capture",
    )
    assert [(row["phase"], row["run_status"]) for row in rows] == [
        ("intent_capture", "running")
    ]

    response = TestClient(app).get(
        f"/api/paper/{session['id']}/checkpoints",
        params={"tradeDate": "2024-01-04", "phase": "intent_capture"},
    )
    assert response.status_code == 404


def test_lean_paper_requires_and_freezes_a_validation_passed_backtest(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.core import config
    from app.db import db, json_dump
    from app.services.paper import create_session, trusted_backtest_candidates

    snapshot_dir = tmp_path / "runs" / "trusted-run" / "strategy"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "main.py").write_text("# frozen strategy\n", encoding="utf-8")
    parameters = {
        "ticker": "600460",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": "2024-01-01",
        "end": "2026-07-13",
        "cash": 50000,
        "benchmarkSymbol": "000300",
        "strategySnapshotDir": "/workspace/web/runtime/runs/trusted-run/strategy",
        "strategySnapshotMainFile": "main.py",
        "strategySnapshotAlgorithmClass": "MacdAlgorithm",
        "strategySnapshotLanguage": "Python",
    }
    now = "2026-07-16T00:00:00+00:00"
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    with db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, project_id, symbol, asset_class, venue, resolution, data_type, parameters_json,
                 status, docker_image, results_dir, created_at, finished_at, validation_json,trust_status)
            values (?, ?, ?, 'equity', 'china', 'daily', 'trade', ?, 'success', ?, ?, ?, ?, ?,'trusted')
            """,
            (
                "trusted-run",
                "project-macd",
                "600460",
                json_dump(parameters),
                "lean:test",
                str(tmp_path / "runs" / "trusted-run" / "results"),
                now,
                now,
                json_dump({"passed": True, "data": {"truncated": False}}),
            ),
        )
        connection.execute(
            """
            insert into experiments
                (id, run_id, strategy_version_id, dataset_version_id, parameter_hash, fingerprint_json,
                 validation_json, experiment_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, '{}', '{}', ?, ?)
            """,
            (
                "experiment-1",
                "trusted-run",
                "strategy-v1",
                "dataset-v1",
                "params-v1",
                json_dump(
                    {
                        "datasetCertification": {
                            "source": "tushare",
                            "environment": "production",
                            "isProduction": True,
                            "isCertified": True,
                            "qaStatus": "ok",
                        }
                    }
                ),
                now,
                now,
            ),
        )
        connection.execute(
            "update backtest_runs set fingerprint_json = ? where id = ?",
            (
                json_dump(
                    {
                        "datasetCertification": {
                            "source": "tushare",
                            "environment": "production",
                            "isProduction": True,
                            "isCertified": True,
                            "qaStatus": "ok",
                        }
                    }
                ),
                "trusted-run",
            ),
        )
        connection.execute(
            """
            insert into backtest_results
                (id, job_id, summary_metrics_json, equity_curve_json, drawdown_curve_json,
                 orders_json, trades_json, holdings_json, statistics_json, created_at)
            values (?, ?, '{}', '[]', '[]', '[]', '[]', '[]', '{}', ?)
            """,
            ("result-1", "trusted-run", now),
        )

    candidates = trusted_backtest_candidates("project-macd")
    assert [item["id"] for item in candidates] == ["trusted-run"]

    session = create_session(
        {
            "mode": "lean_walkforward",
            "name": "MACD paper",
            "projectId": "project-macd",
            "sourceBacktestId": "trusted-run",
            "startDate": "2026-07-14",
            "autoAdvance": True,
        }
    )

    assert session["mode"] == "lean_walkforward"
    assert session["legacy_read_only"] is False
    assert session["source_backtest_id"] == "trusted-run"
    assert session["strategy_version_id"] == "strategy-v1"
    assert session["parameter_hash"] == "params-v1"
    assert session["cash"] == 50000
    assert session["parameters"]["strategySnapshotDir"] == str(snapshot_dir)

    import app.services.paper as paper_module

    monkeypatch.setattr(paper_module, "PAPER_ORDER_PIPELINE_V2_ENABLED", True)
    v2_session = create_session(
        {
            "mode": "lean_walkforward_v2",
            "name": "MACD paper v2",
            "projectId": "project-macd",
            "sourceBacktestId": "trusted-run",
            "startDate": "2026-07-14",
            "autoAdvance": False,
            "maxPositionWeight": 0.2,
            "minCash": 1000,
            "blacklist": ["000001"],
        }
    )
    assert v2_session["mode"] == "lean_walkforward_v2"
    assert v2_session["pipeline_version"] == 2
    assert v2_session["parameters"]["maxPositionWeight"] == 0.2
    assert v2_session["parameters"]["minCash"] == 1000
    assert v2_session["parameters"]["blacklist"] == ["000001"]

    captured = {}
    with db() as connection:
        connection.execute(
            "update paper_sessions set cash=1234 where id=?",
            (v2_session["id"],),
        )
    monkeypatch.setattr(
        paper_module,
        "create_backtest_job",
        lambda payload: (
            captured.update(payload)
            or {
                "id": "paper-child",
                "task_id": "paper-child-task",
            }
        ),
    )
    monkeypatch.setattr(paper_module, "mark_backtest_queued", lambda run_id: None)

    paper_module.create_walkforward_run(v2_session["id"], "2026-07-14")

    assert captured["cash"] == 50000
