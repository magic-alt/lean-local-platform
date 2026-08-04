from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _init() -> None:
    from app.db import init_db

    init_db()


def _account(name: str, cash: str = "1000000.00") -> dict:
    from app.services.paper_accounts import create_account

    return create_account(
        {
            "name": name,
            "initialCash": cash,
            "benchmarkSymbol": "000300",
            "riskConfig": {
                "maxPositions": 10,
                "maxPositionWeight": "0.2",
                "cashFloor": "50000",
            },
        }
    )


def _frozen_candidate(tmp_path: Path) -> dict:
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "main.py").write_text("class Algorithm: pass", encoding="utf-8")
    return {
        "candidate": {
            "id": "trusted-backtest",
            "name": "Frozen Strategy",
            "symbol": "600519",
            "strategyVersionId": "strategy-v1",
            "parameterHash": "parameter-hash",
        },
        "run": {
            "id": "trusted-backtest",
            "symbol": "600519",
            "parameters": {},
            "fingerprint": {},
        },
        "parameters": {
            "ticker": "600519",
            "start": "2024-01-01",
            "end": "2024-01-31",
            "cash": 1000000,
            "strategySnapshotDir": str(snapshot),
            "strategySnapshotHash": "strategy-sha",
            "dataType": "trade",
        },
        "fingerprint": {"datasetCertification": {"id": "dataset-v1", "isCertified": True}},
        "certification": {"id": "dataset-v1", "isCertified": True},
        "versions": {"experiment": {"id": "experiment-v1"}},
        "snapshotDir": str(snapshot),
    }


def _deployment(account_id: str, tmp_path: Path, monkeypatch, *, signal_mode: str = "paper_execute") -> dict:
    from app.services import paper_accounts

    monkeypatch.setattr(paper_accounts, "_candidate", lambda *_args: _frozen_candidate(tmp_path))
    return paper_accounts.create_deployment(
        account_id,
        {
            "name": "Frozen Strategy",
            "projectId": "project-1",
            "sourceBacktestId": "trusted-backtest",
            "signalMode": signal_mode,
            "isPrimary": True,
        },
    )


def test_empty_collecting_cohort_can_rebind_explicit_replacement_deployments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts, paper_certification

    first = _account("cohort-rebind-a", "1000000")
    second = _account("cohort-rebind-b", "3000000")
    first_deployment = _deployment(first["id"], tmp_path, monkeypatch)
    second_deployment = _deployment(second["id"], tmp_path, monkeypatch)
    cohort = paper_certification.create_cohort(
        name="collecting replacement",
        account_ids=[first["id"], second["id"]],
    )
    replacement = paper_accounts.update_deployment(
        first_deployment["id"],
        {"universeConfig": {"symbols": ["600519"]}},
    )

    rebound = paper_certification.rebind_collecting_cohort_members(
        cohort["id"],
        {
            first["id"]: replacement["id"],
            second["id"]: second_deployment["id"],
        },
    )

    bindings = {member["paper_account_id"]: member["deployment_id"] for member in rebound["members"]}
    assert bindings[first["id"]] == replacement["id"]
    assert bindings[second["id"]] == second_deployment["id"]
    assert all(member["certified_sessions"] == 0 for member in rebound["members"])
    with db() as connection:
        connection.execute(
            "update paper_certification_cohorts set status='certified' where id=?",
            (cohort["id"],),
        )
    with pytest.raises(ValueError, match="bindings are immutable"):
        paper_certification.rebind_collecting_cohort_members(
            cohort["id"],
            {
                first["id"]: replacement["id"],
                second["id"]: second_deployment["id"],
            },
        )


def test_account_creation_writes_only_opening_ledger_and_projection() -> None:
    _init()
    from app.db import db
    from app.services.paper_accounts import get_account, rebuild_projection

    account = _account("Account A", "1234567.89")

    assert account["status"] == "draft"
    assert account["initial_cash"] == "1234567.89000000"
    assert account["cash"] == "1234567.89000000"
    assert account["total_equity"] == "1234567.89000000"
    with db() as connection:
        ledger = connection.execute(
            """
            select * from paper_ledger_entries
            where paper_account_id=? order by ledger_sequence
            """,
            (account["id"],),
        ).fetchall()
        generation = connection.execute(
            "select * from paper_account_generations where paper_account_id=?",
            (account["id"],),
        ).fetchone()
        shadow = connection.execute(
            "select cash,equity from paper_sessions where id=?",
            (account["shadow_session_id"],),
        ).fetchone()
    assert len(ledger) == 1
    assert ledger[0]["entry_type"] == "CASH_DEPOSIT"
    assert Decimal(str(ledger[0]["precise_amount"])) == Decimal("1234567.89000000")
    assert generation["opening_ledger_entry_id"] == ledger[0]["id"]
    assert Decimal(str(shadow["cash"])) == Decimal("0")
    assert Decimal(str(shadow["equity"])) == Decimal("0")
    rebuilt = rebuild_projection(account["id"], "2026-07-26")
    assert rebuilt["account"]["cash"] == get_account(account["id"])["cash"]


def test_legacy_paper_routes_are_not_exposed() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/paper" not in paths
    assert "/api/paper/{session_id}" not in paths
    assert "/api/insights/{report_id}/paper-signals" not in paths
    assert "/api/paper/accounts/candidates" in paths


def test_accounts_are_ledger_and_projection_isolated() -> None:
    _init()
    from app.db import db, utc_now
    from app.services.paper_accounts import rebuild_projection

    first = _account("Account A", "100000")
    second = _account("Account B", "250000")
    with db() as connection:
        connection.execute(
            """
            insert into paper_ledger_entries
                (id,session_id,intent_id,entry_type,asset,quantity,amount,currency,
                 idempotency_key,created_at,paper_account_id,account_generation,
                 ledger_sequence,precise_quantity,precise_amount)
            values ('a-withdrawal',?,'risk-reject','COMMISSION','cash',0,-100,'CNY',
                    'a-only-fee',?,?,1,2,0,-100)
            """,
            (first["shadow_session_id"], utc_now(), first["id"]),
        )
    first_projection = rebuild_projection(first["id"], "2026-07-26")["account"]
    second_projection = rebuild_projection(second["id"], "2026-07-26")["account"]
    assert first_projection["cash"] == "99900.00000000"
    assert second_projection["cash"] == "250000.00000000"


def test_valuation_uses_as_of_price_not_latest() -> None:
    _init()
    from app.db import db, utc_now
    from app.services.paper_accounts import rebuild_projection

    account = _account("Point in time account", "100000")
    with db() as connection:
        connection.execute(
            """
            insert into paper_ledger_entries
                (id,session_id,intent_id,entry_type,asset,symbol,quantity,amount,currency,
                 idempotency_key,created_at,paper_account_id,account_generation,
                 ledger_sequence,precise_quantity,precise_amount)
            values ('pit-position',?,'pit','POSITION_INCREASE','equity','600519',10,100,
                    'CNY','pit-position',?,?,1,2,10,100)
            """,
            (account["shadow_session_id"], utc_now(), account["id"]),
        )
        for symbol, asset_class, trade_date, close in (
            ("600519", "equity", "2024-01-02", 10),
            ("600519", "equity", "2024-01-03", 100),
            ("000300", "index", "2024-01-02", 100),
        ):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id,symbol,asset_class,market,venue,trade_date,resolution,
                     data_type,close,adjust,source,created_at)
                values (?,?,?,?,?,?,'daily','trade',?,'raw','unit',?)
                """,
                (
                    f"{asset_class}:{symbol}",
                    symbol,
                    asset_class,
                    "china",
                    "china",
                    trade_date,
                    close,
                    utc_now(),
                ),
            )
    rebuild_projection(
        account["id"],
        "2024-01-02",
        source="unit",
        allow_research_source=True,
        benchmark_start_date="2024-01-02",
    )
    with db() as connection:
        position = connection.execute(
            """
            select certified_price,quote_data_timestamp
            from paper_account_position_projections
            where paper_account_id=? and symbol='600519'
            """,
            (account["id"],),
        ).fetchone()
    assert Decimal(str(position["certified_price"])) == Decimal("10")
    assert position["quote_data_timestamp"] == "2024-01-02"


def test_projection_excludes_future_cycle_ledger_entries(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db, utc_now
    from app.services import paper_accounts

    account = _account("Ledger point in time account", "100000")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    future_cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-01-03")
    with db() as connection:
        connection.execute(
            """
            insert into paper_ledger_entries
                (id,session_id,intent_id,entry_type,asset,quantity,amount,currency,
                 idempotency_key,created_at,paper_account_id,account_generation,
                 execution_cycle_id,ledger_sequence,precise_quantity,precise_amount)
            values ('future-fee',?,'future-fee','COMMISSION','cash',0,-100,'CNY',
                    'future-fee',?,?,1,?,2,0,-100)
            """,
            (
                account["shadow_session_id"],
                utc_now(),
                account["id"],
                future_cycle["id"],
            ),
        )
        for trade_date, close in (("2024-01-02", 100), ("2024-01-03", 101)):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id,symbol,asset_class,market,venue,trade_date,resolution,
                     data_type,close,adjust,source,created_at)
                values ('index:000300','000300','index','china','china',?,'daily',
                        'trade',?,'raw','unit',?)
                """,
                (trade_date, close, utc_now()),
            )

    historical = paper_accounts.rebuild_projection(
        account["id"],
        "2024-01-02",
        source="unit",
        allow_research_source=True,
        benchmark_start_date="2024-01-02",
    )["account"]
    current = paper_accounts.rebuild_projection(
        account["id"],
        "2024-01-03",
        source="unit",
        allow_research_source=True,
        benchmark_start_date="2024-01-02",
    )["account"]

    assert historical["cash"] == "100000.00000000"
    assert historical["source_ledger_sequence"] == 1
    assert current["cash"] == "99900.00000000"
    assert current["source_ledger_sequence"] == 2


def test_excess_equals_cumulative_minus_benchmark() -> None:
    _init()
    from app.db import db, utc_now
    from app.services.paper_accounts import rebuild_projection

    account = _account("Benchmark account", "100000")
    with db() as connection:
        for trade_date, close in (("2024-01-02", 100), ("2024-01-03", 110)):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id,symbol,asset_class,market,venue,trade_date,resolution,
                     data_type,close,adjust,source,created_at)
                values ('index:000300','000300','index','china','china',?,'daily',
                        'trade',?,'raw','unit',?)
                """,
                (trade_date, close, utc_now()),
            )
    projection = rebuild_projection(
        account["id"],
        "2024-01-03",
        source="unit",
        allow_research_source=True,
        benchmark_start_date="2024-01-02",
    )["account"]
    cumulative = Decimal(projection["cumulative_return"])
    benchmark = Decimal(projection["benchmark_return"])
    excess = Decimal(projection["excess_return"])
    assert benchmark == Decimal("0.1")
    assert excess == cumulative - benchmark


def test_benchmark_missing_fails_closed() -> None:
    _init()
    from app.repositories.market_data_repository import MarketDataUnavailable
    from app.services.paper_accounts import rebuild_projection

    account = _account("Missing benchmark account")
    with pytest.raises(MarketDataUnavailable, match="market_data_unavailable"):
        rebuild_projection(
            account["id"],
            "2024-01-03",
            source="unit",
            allow_research_source=True,
            benchmark_start_date="2024-01-02",
        )


def test_market_data_repository_gates_equity_and_index_scopes_separately(monkeypatch) -> None:
    _init()
    from app.db import db, utc_now
    from app.repositories import market_data_repository

    with db() as connection:
        for symbol, asset_class, trade_date, close in (
            ("600519", "equity", "2024-01-03", 10),
            ("000300", "index", "2024-01-02", 100),
            ("000300", "index", "2024-01-03", 110),
        ):
            connection.execute(
                """
                insert into market_daily_bars
                    (instrument_id,symbol,asset_class,market,venue,trade_date,resolution,
                     data_type,close,adjust,source,created_at)
                values (?,?,?,?,?,?,'daily','trade',?,'raw','unit',?)
                """,
                (
                    f"{asset_class}:{symbol}",
                    symbol,
                    asset_class,
                    "china",
                    "china",
                    trade_date,
                    close,
                    utc_now(),
                ),
            )

    gated_asset_classes: list[str] = []

    def resolve_source_context(*_args, asset_class: str, **_kwargs) -> dict:
        gated_asset_classes.append(asset_class)
        return {"source": "unit", "datasetVersion": f"{asset_class}-v1"}

    monkeypatch.setattr(
        market_data_repository,
        "resolve_source_context",
        resolve_source_context,
    )
    market_data_repository.close_price("600519", "2024-01-03", source="unit")
    result = market_data_repository.benchmark_return(
        "000300",
        "2024-01-02",
        "2024-01-03",
        source="unit",
    )

    assert gated_asset_classes == ["equity", "index", "index"]
    assert result["return"] == Decimal("0.1")


def test_checkpoint_divergence_raises() -> None:
    _init()
    from app.db import db
    from app.services.paper_accounts import CanonicalStateDivergence, rebuild_projection

    account = _account("Diverged checkpoint account", "100000")
    with db() as connection:
        connection.execute(
            """
            update paper_ledger_entries
            set precise_amount=precise_amount-100
            where paper_account_id=? and ledger_sequence=1
            """,
            (account["id"],),
        )

    with pytest.raises(CanonicalStateDivergence, match="checkpoint_divergence"):
        rebuild_projection(account["id"], "2024-01-03")

    with db() as connection:
        status = connection.execute(
            "select status from paper_accounts where id=?",
            (account["id"],),
        ).fetchone()
    assert status["status"] == "error"


def test_projection_history_verification_rejects_checkpoint_digest_mismatch() -> None:
    _init()
    from app.db import db
    from app.services.paper_accounts import verify_projection_history

    account = _account("Invalid checkpoint digest account", "100000")
    with db() as connection:
        connection.execute(
            """
            update paper_account_checkpoints set digest='invalid'
            where paper_account_id=? and source_ledger_sequence=1
            """,
            (account["id"],),
        )

    verification = verify_projection_history(account["id"])

    assert verification["passed"] is False
    assert verification["failures"] == ["checkpoint_digest_mismatch:1"]


def test_ledger_sequence_is_unique_per_account_generation() -> None:
    _init()
    from app.db import db, utc_now

    account = _account("Unique sequence account")
    with pytest.raises(sqlite3.IntegrityError):
        with db() as connection:
            connection.execute(
                """
                insert into paper_ledger_entries
                    (id,session_id,intent_id,entry_type,asset,quantity,amount,currency,
                     idempotency_key,created_at,paper_account_id,account_generation,
                     ledger_sequence,precise_quantity,precise_amount)
                values ('duplicate-sequence',?,'duplicate-sequence','COMMISSION','cash',
                        0,-1,'CNY','duplicate-sequence',?,?,1,1,0,-1)
                """,
                (account["shadow_session_id"], utc_now(), account["id"]),
            )


def test_daily_report_persists_projection_benchmark_without_zero_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Daily report benchmark account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    projection = paper_accounts.get_overview(account["id"])

    paper_accounts._write_daily_report(cycle["id"], projection)

    with db() as connection:
        snapshot = connection.execute(
            """
            select benchmark_symbol,benchmark_return,source_ledger_sequence,
                   source_checkpoint_digest
            from paper_account_daily_snapshots
            where paper_account_id=? and generation=1 and trading_date='2024-02-01'
            """,
            (account["id"],),
        ).fetchone()
    assert snapshot["benchmark_symbol"] == "000300"
    assert Decimal(str(snapshot["benchmark_return"])) == Decimal(
        projection["account"]["benchmark_return"]
    )
    assert snapshot["source_ledger_sequence"] == projection["account"]["source_ledger_sequence"]
    assert snapshot["source_checkpoint_digest"] == projection["account"]["source_checkpoint_digest"]


def test_ledger_is_append_only() -> None:
    _init()
    from app.db import db
    from app.services.paper_order_pipeline import (
        append_transition,
        record_fill_and_ledger,
        record_intent,
    )

    account = _account("Append only account")
    with db() as connection:
        opening_before = dict(
            connection.execute(
                """
                select * from paper_ledger_entries
                where paper_account_id=? and ledger_sequence=1
                """,
                (account["id"],),
            ).fetchone()
        )
    intent = record_intent(
        session_id=account["shadow_session_id"],
        paper_run_id="append-only-run",
        backtest_run_id="append-only-backtest",
        event_key="append-only-order",
        trade_date="2024-01-03",
        symbol="600519",
        side="buy",
        quantity=10,
        requested_price=10,
        raw_intent={},
        paper_account_id=account["id"],
        deployment_id="append-only-deployment",
        execution_cycle_id="append-only-cycle",
        account_generation=1,
    )
    for state, event in (
        ("VALIDATION_PENDING", "validation"),
        ("ACCEPTED", "accepted"),
        ("MATCHING", "matching"),
    ):
        append_transition(
            intent["id"],
            state,
            event_type=event,
            idempotency_key=event,
        )
    record_fill_and_ledger(
        intent["id"],
        external_fill_key="append-only-fill",
        trade_date="2024-01-03",
        quantity=Decimal("10"),
        price=Decimal("10"),
        fee=Decimal("1"),
        paper_account_id=account["id"],
        account_generation=1,
        execution_cycle_id="append-only-cycle",
    )
    with db() as connection:
        opening_after = dict(
            connection.execute(
                "select * from paper_ledger_entries where id=?",
                (opening_before["id"],),
            ).fetchone()
        )
        appended = connection.execute(
            """
            select account_generation,execution_cycle_id,ledger_sequence,
                   precise_quantity,precise_amount
            from paper_ledger_entries
            where paper_account_id=? and ledger_sequence>1
            order by ledger_sequence
            """,
            (account["id"],),
        ).fetchall()
    assert opening_after == opening_before
    assert [row["ledger_sequence"] for row in appended] == [2, 3, 4]
    assert all(row["account_generation"] == 1 for row in appended)
    assert all(row["execution_cycle_id"] == "append-only-cycle" for row in appended)
    assert all(row["precise_quantity"] is not None for row in appended)
    assert all(row["precise_amount"] is not None for row in appended)


def test_deployment_is_frozen_versioned_and_cycle_is_idempotent(tmp_path, monkeypatch) -> None:
    _init()
    from app.services.paper_accounts import ensure_cycle, get_deployment

    account = _account("Account A")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    assert deployment["strategy_fingerprint"] == "strategy-sha"
    assert deployment["dataset_version_id"] == "dataset-v1"
    assert len(deployment["deployment_fingerprint"]) == 64
    same = get_deployment(deployment["id"])
    assert same["parameters"]["strategySnapshotHash"] == "strategy-sha"
    assert same["parameters"]["maxPositions"] == 10
    assert same["parameters"]["maxPositionWeight"] == "0.2"
    assert same["parameters"]["minCash"] == "50000"

    first = ensure_cycle(deployment["id"], "2024-02-01")
    duplicate = ensure_cycle(deployment["id"], "2024-02-01")
    assert first["id"] == duplicate["id"]
    assert first["idempotency_key"] == duplicate["idempotency_key"]


def test_signal_only_deployment_uses_isolated_non_ledger_session(tmp_path, monkeypatch) -> None:
    _init()
    from app.services.paper_accounts import get_account
    from app.services.paper import get_session

    account = _account("Account A")
    primary = _deployment(account["id"], tmp_path, monkeypatch)
    account_session = get_session(get_account(account["id"])["shadow_session_id"])
    signal_only = _deployment(account["id"], tmp_path, monkeypatch, signal_mode="signal_only")
    signal_session_id = signal_only["parameters"]["_deploymentShadowSessionId"]
    signal_session = get_session(signal_session_id)

    assert primary["signal_mode"] == "paper_execute"
    assert account_session["mode"] == "lean_walkforward_v2"
    assert signal_session_id != account["shadow_session_id"]
    assert signal_session["mode"] == "lean_walkforward"
    assert signal_session["parameters"]["signalOnly"] is True


def test_account_and_deployment_state_transitions(tmp_path, monkeypatch) -> None:
    _init()
    from app.services.paper_accounts import transition_account, transition_deployment

    account = _account("Account A")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    assert transition_account(account["id"], "activate")["status"] == "active"
    assert transition_deployment(deployment["id"], "pause")["status"] == "paused"
    assert transition_deployment(deployment["id"], "resume")["status"] == "active"
    assert transition_account(account["id"], "pause")["status"] == "paused"
    assert transition_account(account["id"], "archive")["status"] == "archived"
    with pytest.raises(ValueError, match="Archived"):
        transition_account(account["id"], "resume")


def test_clone_has_independent_opening_ledger_without_history() -> None:
    _init()
    from app.db import db
    from app.services.paper_accounts import clone_account

    source = _account("Source", "500000")
    clone = clone_account(source["id"], {"name": "Clone"})
    assert clone["id"] != source["id"]
    assert clone["shadow_session_id"] != source["shadow_session_id"]
    assert clone["cash"] == source["cash"]
    with db() as connection:
        source_entries = connection.execute(
            "select count(*) as count from paper_ledger_entries where paper_account_id=?",
            (source["id"],),
        ).fetchone()
        clone_entries = connection.execute(
            "select count(*) as count from paper_ledger_entries where paper_account_id=?",
            (clone["id"],),
        ).fetchone()
    assert source_entries["count"] == 1
    assert clone_entries["count"] == 1


def test_no_signal_is_observed_not_failed(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Account A")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    with db() as connection:
        signals = paper_accounts._signals_from_intents(connection, cycle, [])
    assert signals == [
        {
            "id": signals[0]["id"],
            "signal_type": "no_signal",
            "disposition": "observed",
            "no_trade_reason": "no_signal",
        }
    ]
    listed = paper_accounts.list_signals(account["id"])
    assert listed["items"][0]["no_trade_reason"] == "no_signal"


def test_compare_refuses_silent_cross_currency_merge(monkeypatch) -> None:
    _init()
    from app.services import paper_accounts

    first = _account("Account A")
    second = _account("Account B")
    original = paper_accounts.get_account

    def get_account(account_id: str):
        item = original(account_id)
        if account_id == second["id"]:
            item["base_currency"] = "USD"
        return item

    monkeypatch.setattr(paper_accounts, "get_account", get_account)
    comparison = paper_accounts.compare_accounts([first["id"], second["id"]])
    assert comparison["comparable"] is False
    assert comparison["reason"] == "currency_mismatch"


def test_duplicate_beat_dispatch_creates_one_cycle(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db, utc_now
    from app.services import paper_accounts
    from app.tasks import worker

    account = _account("Scheduled Account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    paper_accounts.transition_account(account["id"], "activate")
    with db() as connection:
        connection.execute(
            "update paper_strategy_deployments set next_scheduled_at=? where id=?",
            ("2024-01-01T00:00:00+00:00", deployment["id"]),
        )
    dispatched: list[str] = []

    class Result:
        id = "celery-cycle"

    monkeypatch.setattr(
        worker.run_paper_execution_cycle_task,
        "apply_async",
        lambda args: dispatched.append(args[0]) or Result(),
    )
    first = paper_accounts.schedule_due_deployments()
    second = paper_accounts.schedule_due_deployments()
    assert len(first["queued"]) == 1
    assert second["queued"] == []
    assert dispatched == first["queued"]
    with db() as connection:
        count = connection.execute(
            "select count(*) as count from paper_execution_cycles where deployment_id=?",
            (deployment["id"],),
        ).fetchone()
    assert count["count"] == 1


def test_data_gate_waiting_does_not_mutate_account_ledger(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Waiting Account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    paper_accounts.transition_cycle(
        cycle["id"],
        "queued",
        event_type="test_queued",
        expected={"scheduled"},
    )
    monkeypatch.setattr(
        paper_accounts.paper_runtime,
        "create_walkforward_run",
        lambda *_args: (_ for _ in ()).throw(ValueError("qa failed: data watermark missing")),
    )
    waiting = paper_accounts.begin_cycle(cycle["id"])
    assert waiting["status"] == "waiting_data"
    assert waiting["failure_code"] == "data_not_ready"
    with db() as connection:
        ledger = connection.execute(
            "select count(*) as count from paper_ledger_entries where paper_account_id=?",
            (account["id"],),
        ).fetchone()
    assert ledger["count"] == 1


def test_orphan_recovery_finalizes_successful_lean_run(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Recovery Account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    paper_accounts.transition_cycle(
        cycle["id"],
        "running",
        event_type="worker_started",
        expected={"scheduled"},
        fields={"paper_run_id": "paper-run-1", "updated_at": "2020-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        paper_accounts.paper_runtime,
        "get_walkforward_run",
        lambda _run_id: {"id": "paper-run-1", "status": "success"},
    )
    finalized: list[str] = []
    monkeypatch.setattr(
        paper_accounts,
        "finalize_cycle",
        lambda cycle_id: finalized.append(cycle_id) or {"id": cycle_id, "status": "succeeded"},
    )
    recovered = paper_accounts.recover_orphaned_cycles(stale_minutes=1)
    assert recovered["recovered"] == [cycle["id"]]
    assert finalized == [cycle["id"]]


def test_orphan_recovery_fails_closed_when_restricted_runner_failed(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Failed Recovery Account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    paper_accounts.transition_cycle(
        cycle["id"],
        "running",
        event_type="worker_started",
        expected={"scheduled"},
        fields={"paper_run_id": "paper-run-failed", "updated_at": "2020-01-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(
        paper_accounts.paper_runtime,
        "get_walkforward_run",
        lambda _run_id: {
            "id": "paper-run-failed",
            "status": "running",
            "backtest_run_id": "backtest-failed",
        },
    )
    monkeypatch.setattr(
        paper_accounts,
        "get_backtest",
        lambda _run_id: {"id": "backtest-failed", "status": "running"},
    )
    failed_runs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        paper_accounts.paper_runtime,
        "fail_walkforward_run",
        lambda run_id, error: failed_runs.append((run_id, error)) or {},
    )
    with db() as connection:
        connection.execute(
            """
            insert into restricted_runner_jobs
                (id,run_id,spec_digest,image_digest,command_json,mounts_json,
                 resource_limits_json,network_policy,status,exit_code,error,created_at)
            values ('runner-failed','backtest-failed','digest','image','[]','[]',
                    '{}','none','failed',1,'runner interrupted','2020-01-01T00:00:00+00:00')
            """
        )
    recovered = paper_accounts.recover_orphaned_cycles(stale_minutes=1)
    assert recovered["failed"] == [cycle["id"]]
    assert failed_runs == [("paper-run-failed", "runner interrupted")]
    failed_cycle = paper_accounts.get_cycle(cycle["id"])
    assert failed_cycle["status"] == "failed"
    assert failed_cycle["failure_code"] == "orphaned_lean_run"


def test_orphan_recovery_resumes_postprocessing_after_runner_success(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Postprocessing Recovery Account")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    paper_accounts.transition_cycle(
        cycle["id"],
        "running",
        event_type="worker_started",
        expected={"scheduled"},
        fields={"paper_run_id": "paper-run-resume", "updated_at": "2020-01-01T00:00:00+00:00"},
    )
    paper_run = {
        "id": "paper-run-resume",
        "status": "running",
        "task_id": "backtest-task-resume",
        "backtest_run_id": "backtest-resume",
    }
    monkeypatch.setattr(
        paper_accounts.paper_runtime,
        "get_walkforward_run",
        lambda _run_id: paper_run,
    )
    monkeypatch.setattr(
        paper_accounts,
        "get_backtest",
        lambda _run_id: {"id": "backtest-resume", "status": "running"},
    )
    resumed: list[dict] = []
    monkeypatch.setattr(
        paper_accounts,
        "_resume_interrupted_backtest",
        lambda item: resumed.append(item) or "replacement-task",
    )
    with db() as connection:
        connection.execute(
            """
            insert into restricted_runner_jobs
                (id,run_id,spec_digest,image_digest,command_json,mounts_json,
                 resource_limits_json,network_policy,status,exit_code,created_at,finished_at)
            values ('runner-success','backtest-resume','digest','image','[]','[]',
                    '{}','none','success',0,'2020-01-01T00:00:00+00:00',
                    '2020-01-01T00:01:00+00:00')
            """
        )
    recovered = paper_accounts.recover_orphaned_cycles(stale_minutes=1)

    assert recovered == {"recovered": [], "resumed": [cycle["id"]], "failed": []}
    assert resumed == [paper_run]
    current = paper_accounts.get_cycle(cycle["id"])
    assert current["status"] == "running"
    with db() as connection:
        event = connection.execute(
            """
            select event_type,payload_json from paper_execution_cycle_events
            where cycle_id=? order by sequence desc limit 1
            """,
            (cycle["id"],),
        ).fetchone()
    assert event["event_type"] == "lean_postprocessing_recovered"
    assert "replacement-task" in event["payload_json"]


def test_backend_restart_preserves_run_with_successful_delegated_runner() -> None:
    _init()
    from app.db import db, init_db, utc_now

    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into tasks
                (id,kind,status,title,parameters_json,log_path,created_at)
            values ('restart-task','backtest','running','Restart recovery','{}','/tmp/restart.log',?)
            """,
            (now,),
        )
        connection.execute(
            """
            insert into backtest_runs
                (id,task_id,symbol,asset_class,venue,resolution,data_type,parameters_json,
                 status,docker_image,results_dir,created_at)
            values ('restart-run','restart-task','600519','equity','china','daily','trade',
                    '{}','running','lean:test','/tmp/restart-results',?)
            """,
            (now,),
        )
        connection.execute(
            """
            insert into restricted_runner_jobs
                (id,run_id,spec_digest,image_digest,command_json,mounts_json,
                 resource_limits_json,network_policy,status,exit_code,created_at,finished_at)
            values ('restart-runner','restart-run','digest','image','[]','[]','{}','none',
                    'success',0,?,?)
            """,
            (now, now),
        )

    init_db()

    with db() as connection:
        task = connection.execute("select status,error from tasks where id='restart-task'").fetchone()
        run = connection.execute("select status,error from backtest_runs where id='restart-run'").fetchone()
    assert dict(task) == {"status": "running", "error": None}
    assert dict(run) == {"status": "running", "error": None}


def test_paper_account_api_validates_lifecycle() -> None:
    _init()
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/paper/accounts",
        json={
            "name": "API Account",
            "initialCash": "1000000.00",
            "marketScope": "china",
            "baseCurrency": "CNY",
            "benchmarkSymbol": "000300",
            "riskConfig": {},
        },
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    listed = client.get("/api/paper/accounts", params={"keyword": "API Account"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert client.get(f"/api/paper/accounts/{account_id}/overview").status_code == 200
    activate = client.post(f"/api/paper/accounts/{account_id}/activate")
    assert activate.status_code == 409
    assert "deployment" in activate.json()["detail"].lower()


def test_paused_accounts_expose_data_trust_flag() -> None:
    _init()
    from app.main import app
    from app.services.paper_accounts import pause_accounts_for_data_trust

    first = _account("Trust Account A")
    second = _account("Trust Account B")
    paused = pause_accounts_for_data_trust()
    assert paused["pausedCount"] == 2
    assert paused["dataTrust"] == {
        "valuationTrusted": False,
        "reason": "historical_recertification_pending",
    }

    client = TestClient(app)
    listed = client.get("/api/paper/accounts")
    overview = client.get(f"/api/paper/accounts/{first['id']}/overview")
    performance = client.get(f"/api/paper/accounts/{first['id']}/performance")
    comparison = client.get("/api/paper/accounts/compare", params=[("accountId", first["id"]), ("accountId", second["id"])])

    for response in (listed, overview, performance, comparison):
        assert response.status_code == 200
        assert response.json()["dataTrust"] == {
            "valuationTrusted": False,
            "reason": "historical_recertification_pending",
        }
    assert all(item["status"] == "paused" for item in listed.json()["items"])


def test_paper_account_delete_cascades_stopped_account_records() -> None:
    _init()
    from app.db import db
    from app.main import app

    client = TestClient(app)
    created = client.post(
        "/api/paper/accounts",
        json={
            "name": "Delete Account",
            "initialCash": "1000000.00",
            "marketScope": "china",
            "baseCurrency": "CNY",
            "benchmarkSymbol": "000300",
            "riskConfig": {},
        },
    )
    assert created.status_code == 201
    account = created.json()

    deleted = client.delete(f"/api/paper/accounts/{account['id']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": account["id"]}
    assert client.get(f"/api/paper/accounts/{account['id']}").status_code == 404

    with db() as connection:
        assert connection.execute(
            "select count(*) as count from paper_sessions where id=?",
            (account["shadow_session_id"],),
        ).fetchone()["count"] == 0
        assert connection.execute(
            "select count(*) as count from paper_ledger_entries where paper_account_id=?",
            (account["id"],),
        ).fetchone()["count"] == 0


def test_paper_account_delete_rejects_active_account() -> None:
    _init()
    from app.db import db, utc_now
    from app.main import app

    account = _account("Active Delete Account")
    with db() as connection:
        connection.execute(
            "update paper_accounts set status='active',updated_at=? where id=?",
            (utc_now(), account["id"]),
        )

    response = TestClient(app).delete(f"/api/paper/accounts/{account['id']}")
    assert response.status_code == 409
    assert "paused or archived" in response.json()["detail"]


def test_paper_account_delete_cascades_deployment_and_terminal_cycle(tmp_path, monkeypatch) -> None:
    _init()
    from app.db import db
    from app.services import paper_accounts

    account = _account("Delete Account With History")
    deployment = _deployment(account["id"], tmp_path, monkeypatch)
    cycle = paper_accounts.ensure_cycle(deployment["id"], "2024-02-01")
    paper_accounts.transition_cycle(
        cycle["id"],
        "failed",
        event_type="test_terminal_failure",
        expected={"scheduled"},
        fields={"failure_code": "test", "failure_detail": "terminal test cycle"},
    )

    assert paper_accounts.delete_account(account["id"])["deleted"] is True
    with db() as connection:
        for table in (
            "paper_execution_cycle_events",
            "paper_execution_cycles",
            "paper_strategy_deployments",
            "paper_accounts",
        ):
            assert connection.execute(f"select count(*) as count from {table}").fetchone()["count"] == 0
