from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


ORDER_STATES = {
    "received",
    "validating",
    "rejected",
    "accepted",
    "submitted",
    "partially_filled",
    "filled",
    "cancel_pending",
    "cancelled",
    "expired",
    "invalid",
    "settled",
    "reconciled",
}

LEGAL_TRANSITIONS = {
    None: {"received"},
    "received": {"validating", "invalid"},
    "validating": {"accepted", "rejected", "invalid"},
    "accepted": {"submitted", "cancelled"},
    "submitted": {"partially_filled", "filled", "cancel_pending", "cancelled", "expired", "invalid"},
    "partially_filled": {"partially_filled", "filled", "cancel_pending", "cancelled", "expired"},
    "filled": {"settled"},
    "cancel_pending": {"cancelled", "partially_filled", "filled"},
    "settled": {"reconciled"},
    "rejected": set(),
    "cancelled": set(),
    "expired": set(),
    "invalid": set(),
    "reconciled": set(),
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
) -> dict[str, Any]:
    idempotency_key = f"lean:{paper_run_id}:{event_key}"
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
                 requested_price,raw_intent_json,created_at)
            values (?,?,?,?,?,?,?,1,?,?,?,?,?,?,?,?)
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
            ),
        )
    append_transition(
        intent_id,
        "received",
        event_type="intent_captured",
        idempotency_key="received",
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
    payload: dict[str, Any] | None = None,
    currency: str = "CNY",
) -> dict[str, Any]:
    intent = get_intent(intent_id)
    if not intent:
        raise KeyError("Paper order intent not found.")
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
        connection.execute(
            """
            insert into paper_order_fills
                (id,intent_id,external_fill_key,trade_date,quantity,price,fee,payload_json,created_at)
            values (?,?,?,?,?,?,?,?,?)
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
            ),
        )
        signed_quantity = quantity if intent["side"] == "buy" else -quantity
        cash_amount = -(quantity * price + fee) if intent["side"] == "buy" else quantity * price - fee
        entries = (
            ("position", intent["symbol"], signed_quantity, 0.0),
            ("cash", None, 0.0, cash_amount),
            ("fee", None, 0.0, -fee),
        )
        for entry_type, symbol, entry_quantity, amount in entries:
            connection.execute(
                """
                insert into paper_ledger_entries
                    (id,session_id,intent_id,fill_id,entry_type,asset,symbol,quantity,
                     amount,currency,idempotency_key,created_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    intent["session_id"],
                    intent_id,
                    fill_id,
                    entry_type,
                    "equity" if entry_type == "position" else "cash",
                    symbol,
                    entry_quantity,
                    amount,
                    currency,
                    f"{external_fill_key}:{entry_type}",
                    utc_now(),
                ),
            )
        row = connection.execute(
            "select * from paper_order_fills where id=?",
            (fill_id,),
        ).fetchone()
    return row_to_dict(row) or {}


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
    return row_to_dict(row) or {}
