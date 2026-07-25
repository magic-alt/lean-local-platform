from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


ORDER_STATES = {
    "INTENT_CREATED",
    "VALIDATION_PENDING",
    "REJECTED",
    "ACCEPTED",
    "MATCHING",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "EXPIRED",
    "FAILED",
    "RECONCILIATION_PENDING",
    "RECONCILED",
    "RECONCILIATION_FAILED",
}

LEGAL_TRANSITIONS = {
    None: {"INTENT_CREATED"},
    "INTENT_CREATED": {"VALIDATION_PENDING", "FAILED"},
    "VALIDATION_PENDING": {"ACCEPTED", "REJECTED", "FAILED"},
    "ACCEPTED": {"MATCHING", "CANCELLED", "EXPIRED", "FAILED"},
    "MATCHING": {"PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED", "FAILED"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED", "FAILED"},
    "FILLED": {"RECONCILIATION_PENDING"},
    "REJECTED": {"RECONCILIATION_PENDING"},
    "CANCELLED": {"RECONCILIATION_PENDING"},
    "EXPIRED": {"RECONCILIATION_PENDING"},
    "FAILED": {"RECONCILIATION_PENDING"},
    "RECONCILIATION_PENDING": {"RECONCILED", "RECONCILIATION_FAILED"},
    "RECONCILED": set(),
    "RECONCILIATION_FAILED": set(),
}

RUN_PHASES = (
    "intent_capture",
    "constraint_validation",
    "matching",
    "ledger",
    "snapshot_report",
    "reconciliation",
)


def _digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def record_intent(
    *,
    session_id: str,
    paper_run_id: str,
    backtest_run_id: str,
    event_key: str,
    trade_date: str,
    symbol: str,
    side: str,
    quantity: float,
    requested_price: float | None,
    raw_intent: dict[str, Any],
    attempt: int = 1,
    lean_order_id: str | None = None,
    project_snapshot_id: str | None = None,
    project_snapshot_hash: str | None = None,
    strategy_fingerprint: str | None = None,
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    signal_time: str | None = None,
    requested_execution_time: str | None = None,
    dataset_version: str | None = None,
    universe_version: str | None = None,
    constraint_version: str = "paper-constraints-v2",
) -> dict[str, Any]:
    normalized_payload = {
        "symbol": str(symbol).upper(),
        "side": str(side).lower(),
        "quantity": abs(float(quantity)),
        "orderType": str(order_type).lower(),
        "limitPrice": limit_price,
        "stopPrice": stop_price,
        "signalTime": signal_time,
        "requestedExecutionTime": requested_execution_time,
    }
    idempotency_key = _digest(
        {
            "sessionId": session_id,
            "tradeDate": trade_date,
            "projectSnapshotHash": project_snapshot_hash or project_snapshot_id or "missing",
            "logicalPaperRunId": paper_run_id,
            "leanOrderId": lean_order_id or event_key,
            "normalizedOrder": normalized_payload,
        }
    )
    correlation_id = f"{session_id}:{paper_run_id}"
    with db() as connection:
        existing = connection.execute(
            """
            select * from paper_order_intents
            where session_id=? and idempotency_key=?
            """,
            (session_id, idempotency_key),
        ).fetchone()
        if existing:
            return row_to_dict(existing) or {}
        intent_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_order_intents
                (id,session_id,paper_run_id,backtest_run_id,event_key,idempotency_key,
                 correlation_id,version,attempt,trade_date,symbol,side,quantity,
                 requested_price,raw_intent_json,created_at,lean_run_id,lean_order_id,
                 project_snapshot_id,project_snapshot_hash,strategy_fingerprint,order_type,
                 limit_price,stop_price,signal_time,requested_execution_time,dataset_version,
                 universe_version,constraint_version)
            values (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                intent_id,
                session_id,
                paper_run_id,
                backtest_run_id,
                event_key,
                idempotency_key,
                correlation_id,
                attempt,
                trade_date,
                symbol,
                side,
                quantity,
                requested_price,
                json_dump(raw_intent),
                utc_now(),
                backtest_run_id,
                lean_order_id or event_key,
                project_snapshot_id,
                project_snapshot_hash,
                strategy_fingerprint,
                str(order_type).lower(),
                limit_price,
                stop_price,
                signal_time,
                requested_execution_time,
                dataset_version,
                universe_version,
                constraint_version,
            ),
        )
    append_transition(
        intent_id,
        "INTENT_CREATED",
        event_type="intent_captured",
        idempotency_key="intent_created",
        payload={"source": "lean", "eventKey": event_key},
    )
    return get_intent(intent_id) or {}


def get_intent(intent_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from paper_order_intents where id=?",
            (intent_id,),
        ).fetchone()
    return row_to_dict(row)


def list_intents(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_order_intents
            where session_id=? order by trade_date,created_at,id
            """,
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_transitions(intent_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_order_transitions
            where intent_id=? order by sequence
            """,
            (intent_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def record_constraint_decision(
    intent_id: str,
    *,
    decision: str,
    constraint_version: str,
    rule_code: str | None,
    rule_inputs: dict[str, Any],
    portfolio_snapshot: dict[str, Any],
    reference_data_version: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_decision = str(decision).upper()
    if normalized_decision not in {"ACCEPT", "REJECT"}:
        raise ValueError("Constraint decision must be ACCEPT or REJECT.")
    payload = {
        "intentId": intent_id,
        "decision": normalized_decision,
        "constraintVersion": constraint_version,
        "ruleCode": rule_code,
        "ruleInputs": rule_inputs,
        "portfolioSnapshot": portfolio_snapshot,
        "referenceDataVersion": reference_data_version,
        "rules": rules,
    }
    digest = _digest(payload)
    with db() as connection:
        existing = connection.execute(
            "select * from paper_constraint_decisions where intent_id=?",
            (intent_id,),
        ).fetchone()
        if existing:
            if str(existing["decision_digest"]) != digest:
                raise ValueError("Constraint decision drift detected for immutable intent.")
            return row_to_dict(existing) or {}
        decision_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_constraint_decisions
                (id,intent_id,decision,constraint_version,rule_code,rule_inputs_json,
                 portfolio_snapshot_json,reference_data_version,rules_json,decision_digest,
                 decision_timestamp)
            values (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                decision_id,
                intent_id,
                normalized_decision,
                constraint_version,
                rule_code,
                json_dump(rule_inputs),
                json_dump(portfolio_snapshot),
                reference_data_version,
                json_dump(rules),
                digest,
                utc_now(),
            ),
        )
        row = connection.execute(
            "select * from paper_constraint_decisions where id=?",
            (decision_id,),
        ).fetchone()
    return row_to_dict(row) or {}


def list_constraint_decisions(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select decision.* from paper_constraint_decisions decision
            join paper_order_intents intent on intent.id=decision.intent_id
            where intent.session_id=?
            order by decision.decision_timestamp,decision.id
            """,
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_fills(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select fill.* from paper_order_fills fill
            join paper_order_intents intent on intent.id=fill.intent_id
            where intent.session_id=?
            order by fill.trade_date,fill.created_at,fill.id
            """,
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_ledger_entries(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_ledger_entries
            where session_id=? order by created_at,id
            """,
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def current_state(intent_id: str) -> str | None:
    with db() as connection:
        row = connection.execute(
            """
            select to_state from paper_order_transitions
            where intent_id=? order by sequence desc limit 1
            """,
            (intent_id,),
        ).fetchone()
    return str(row["to_state"]) if row else None


def append_transition(
    intent_id: str,
    to_state: str,
    *,
    event_type: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if to_state not in ORDER_STATES:
        raise ValueError(f"Unknown Paper order state: {to_state}")
    intent = get_intent(intent_id)
    if not intent:
        raise KeyError("Paper order intent not found.")
    with db() as connection:
        existing = connection.execute(
            """
            select * from paper_order_transitions
            where intent_id=? and idempotency_key=?
            """,
            (intent_id, idempotency_key),
        ).fetchone()
        if existing:
            if str(existing["to_state"]) != to_state:
                raise ValueError("Transition idempotency key was reused for a different state.")
            return row_to_dict(existing) or {}
        latest = connection.execute(
            """
            select sequence,to_state from paper_order_transitions
            where intent_id=? order by sequence desc limit 1
            """,
            (intent_id,),
        ).fetchone()
        from_state = str(latest["to_state"]) if latest else None
        if to_state not in LEGAL_TRANSITIONS[from_state]:
            raise ValueError(f"Illegal Paper order transition: {from_state or 'null'} -> {to_state}")
        transition_id = str(uuid.uuid4())
        sequence = int(latest["sequence"]) + 1 if latest else 1
        connection.execute(
            """
            insert into paper_order_transitions
                (id,intent_id,sequence,from_state,to_state,event_type,idempotency_key,
                 correlation_id,version,attempt,payload_json,created_at)
            values (?,?,?,?,?,?,?,?,1,?,?,?)
            """,
            (
                transition_id,
                intent_id,
                sequence,
                from_state,
                to_state,
                event_type,
                idempotency_key,
                intent["correlation_id"],
                int(intent.get("attempt") or 1),
                json_dump(payload or {}),
                utc_now(),
            ),
        )
        row = connection.execute(
            "select * from paper_order_transitions where id=?",
            (transition_id,),
        ).fetchone()
    return row_to_dict(row) or {}


def record_fill_and_ledger(
    intent_id: str,
    *,
    external_fill_key: str,
    trade_date: str,
    quantity: float,
    price: float,
    fee: float,
    tax: float = 0.0,
    slippage: float = 0.0,
    fee_model_version: str = "paper-fees-v1",
    matching_contract: str = "next_open-v1",
    payload: dict[str, Any] | None = None,
    currency: str = "CNY",
) -> dict[str, Any]:
    intent = get_intent(intent_id)
    if not intent:
        raise KeyError("Paper order intent not found.")
    state = current_state(intent_id)
    if state not in {"MATCHING", "PARTIALLY_FILLED"}:
        raise ValueError(f"Paper fill requires MATCHING state, got {state or 'null'}.")
    with db() as connection:
        existing = connection.execute(
            """
            select * from paper_order_fills
            where intent_id=? and external_fill_key=?
            """,
            (intent_id, external_fill_key),
        ).fetchone()
        if existing:
            return row_to_dict(existing) or {}
        fill_id = str(uuid.uuid4())
        fill_fingerprint = _digest(
            {
                "intentId": intent_id,
                "tradeDate": trade_date,
                "quantity": quantity,
                "price": price,
                "fee": fee,
                "tax": tax,
                "slippage": slippage,
                "feeModelVersion": fee_model_version,
                "matchingContract": matching_contract,
            }
        )
        connection.execute(
            """
            insert into paper_order_fills
                (id,intent_id,external_fill_key,trade_date,quantity,price,fee,payload_json,
                 created_at,tax,slippage,fee_model_version,matching_contract,fill_fingerprint)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fill_id,
                intent_id,
                external_fill_key,
                trade_date,
                quantity,
                price,
                fee,
                json_dump(payload or {}),
                utc_now(),
                tax,
                slippage,
                fee_model_version,
                matching_contract,
                fill_fingerprint,
            ),
        )
        signed_quantity = quantity if intent["side"] == "buy" else -quantity
        principal_amount = -(quantity * price) if intent["side"] == "buy" else quantity * price
        entries = [
            (
                "POSITION_INCREASE" if intent["side"] == "buy" else "POSITION_DECREASE",
                "equity",
                intent["symbol"],
                signed_quantity,
                quantity * price,
                f"POSITION:{intent['symbol']}" if intent["side"] == "buy" else "TRADE_CLEARING",
                "TRADE_CLEARING" if intent["side"] == "buy" else f"POSITION:{intent['symbol']}",
            ),
            (
                "TRADE_PRINCIPAL",
                "cash",
                None,
                0.0,
                principal_amount,
                "TRADE_CLEARING" if intent["side"] == "buy" else "CASH",
                "CASH" if intent["side"] == "buy" else "TRADE_CLEARING",
            ),
            ("COMMISSION", "cash", None, 0.0, -fee, "COMMISSION_EXPENSE", "CASH"),
        ]
        if tax:
            entries.append(("STAMP_DUTY", "cash", None, 0.0, -tax, "STAMP_DUTY_EXPENSE", "CASH"))
        if slippage:
            entries.append(("SLIPPAGE", "cash", None, 0.0, -slippage, "SLIPPAGE_EXPENSE", "CASH"))
        for entry_type, asset, symbol, entry_quantity, amount, debit_account, credit_account in entries:
            connection.execute(
                """
                insert into paper_ledger_entries
                    (id,session_id,intent_id,fill_id,entry_type,asset,symbol,quantity,
                     amount,currency,idempotency_key,created_at,event_id,trade_date,
                     debit_account,credit_account)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    intent["session_id"],
                    intent_id,
                    fill_id,
                    entry_type,
                    asset,
                    symbol,
                    entry_quantity,
                    amount,
                    currency,
                    f"{external_fill_key}:{entry_type}",
                    utc_now(),
                    fill_id,
                    trade_date,
                    debit_account,
                    credit_account,
                ),
            )
        row = connection.execute(
            "select * from paper_order_fills where id=?",
            (fill_id,),
        ).fetchone()
    return row_to_dict(row) or {}


def ensure_opening_ledger(
    *,
    session_id: str,
    cash: float,
    positions: list[dict[str, Any]],
    currency: str = "CNY",
) -> None:
    """Write the immutable opening balances once before a v2 session is projected.

    A v2 projection cannot safely infer an opening balance from a mutable session
    row.  The deliberately idempotent opening entries make cash and positions
    reproducible from the ledger after a retry or worker restart.
    """
    with db() as connection:
        # The cash entry is the immutable opening marker.  Checking that marker
        # (rather than the session's whole ledger) keeps a retry from treating
        # a previously projected fill position as a new opening position.
        opening = connection.execute(
            """
            select id from paper_ledger_entries
            where session_id=? and asset='cash' and entry_type='CASH_DEPOSIT'
              and trade_date is null
            order by created_at,id limit 1
            """,
            (session_id,),
        ).fetchone()
        if opening:
            return
        now = utc_now()
        opening_intent_id = f"opening:{session_id}"
        connection.execute(
            """
            insert into paper_ledger_entries
                (id,session_id,intent_id,fill_id,entry_type,asset,symbol,quantity,
                 amount,currency,idempotency_key,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(session_id,idempotency_key) do update set
                idempotency_key=excluded.idempotency_key
            """,
            (
                str(uuid.uuid4()),
                session_id,
                opening_intent_id,
                None,
                "CASH_DEPOSIT",
                "cash",
                None,
                0.0,
                float(cash),
                currency,
                "opening:cash",
                now,
            ),
        )
        for position in positions:
            quantity = float(position.get("quantity") or 0)
            if not quantity:
                continue
            price = float(
                position.get("average_price")
                or position.get("averagePrice")
                or position.get("market_price")
                or position.get("marketPrice")
                or 0
            )
            symbol = str(position.get("symbol") or "").upper()
            if not symbol:
                raise ValueError("Opening position is missing a symbol.")
            connection.execute(
                """
                insert into paper_ledger_entries
                    (id,session_id,intent_id,fill_id,entry_type,asset,symbol,quantity,
                     amount,currency,idempotency_key,created_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(session_id,idempotency_key) do update set
                    idempotency_key=excluded.idempotency_key
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    opening_intent_id,
                    None,
                    "POSITION_INCREASE",
                    "equity",
                    symbol,
                    quantity,
                    quantity * price,
                    currency,
                    f"opening:position:{symbol}",
                    now,
                ),
            )


def ledger_projection(session_id: str) -> dict[str, Any]:
    """Return the deterministic cash and position projection of a v2 ledger."""
    with db() as connection:
        entries = connection.execute(
            """
            select ledger.*, fill.trade_date as fill_trade_date
            from paper_ledger_entries ledger
            left join paper_order_fills fill on fill.id=ledger.fill_id
            where ledger.session_id=? order by ledger.created_at,ledger.id
            """,
            (session_id,),
        ).fetchall()

    rows = rows_to_dicts(entries)
    cash = sum(float(item.get("amount") or 0) for item in rows if item.get("asset") == "cash")
    positions: dict[str, dict[str, Any]] = {}
    for entry in rows:
        if entry.get("asset") != "equity" or not entry.get("symbol"):
            continue
        symbol = str(entry["symbol"])
        quantity = float(entry.get("quantity") or 0)
        amount = float(entry.get("amount") or 0)
        item = positions.setdefault(
            symbol,
            {
                "symbol": symbol,
                "quantity": 0.0,
                "average_price": 0.0,
                "last_buy_date": None,
            },
        )
        current_quantity = float(item["quantity"])
        if quantity > 0:
            new_quantity = current_quantity + quantity
            item["average_price"] = (
                ((current_quantity * float(item["average_price"])) + amount) / new_quantity
                if new_quantity
                else 0.0
            )
            item["quantity"] = new_quantity
            if entry.get("fill_trade_date"):
                item["last_buy_date"] = str(entry["fill_trade_date"])
        elif quantity < 0:
            item["quantity"] = current_quantity + quantity
            if item["quantity"] < -1e-9:
                raise ValueError(f"Ledger projects a negative position for {symbol}.")
            if abs(float(item["quantity"])) <= 1e-9:
                item["quantity"] = 0.0
                item["average_price"] = 0.0
                item["last_buy_date"] = None

    return {
        "cash": cash,
        "positions": [item for _, item in sorted(positions.items()) if item["quantity"] > 0],
        "entryCount": len(rows),
    }


def reconcile_session_day(
    *,
    session_id: str,
    paper_run_id: str,
    trade_date: str,
) -> dict[str, Any]:
    projection = ledger_projection(session_id)
    with db() as connection:
        session = connection.execute(
            "select cash from paper_sessions where id=?",
            (session_id,),
        ).fetchone()
        previous = connection.execute(
            """
            select cash from paper_portfolio_snapshots
            where session_id=? and trade_date<?
            order by trade_date desc limit 1
            """,
            (session_id, trade_date),
        ).fetchone()
        opening = (
            float(previous["cash"])
            if previous
            else float(
                connection.execute(
                    """
                    select coalesce(sum(amount),0) as amount
                    from paper_ledger_entries
                    where session_id=? and asset='cash' and trade_date is null
                    """,
                    (session_id,),
                ).fetchone()["amount"]
                or 0
            )
        )
        day_cash = float(
            connection.execute(
                """
                select coalesce(sum(amount),0) as amount
                from paper_ledger_entries
                where session_id=? and asset='cash' and trade_date=?
                """,
                (session_id, trade_date),
            ).fetchone()["amount"]
            or 0
        )
        read_positions = connection.execute(
            """
            select symbol,quantity,average_price from paper_positions
            where session_id=? order by symbol
            """,
            (session_id,),
        ).fetchall()
        snapshot = connection.execute(
            """
            select * from paper_portfolio_snapshots
            where session_id=? and trade_date=?
            """,
            (session_id, trade_date),
        ).fetchone()
        report = connection.execute(
            """
            select id from paper_daily_reports
            where session_id=? and trade_date=?
            """,
            (session_id, trade_date),
        ).fetchone()
        fills = connection.execute(
            """
            select fill.id,fill.intent_id from paper_order_fills fill
            join paper_order_intents intent on intent.id=fill.intent_id
            where intent.session_id=? and fill.trade_date=?
            """,
            (session_id, trade_date),
        ).fetchall()
        filled_transition_count = int(
            connection.execute(
                """
                select count(distinct transition.intent_id) as count
                from paper_order_transitions transition
                join paper_order_intents intent on intent.id=transition.intent_id
                where intent.session_id=? and intent.trade_date=? and transition.to_state='FILLED'
                """,
                (session_id, trade_date),
            ).fetchone()["count"]
            or 0
        )
        fill_ledger_counts = {
            str(row["fill_id"]): int(row["count"])
            for row in connection.execute(
                """
                select fill_id,count(*) as count from paper_ledger_entries
                where session_id=? and trade_date=? and fill_id is not null
                group by fill_id
                """,
                (session_id, trade_date),
            ).fetchall()
        }
    closing_cash = float((session or {}).get("cash") or 0)
    expected_cash = opening + day_cash
    cash_drift = closing_cash - expected_cash
    projected_positions = {
        str(item["symbol"]): (float(item["quantity"]), float(item["average_price"]))
        for item in projection["positions"]
    }
    actual_positions = {
        str(item["symbol"]): (float(item["quantity"]), float(item["average_price"]))
        for item in read_positions
    }
    all_symbols = set(projected_positions) | set(actual_positions)
    position_drift = sum(
        abs(projected_positions.get(symbol, (0.0, 0.0))[0] - actual_positions.get(symbol, (0.0, 0.0))[0])
        for symbol in all_symbols
    )
    order_fill_ok = filled_transition_count == len(fills)
    fill_ledger_ok = all(fill_ledger_counts.get(str(fill["id"]), 0) >= 3 for fill in fills)
    snapshot_ok = bool(
        snapshot
        and abs(float(snapshot["cash"]) - closing_cash) <= 1e-8
        and abs(float(snapshot["cash"]) - float(projection["cash"])) <= 1e-8
    )
    invariants = {
        "openingCash": opening,
        "ledgerCashMovement": day_cash,
        "expectedClosingCash": expected_cash,
        "closingCash": closing_cash,
        "cashDrift": cash_drift,
        "positionDrift": position_drift,
        "filledTransitions": filled_transition_count,
        "fills": len(fills),
        "fillLedgerCounts": fill_ledger_counts,
        "snapshotPresent": bool(snapshot),
        "dailyReportPresent": bool(report),
    }
    passed = bool(
        abs(cash_drift) <= 1e-8
        and position_drift <= 1e-8
        and order_fill_ok
        and fill_ledger_ok
        and snapshot_ok
        and report
    )
    digest = _digest({"sessionId": session_id, "tradeDate": trade_date, **invariants})
    now = utc_now()
    with db() as connection:
        existing = connection.execute(
            "select * from paper_reconciliation_records where session_id=? and trade_date=?",
            (session_id, trade_date),
        ).fetchone()
        if existing:
            if str(existing["result_digest"]) != digest:
                raise ValueError("Paper reconciliation drift detected for completed trade date.")
            return row_to_dict(existing) or {}
        record_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_reconciliation_records
                (id,session_id,paper_run_id,trade_date,status,opening_cash,
                 ledger_cash_movement,closing_cash,cash_drift,position_drift,
                 order_fill_ok,fill_ledger_ok,ledger_cash_ok,ledger_positions_ok,
                 snapshot_ok,daily_report_ok,invariants_json,result_digest,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record_id,
                session_id,
                paper_run_id,
                trade_date,
                "RECONCILED" if passed else "RECONCILIATION_FAILED",
                opening,
                day_cash,
                closing_cash,
                cash_drift,
                position_drift,
                1 if order_fill_ok else 0,
                1 if fill_ledger_ok else 0,
                1 if abs(cash_drift) <= 1e-8 else 0,
                1 if position_drift <= 1e-8 else 0,
                1 if snapshot_ok else 0,
                1 if report else 0,
                json_dump(invariants),
                digest,
                now,
            ),
        )
        row = connection.execute(
            "select * from paper_reconciliation_records where id=?",
            (record_id,),
        ).fetchone()
    return row_to_dict(row) or {}


def list_reconciliations(session_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select * from paper_reconciliation_records
            where session_id=? order by trade_date
            """,
            (session_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def list_checkpoints(
    session_id: str,
    *,
    trade_date: str | None = None,
    phase: str | None = None,
) -> list[dict[str, Any]]:
    filters = ["run.session_id=?"]
    params: list[Any] = [session_id]
    if trade_date:
        filters.append("run.trade_date=?")
        params.append(trade_date)
    if phase:
        filters.append("checkpoint.phase=?")
        params.append(phase)
    with db() as connection:
        rows = connection.execute(
            f"""
            select checkpoint.*,run.trade_date,run.status as run_status
            from paper_run_checkpoints checkpoint
            join paper_walkforward_runs run on run.id=checkpoint.paper_run_id
            where {" and ".join(filters)}
            order by run.trade_date,checkpoint.created_at,checkpoint.phase
            """,
            tuple(params),
        ).fetchall()
    return rows_to_dicts(rows)


def _fault_pause_after_checkpoint(paper_run_id: str, phase: str) -> None:
    if os.environ.get("LEAN_FAULT_INJECTION_ENABLED", "0") != "1":
        return
    configured = {
        item.strip()
        for item in os.environ.get(
            "LEAN_PAPER_FAULT_PAUSE_PHASES",
            ",".join(RUN_PHASES),
        ).split(",")
        if item.strip()
    }
    if phase not in configured:
        return
    raw_targets = os.environ.get("LEAN_PAPER_FAULT_PAUSE_TARGETS", "").strip()
    if raw_targets:
        with db() as connection:
            run = connection.execute(
                "select trade_date from paper_walkforward_runs where id=?",
                (paper_run_id,),
            ).fetchone()
        target = f"{str(run['trade_date'])}:{phase}" if run else ""
        configured_targets = {
            item.strip()
            for item in raw_targets.split(",")
            if item.strip()
        }
        if target not in configured_targets:
            return
    try:
        seconds = max(
            0.0,
            min(60.0, float(os.environ.get("LEAN_PAPER_CHECKPOINT_PAUSE_SECONDS", "0"))),
        )
    except (TypeError, ValueError):
        seconds = 0.0
    if seconds:
        time.sleep(seconds)


def complete_checkpoint(
    paper_run_id: str,
    phase: str,
    payload: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    if phase not in RUN_PHASES:
        raise ValueError(f"Unknown Paper run checkpoint phase: {phase}")
    body = payload or {}
    digest = _digest(body)
    now = utc_now()
    with db() as connection:
        existing = connection.execute(
            """
            select * from paper_run_checkpoints
            where paper_run_id=? and phase=?
            """,
            (paper_run_id, phase),
        ).fetchone()
        if existing:
            if str(existing["digest"] or "") != digest:
                raise ValueError(f"Checkpoint payload drift detected for {phase}.")
            return row_to_dict(existing) or {}
        checkpoint_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into paper_run_checkpoints
                (id,paper_run_id,phase,status,digest,payload_json,created_at,completed_at)
            values (?,?,?,'complete',?,?,?,?)
            """,
            (checkpoint_id, paper_run_id, phase, digest, json_dump(body), now, now),
        )
        row = connection.execute(
            "select * from paper_run_checkpoints where id=?",
            (checkpoint_id,),
        ).fetchone()
    item = row_to_dict(row) or {}
    _fault_pause_after_checkpoint(paper_run_id, phase)
    return item
