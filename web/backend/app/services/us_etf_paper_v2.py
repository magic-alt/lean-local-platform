from __future__ import annotations

import uuid
from typing import Any, Mapping

from ..db import db, json_dump, row_to_dict, utc_now
from ..repositories.backtest_repository import get_backtest, get_result
from .experiments import get_experiment_versions
from .run_paths import run_directory
from .trading_calendar import next_trade_date
from . import paper as paper_service
from . import paper_order_pipeline


POLICY_VERSION = "us-etf-paper-v2.1"
CURRENCY = "USD"
SUPPORTED_TEMPLATE = "etf_rotation"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_context(source_backtest_id: str, project_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Any]:
    source_run = get_backtest(source_backtest_id)
    if not source_run or _text(source_run.get("project_id")) != project_id:
        raise ValueError("The selected backtest does not belong to this project.")
    if (
        source_run.get("status") != "success"
        or source_run.get("trust_status") != "trusted"
        or (source_run.get("validation") or {}).get("passed") is not True
    ):
        raise ValueError("The selected backtest has not passed execution validation.")
    source_parameters = dict(source_run.get("parameters") or {})
    if _text(source_parameters.get("strategyTemplateKey")) != SUPPORTED_TEMPLATE:
        raise ValueError("U.S. ETF Paper-v2 accepts the certified etf_rotation template only.")
    if source_parameters.get("allowResearchSource"):
        raise ValueError("Research-source backtests cannot seed U.S. ETF Paper-v2.")
    source_fingerprint = dict(source_run.get("fingerprint") or {})
    certification = dict(source_fingerprint.get("datasetCertification") or {})
    if not (
        certification.get("isProduction")
        and certification.get("isCertified")
        and certification.get("environment") == "production"
        and _text(certification.get("qaStatus")).lower() == "ok"
    ):
        raise ValueError("U.S. ETF Paper-v2 requires a certified production dataset.")
    if source_parameters.get("allowTruncatedData") or ((source_run.get("validation") or {}).get("data") or {}).get("truncated"):
        raise ValueError("Truncated backtests cannot seed U.S. ETF Paper-v2.")
    if _text(source_run.get("asset_class") or source_parameters.get("assetClass") or "equity") != "equity":
        raise ValueError("U.S. ETF Paper-v2 supports equity/ETF sources only.")
    venue = _text(source_run.get("venue") or source_parameters.get("venue") or source_parameters.get("market")).lower()
    if venue != "usa" or _text(source_run.get("resolution") or source_parameters.get("resolution")).lower() != "daily":
        raise ValueError("U.S. ETF Paper-v2 supports market=usa, resolution=daily only.")
    source_result = get_result(source_backtest_id)
    if not source_result:
        raise ValueError("The selected backtest result ledger is unavailable.")
    snapshot_dir = run_directory(
        source_backtest_id,
        source_parameters.get("strategySnapshotDir"),
        relative="strategy",
    )
    if not snapshot_dir.is_dir():
        raise ValueError("The selected backtest strategy snapshot is unavailable.")
    return source_run, source_result, source_parameters, snapshot_dir


def create_session(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if _text(parameters.get("mode") or "lean_walkforward_v2") != "lean_walkforward_v2":
        raise ValueError("U.S. ETF certification uses lean_walkforward_v2 only.")
    project_id = _text(parameters.get("projectId"))
    source_backtest_id = _text(parameters.get("sourceBacktestId"))
    if not project_id or not source_backtest_id:
        raise ValueError("U.S. ETF Paper-v2 requires projectId and sourceBacktestId.")
    source_run, source_result, source_parameters, snapshot_dir = _source_context(
        source_backtest_id,
        project_id,
    )
    cash = float(source_parameters.get("cash") or source_parameters.get("initialCash") or 100000)
    source_holdings = [
        dict(item)
        for item in (source_result.get("holdings") or [])
        if isinstance(item, dict)
    ]
    source_equity = paper_service._last_equity(source_result, cash)
    source_market_value = sum(
        float(
            item.get("marketValue")
            or item.get("market_value")
            or (
                float(item.get("quantity") or item.get("Quantity") or 0)
                * float(item.get("price") or item.get("Price") or item.get("marketPrice") or 0)
            )
        )
        for item in source_holdings
    )
    initial_cash = max(0.0, source_equity - source_market_value)
    start_date = _text(parameters.get("startDate")) or next_trade_date(
        "usa",
        _text(source_parameters.get("end")),
    )
    if paper_service.parse_date(start_date) <= paper_service.parse_date(_text(source_parameters.get("end"))):
        raise ValueError("Paper startDate must be after the source backtest end date.")
    versions = get_experiment_versions(source_backtest_id) or {}
    experiment = dict(versions.get("experiment") or {})
    source_fingerprint = dict(source_run.get("fingerprint") or {})
    certification = dict(source_fingerprint.get("datasetCertification") or {})
    commission = float(source_parameters.get("commissionPerOrder") or 1.0)
    if commission < 0:
        raise ValueError("commissionPerOrder must be non-negative.")
    frozen = {
        **source_parameters,
        **{
            key: parameters[key]
            for key in (
                "maxPositions",
                "maxPositionWeight",
                "maxOrderAmount",
                "maxDailyTurnover",
                "minCash",
                "blacklist",
                "watchlist",
                "observeOnlySymbols",
            )
            if key in parameters
        },
        "market": "usa",
        "venue": "usa",
        "currency": CURRENCY,
        "paperMarketPolicy": POLICY_VERSION,
        "executionPolicy": "next_open",
        "sourceBacktestId": source_backtest_id,
        "strategySnapshotDir": str(snapshot_dir),
        "strategySnapshotMainFile": source_parameters.get("strategySnapshotMainFile"),
        "strategySnapshotAlgorithmClass": source_parameters.get("strategySnapshotAlgorithmClass"),
        "strategySnapshotLanguage": source_parameters.get("strategySnapshotLanguage"),
        "strategySnapshotHash": source_parameters.get("strategySnapshotHash")
        or source_parameters.get("strategyFingerprint"),
        "datasetVersion": certification.get("datasetVersion") or certification.get("id"),
        "universeVersion": (source_fingerprint.get("universe") or {}).get("version")
        if isinstance(source_fingerprint.get("universe"), dict)
        else source_fingerprint.get("universeVersion"),
        # The existing generic worker risk helper calls paper._fee().  Map its
        # non-HK fee knobs to the same constant-per-order U.S. commission so
        # cash-floor validation and the immutable ledger use the same cost.
        "commissionPerOrder": commission,
        "commissionRate": 0.0,
        "minCommission": commission,
        "stampTaxSell": 0.0,
        "transferFeeRate": 0.0,
    }
    session_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_sessions
                (id, project_id, name, status, symbol, asset_class, venue, resolution, cash, equity,
                 parameters_json, created_at, updated_at, mode, legacy_read_only, source_backtest_id,
                 strategy_version_id, parameter_hash, start_date, auto_advance, pipeline_version)
            values (?, ?, ?, ?, ?, 'equity', 'usa', 'daily', ?, ?, ?, ?, ?, 'lean_walkforward_v2',
                    0, ?, ?, ?, ?, 0, 2)
            """,
            (
                session_id,
                project_id,
                parameters.get("name") or f"{source_run['symbol']} U.S. ETF Paper Certification",
                "created",
                source_run["symbol"],
                initial_cash,
                source_equity,
                json_dump(frozen),
                now,
                now,
                source_backtest_id,
                experiment.get("strategy_version_id"),
                experiment.get("parameter_hash"),
                start_date,
            ),
        )
        for holding in source_holdings:
            symbol = _text(holding.get("symbol") or holding.get("Symbol") or source_run["symbol"]).upper()
            quantity = float(holding.get("quantity") or holding.get("Quantity") or 0)
            if not symbol or quantity == 0:
                continue
            average = float(
                holding.get("averagePrice")
                or holding.get("average_price")
                or holding.get("price")
                or holding.get("marketPrice")
                or 0
            )
            market_price = float(
                holding.get("marketPrice")
                or holding.get("price")
                or holding.get("Price")
                or average
            )
            connection.execute(
                """
                insert into paper_positions
                    (session_id,symbol,quantity,average_price,market_price,market_value,last_buy_date,updated_at)
                values (?,?,?,?,?,?,?,?)
                on conflict(session_id,symbol) do update set
                    quantity=excluded.quantity,average_price=excluded.average_price,
                    market_price=excluded.market_price,market_value=excluded.market_value,
                    last_buy_date=excluded.last_buy_date,updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    symbol,
                    quantity,
                    average,
                    market_price,
                    quantity * market_price,
                    _text(source_parameters.get("end")) or None,
                    now,
                ),
            )
    return paper_service.get_session(session_id) or {}


def create_walkforward_run(session_id: str, trade_date: str) -> dict[str, Any]:
    session = paper_service.get_session(session_id)
    if not session or _text((session.get("parameters") or {}).get("paperMarketPolicy")) != POLICY_VERSION:
        raise ValueError("Session is not a U.S. ETF Paper-v2 certification session.")
    return paper_service.create_walkforward_run(session_id, trade_date)


def _commission(session: Mapping[str, Any]) -> float:
    return max(0.0, float((session.get("parameters") or {}).get("commissionPerOrder") or 0.0))


def _pending(intent_id: str) -> None:
    state = paper_order_pipeline.current_state(intent_id)
    if state in {"FILLED", "REJECTED", "CANCELLED", "EXPIRED", "FAILED"}:
        paper_order_pipeline.append_transition(
            intent_id,
            "RECONCILIATION_PENDING",
            event_type="ledger_projected",
            idempotency_key="reconciliation_pending",
        )


def _process_orders(
    *,
    session: dict[str, Any],
    paper_run: dict[str, Any],
    child: dict[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    paper_order_pipeline.ensure_opening_ledger(
        session_id=str(session["id"]),
        cash=float(session.get("cash") or 0),
        positions=paper_service.list_positions(str(session["id"])),
        currency=CURRENCY,
    )
    paper_service._apply_v2_ledger_projection(str(session["id"]), str(paper_run["trade_date"]))
    session = paper_service.get_session(str(session["id"])) or session
    projected_orders: list[dict[str, Any]] = []
    intents: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    fill_keys: list[str] = []
    for raw_order in orders:
        event_key = paper_service._order_event_key(raw_order)
        price = float(raw_order.get("price") or raw_order.get("fillPrice") or 0)
        intent = paper_order_pipeline.record_intent(
            session_id=str(session["id"]),
            paper_run_id=str(paper_run["id"]),
            backtest_run_id=str(child["id"]),
            event_key=event_key,
            trade_date=paper_service._order_trade_date(raw_order),
            symbol=_text(raw_order.get("symbol") or session["symbol"]).upper(),
            side=_text(raw_order.get("side")).lower(),
            quantity=abs(float(raw_order.get("quantity") or 0)),
            requested_price=price,
            raw_intent={**raw_order, "certificationMarketPolicy": POLICY_VERSION},
            attempt=1,
            lean_order_id=_text(raw_order.get("orderId") or raw_order.get("id") or raw_order.get("order_id") or event_key),
            project_snapshot_id=_text((session.get("parameters") or {}).get("strategySnapshotDir")) or None,
            project_snapshot_hash=_text((session.get("parameters") or {}).get("strategySnapshotHash") or (session.get("parameters") or {}).get("parameterHash")) or None,
            strategy_fingerprint=paper_service._strategy_fingerprint(child),
            order_type=_text(raw_order.get("orderType") or raw_order.get("type") or "market").lower(),
            limit_price=raw_order.get("limitPrice"),
            stop_price=raw_order.get("stopPrice"),
            signal_time=_text(raw_order.get("signalTime") or raw_order.get("time")) or None,
            requested_execution_time=_text(raw_order.get("requestedExecutionTime") or raw_order.get("time")) or None,
            dataset_version=_text((session.get("parameters") or {}).get("datasetVersion")) or None,
            universe_version=_text((session.get("parameters") or {}).get("universeVersion")) or None,
            constraint_version=POLICY_VERSION,
        )
        intents.append(intent)
        state = paper_order_pipeline.current_state(str(intent["id"]))
        if state != "INTENT_CREATED":
            with db() as connection:
                existing = connection.execute("select * from paper_orders where id=?", (intent["id"],)).fetchone()
            if not existing:
                raise ValueError(f"Intent {intent['id']} is {state} without a Paper order projection.")
            projected_orders.append(row_to_dict(existing) or {})
            continue
        paper_order_pipeline.append_transition(
            str(intent["id"]),
            "VALIDATION_PENDING",
            event_type="constraint_validation_started",
            idempotency_key="validation_pending",
        )
        session = paper_service.get_session(str(session["id"])) or session
        reason = paper_service._lean_intent_rejection(
            session,
            raw_order,
            str(intent["trade_date"]),
        )
        paper_order_pipeline.record_constraint_decision(
            str(intent["id"]),
            decision="REJECT" if reason else "ACCEPT",
            constraint_version=POLICY_VERSION,
            rule_code=reason,
            rule_inputs={
                "tradeDate": intent["trade_date"],
                "symbol": intent["symbol"],
                "side": intent["side"],
                "quantity": intent["quantity"],
                "requestedPrice": intent.get("requested_price"),
                "currency": CURRENCY,
            },
            portfolio_snapshot={
                "cash": float(session.get("cash") or 0),
                "equity": float(session.get("equity") or 0),
                "positions": paper_service.list_positions(str(session["id"])),
            },
            reference_data_version=_text(intent.get("dataset_version")) or "UNVERSIONED",
            rules=[{"code": reason or "all_rules_passed", "decision": "REJECT" if reason else "ACCEPT"}],
        )
        if reason:
            paper_order_pipeline.append_transition(
                str(intent["id"]),
                "REJECTED",
                event_type="constraint_rejected",
                idempotency_key="constraint_result",
                payload={"reason": reason, "marketPolicy": POLICY_VERSION},
            )
            projected_orders.append(
                paper_service._project_v2_order(
                    session,
                    intent,
                    status="rejected",
                    reason=reason,
                    price=price,
                    fee=0,
                    trade_date=str(intent["trade_date"]),
                )
            )
            _pending(str(intent["id"]))
            decisions.append({"intentId": intent["id"], "accepted": False, "reason": reason})
            continue
        paper_order_pipeline.append_transition(
            str(intent["id"]),
            "ACCEPTED",
            event_type="constraint_accepted",
            idempotency_key="constraint_result",
        )
        paper_order_pipeline.append_transition(
            str(intent["id"]),
            "MATCHING",
            event_type="lean_match_submitted",
            idempotency_key="matching",
        )
        matched_price, no_fill_reason = paper_service._deterministic_v2_match_price(session, intent)
        if matched_price is None:
            paper_order_pipeline.append_transition(
                str(intent["id"]),
                "EXPIRED",
                event_type="paper_match_no_fill",
                idempotency_key="matching_result",
                payload={"reason": no_fill_reason, "marketPolicy": POLICY_VERSION},
            )
            projected_orders.append(
                paper_service._project_v2_order(
                    session,
                    intent,
                    status="expired",
                    reason=no_fill_reason,
                    price=price,
                    fee=0,
                    trade_date=str(intent["trade_date"]),
                )
            )
            _pending(str(intent["id"]))
            decisions.append({"intentId": intent["id"], "accepted": True, "reason": no_fill_reason})
            continue
        quantity = float(intent["quantity"])
        commission = _commission(session)
        fill_key = f"{event_key}:fill"
        paper_order_pipeline.record_fill_and_ledger(
            str(intent["id"]),
            external_fill_key=fill_key,
            trade_date=str(intent["trade_date"]),
            quantity=quantity,
            price=matched_price,
            fee=commission,
            tax=0.0,
            slippage=0.0,
            fee_model_version="us-etf-constant-commission-v1",
            matching_contract="next_open-v1",
            payload={**raw_order, "marketPolicy": POLICY_VERSION},
            currency=CURRENCY,
        )
        paper_service._apply_v2_ledger_projection(str(session["id"]), str(intent["trade_date"]))
        session = paper_service.get_session(str(session["id"])) or session
        paper_order_pipeline.append_transition(
            str(intent["id"]),
            "FILLED",
            event_type="lean_fill_recorded",
            idempotency_key="filled",
            payload={
                "fillKey": fill_key,
                "quantity": quantity,
                "price": matched_price,
                "fee": commission,
                "tax": 0.0,
                "slippage": 0.0,
                "currency": CURRENCY,
                "matchingContract": "next_open-v1",
                "marketPolicy": POLICY_VERSION,
            },
        )
        projected_orders.append(
            paper_service._project_v2_order(
                session,
                intent,
                status="filled",
                reason=None,
                price=matched_price,
                fee=commission,
                trade_date=str(intent["trade_date"]),
            )
        )
        _pending(str(intent["id"]))
        fill_keys.append(fill_key)
        decisions.append({"intentId": intent["id"], "accepted": True, "reason": None})
    paper_order_pipeline.complete_checkpoint(str(paper_run["id"]), "intent_capture", {"eventKeys": [paper_service._order_event_key(item) for item in orders]})
    paper_order_pipeline.complete_checkpoint(str(paper_run["id"]), "constraint_validation", {"decisions": decisions})
    paper_order_pipeline.complete_checkpoint(str(paper_run["id"]), "matching", {"fillKeys": fill_keys})
    paper_order_pipeline.complete_checkpoint(str(paper_run["id"]), "ledger", {"projectedOrderIds": [item["id"] for item in projected_orders]})
    return {"orders": projected_orders, "intents": intents}


def _write_snapshot_report(
    *,
    session: dict[str, Any],
    paper_run: dict[str, Any],
    child: dict[str, Any],
    orders: list[dict[str, Any]],
) -> dict[str, Any]:
    trade_date = str(paper_run["trade_date"])
    holdings = paper_service.list_positions(str(session["id"]))
    market_value = 0.0
    for holding in holdings:
        bar = paper_service._execution_bar(session, str(holding["symbol"]), trade_date)
        market_price = float((bar or {}).get("close") or holding.get("market_price") or holding.get("average_price") or 0)
        holding["market_price"] = market_price
        holding["market_value"] = float(holding["quantity"]) * market_price
        market_value += float(holding["market_value"])
    session = paper_service.get_session(str(session["id"])) or session
    cash = float(session.get("cash") or 0)
    equity = cash + market_value
    rejects = [item for item in orders if item.get("status") == "rejected"]
    fills = [item for item in orders if item.get("status") == "filled"]
    snapshot = {
        "sessionId": session["id"],
        "tradeDate": trade_date,
        "cash": cash,
        "marketValue": market_value,
        "equity": equity,
        "currency": CURRENCY,
        "positions": holdings,
        "backtestRunId": child["id"],
        "marketPolicy": POLICY_VERSION,
    }
    report = {
        "schemaVersion": 2,
        "sessionId": session["id"],
        "tradeDate": trade_date,
        "NAV": equity,
        "cash": cash,
        "orders": orders,
        "trades": fills,
        "rejects": rejects,
        "positions": holdings,
        "snapshot": snapshot,
        "qa": {"passed": True, "severity": "ok"},
        "executionPolicy": "next_open",
        "currency": CURRENCY,
        "marketPolicy": POLICY_VERSION,
        "backtestRunId": child["id"],
    }
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into paper_portfolio_snapshots
                (id, session_id, trade_date, cash, market_value, equity, positions_json,
                 benchmark_symbol, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id, trade_date) do update set
                cash=excluded.cash,market_value=excluded.market_value,equity=excluded.equity,
                positions_json=excluded.positions_json,benchmark_symbol=excluded.benchmark_symbol
            """,
            (
                str(uuid.uuid4()),
                session["id"],
                trade_date,
                cash,
                market_value,
                equity,
                json_dump(holdings),
                (session.get("parameters") or {}).get("benchmarkSymbol"),
                now,
            ),
        )
        connection.execute(
            """
            insert into paper_daily_reports
                (id, session_id, trade_date, report_json, signals_json, orders_json, trades_json,
                 rejects_json, positions_json, snapshot_json, benchmark_json, qa_json, created_at)
            values (?, ?, ?, ?, '[]', ?, ?, ?, ?, ?, '{}', ?, ?)
            on conflict(session_id, trade_date) do update set
                report_json=excluded.report_json,orders_json=excluded.orders_json,
                trades_json=excluded.trades_json,rejects_json=excluded.rejects_json,
                positions_json=excluded.positions_json,snapshot_json=excluded.snapshot_json,
                qa_json=excluded.qa_json
            """,
            (
                str(uuid.uuid4()),
                session["id"],
                trade_date,
                json_dump(report),
                json_dump(orders),
                json_dump(fills),
                json_dump(rejects),
                json_dump(holdings),
                json_dump(snapshot),
                json_dump(report["qa"]),
                now,
            ),
        )
        connection.execute(
            "update paper_sessions set equity=?,updated_at=? where id=?",
            (equity, now, session["id"]),
        )
    paper_order_pipeline.complete_checkpoint(str(paper_run["id"]), "snapshot_report", {"tradeDate": trade_date})
    return {"snapshot": snapshot, "report": report}


def finalize_walkforward_run(paper_run_id: str) -> dict[str, Any]:
    paper_run = paper_service.get_walkforward_run(paper_run_id)
    if not paper_run:
        raise KeyError("Paper run not found.")
    if paper_run.get("status") == "success":
        return paper_run
    session = paper_service.get_session(str(paper_run["session_id"]))
    child = get_backtest(str(paper_run["backtest_run_id"]))
    if not session or not child:
        return paper_service.fail_walkforward_run(paper_run_id, "paper_run_context_missing")
    if _text((session.get("parameters") or {}).get("paperMarketPolicy")) != POLICY_VERSION:
        return paper_service.fail_walkforward_run(paper_run_id, "wrong_paper_market_policy")
    if child.get("status") != "success" or (child.get("validation") or {}).get("passed") is not True:
        return paper_service.fail_walkforward_run(
            paper_run_id,
            f"child_backtest_failed:{child.get('error_message') or child.get('error') or child.get('status')}",
        )
    result = get_result(str(child["id"]))
    if not result:
        return paper_service.fail_walkforward_run(paper_run_id, "child_backtest_result_missing")
    baseline_date, _prior, history = paper_service._history_reconciliation(session, child, result)
    if not history.get("passed"):
        with db() as connection:
            connection.execute(
                "update paper_walkforward_runs set reconciliation_json=? where id=?",
                (json_dump(history), paper_run_id),
            )
        return paper_service.fail_walkforward_run(paper_run_id, "history_reconciliation_failed")
    trade_date = str(paper_run["trade_date"])
    raw_orders = [
        item
        for item in paper_service._orders_through(result, trade_date)
        if paper_service._order_trade_date(item) > baseline_date
    ]
    processed = _process_orders(
        session=session,
        paper_run=paper_run,
        child=child,
        orders=raw_orders,
    )
    session = paper_service.get_session(str(session["id"])) or session
    _write_snapshot_report(
        session=session,
        paper_run=paper_run,
        child=child,
        orders=processed["orders"],
    )
    reconciliation = paper_order_pipeline.reconcile_session_day(
        session_id=str(session["id"]),
        paper_run_id=paper_run_id,
        trade_date=trade_date,
    )
    final_state = "RECONCILED" if reconciliation.get("passed") else "RECONCILIATION_FAILED"
    for intent in processed["intents"]:
        if paper_order_pipeline.current_state(str(intent["id"])) == "RECONCILIATION_PENDING":
            paper_order_pipeline.append_transition(
                str(intent["id"]),
                final_state,
                event_type="reconciliation_completed" if reconciliation.get("passed") else "reconciliation_failed",
                idempotency_key="reconciliation_result",
                payload={"recordId": reconciliation.get("id"), "marketPolicy": POLICY_VERSION},
            )
    paper_order_pipeline.complete_checkpoint(
        paper_run_id,
        "reconciliation",
        {"passed": bool(reconciliation.get("passed")), "recordId": reconciliation.get("id")},
    )
    now = utc_now()
    if not reconciliation.get("passed"):
        with db() as connection:
            connection.execute(
                "update paper_walkforward_runs set reconciliation_json=? where id=?",
                (json_dump(reconciliation), paper_run_id),
            )
        return paper_service.fail_walkforward_run(paper_run_id, "ledger_reconciliation_failed")
    with db() as connection:
        connection.execute(
            """
            update paper_walkforward_runs
            set status='success',reconciliation_json=?,finished_at=?
            where id=?
            """,
            (json_dump(reconciliation), now, paper_run_id),
        )
        connection.execute(
            """
            update paper_sessions
            set status='running',last_processed_date=?,failure_json=null,updated_at=?
            where id=?
            """,
            (trade_date, now, session["id"]),
        )
    return paper_service.get_walkforward_run(paper_run_id) or {}
