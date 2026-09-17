from __future__ import annotations

import math
from typing import Any, Mapping

from ..db import db, row_to_dict
from ..repositories.backtest_repository import get_backtest
from . import paper as paper_service
from . import paper_order_pipeline
from .us_etf_paper_v2 import CURRENCY, POLICY_VERSION


PROBE_VERSION = "us-etf-worker-risk-probe-v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _paper_context(paper_run_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    paper_run = paper_service.get_walkforward_run(paper_run_id)
    if not paper_run:
        raise KeyError("Paper run not found.")
    session = paper_service.get_session(str(paper_run["session_id"]))
    child = get_backtest(str(paper_run["backtest_run_id"]))
    if not session or not child:
        raise ValueError("U.S. ETF risk probe requires persisted session and child backtest context.")
    if _text((session.get("parameters") or {}).get("paperMarketPolicy")) != POLICY_VERSION:
        raise ValueError("Risk probe is restricted to U.S. ETF Paper-v2 certification sessions.")
    if child.get("status") != "success" or (child.get("validation") or {}).get("passed") is not True:
        raise ValueError("Risk probe requires a successful validated LEAN Paper child run.")
    return paper_run, session, child


def _probe_price(session: Mapping[str, Any], trade_date: str, symbol: str) -> float:
    bar = paper_service._execution_bar(dict(session), symbol, trade_date)
    if not isinstance(bar, Mapping):
        raise ValueError(f"No authoritative execution bar is available for risk probe {symbol} {trade_date}.")
    price = float(bar.get("open") or bar.get("close") or 0)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Risk probe requires a finite positive authoritative execution price.")
    return price


def _oversized_buy(session: Mapping[str, Any], price: float) -> tuple[float, dict[str, Any]]:
    parameters = dict(session.get("parameters") or {})
    cash = max(0.0, float(session.get("cash") or 0))
    min_cash = max(
        0.0,
        float(
            parameters.get("minCash")
            or parameters.get("min_cash")
            or parameters.get("cashFloor")
            or 0.0
        ),
    )
    commission = max(0.0, float(parameters.get("commissionPerOrder") or 0.0))
    max_order = parameters.get("maxOrderAmount")
    if max_order is None:
        max_order = parameters.get("max_order_amount")
    max_order_amount = float(max_order) if max_order is not None else 0.0
    # Exceed both current usable cash and any configured max-order amount. The
    # resulting REJECT is still produced by the production worker risk helper;
    # this helper only constructs the audit probe input.
    rejection_floor = max(cash - min_cash + commission, max_order_amount, price)
    principal = rejection_floor + max(price, 1.0)
    quantity = principal / price
    return quantity, {
        "cash": cash,
        "minCash": min_cash,
        "commissionPerOrder": commission,
        "maxOrderAmount": max_order_amount if max_order is not None else None,
        "requestedPrincipal": principal,
    }


def record_worker_rejection_probe(paper_run_id: str) -> dict[str, Any]:
    """Record one explicit no-fill risk probe through the canonical Paper-v2 state machine.

    The probe is intentionally not a strategy signal and is excluded from PnL. It
    exists only to prove that the worker-side admission/risk boundary can reject an
    order and that the rejected intent cannot create a fill or ledger movement.
    """

    paper_run, session, child = _paper_context(paper_run_id)
    trade_date = str(paper_run["trade_date"])
    symbol = _text(session.get("symbol")).upper()
    price = _probe_price(session, trade_date, symbol)
    quantity, risk_inputs = _oversized_buy(session, price)
    event_key = f"certification-risk-reject:{PROBE_VERSION}:{trade_date}:{symbol}"
    intent = paper_order_pipeline.record_intent(
        session_id=str(session["id"]),
        paper_run_id=paper_run_id,
        backtest_run_id=str(child["id"]),
        event_key=event_key,
        trade_date=trade_date,
        symbol=symbol,
        side="buy",
        quantity=quantity,
        requested_price=price,
        raw_intent={
            "certificationProbe": True,
            "probeVersion": PROBE_VERSION,
            "probeType": "worker_risk_rejection",
            "excludedFromStrategyPnl": True,
            "symbol": symbol,
            "side": "buy",
            "quantity": quantity,
            "price": price,
            "tradeDate": trade_date,
            "riskInputs": risk_inputs,
        },
        attempt=1,
        lean_order_id=event_key,
        project_snapshot_id=_text((session.get("parameters") or {}).get("strategySnapshotDir")) or None,
        project_snapshot_hash=_text((session.get("parameters") or {}).get("strategySnapshotHash")) or None,
        strategy_fingerprint=paper_service._strategy_fingerprint(child),
        order_type="market",
        signal_time=None,
        requested_execution_time=None,
        dataset_version=_text((session.get("parameters") or {}).get("datasetVersion")) or None,
        universe_version=_text((session.get("parameters") or {}).get("universeVersion")) or None,
        constraint_version=POLICY_VERSION,
    )
    intent_id = str(intent["id"])
    state = paper_order_pipeline.current_state(intent_id)
    if state != "INTENT_CREATED":
        with db() as connection:
            decision = connection.execute(
                "select * from paper_constraint_decisions where intent_id=?",
                (intent_id,),
            ).fetchone()
            fill_count = int(
                connection.execute(
                    "select count(*) as count from paper_order_fills where intent_id=?",
                    (intent_id,),
                ).fetchone()["count"]
                or 0
            )
        return {
            "probeVersion": PROBE_VERSION,
            "intentId": intent_id,
            "state": state,
            "decision": row_to_dict(decision) if decision else None,
            "fillCount": fill_count,
            "idempotentReplay": True,
        }

    paper_order_pipeline.append_transition(
        intent_id,
        "VALIDATION_PENDING",
        event_type="certification_probe_validation_started",
        idempotency_key=f"{PROBE_VERSION}:validation",
        payload={"probeVersion": PROBE_VERSION},
    )
    refreshed = paper_service.get_session(str(session["id"])) or session
    probe_order = {
        "id": event_key,
        "orderId": event_key,
        "symbol": symbol,
        "side": "buy",
        "quantity": quantity,
        "price": price,
        "tradeDate": trade_date,
        "certificationProbe": True,
    }
    reason = paper_service._lean_intent_rejection(refreshed, probe_order, trade_date)
    if not reason:
        raise ValueError(
            "Certification risk probe was not rejected by the worker risk boundary; "
            "refusing to fabricate a REJECT decision."
        )
    decision = paper_order_pipeline.record_constraint_decision(
        intent_id,
        decision="REJECT",
        constraint_version=POLICY_VERSION,
        rule_code=reason,
        rule_inputs={
            **risk_inputs,
            "tradeDate": trade_date,
            "symbol": symbol,
            "side": "buy",
            "quantity": quantity,
            "requestedPrice": price,
            "currency": CURRENCY,
            "probeVersion": PROBE_VERSION,
        },
        portfolio_snapshot={
            "cash": float(refreshed.get("cash") or 0),
            "equity": float(refreshed.get("equity") or 0),
            "positions": paper_service.list_positions(str(refreshed["id"])),
        },
        reference_data_version=_text(intent.get("dataset_version")) or "UNVERSIONED",
        rules=[
            {
                "code": reason,
                "decision": "REJECT",
                "source": "paper._lean_intent_rejection",
                "certificationProbe": True,
            }
        ],
    )
    paper_order_pipeline.append_transition(
        intent_id,
        "REJECTED",
        event_type="certification_probe_rejected",
        idempotency_key=f"{PROBE_VERSION}:constraint_result",
        payload={
            "reason": reason,
            "probeVersion": PROBE_VERSION,
            "excludedFromStrategyPnl": True,
        },
    )
    paper_service._project_v2_order(
        refreshed,
        intent,
        status="rejected",
        reason=reason,
        price=price,
        fee=0,
        trade_date=trade_date,
    )
    paper_order_pipeline.append_transition(
        intent_id,
        "RECONCILIATION_PENDING",
        event_type="certification_probe_ledger_projection",
        idempotency_key=f"{PROBE_VERSION}:reconciliation_pending",
        payload={"probeVersion": PROBE_VERSION},
    )
    with db() as connection:
        fill_count = int(
            connection.execute(
                "select count(*) as count from paper_order_fills where intent_id=?",
                (intent_id,),
            ).fetchone()["count"]
            or 0
        )
    if fill_count:
        raise ValueError("Rejected certification probe unexpectedly created a fill.")
    return {
        "probeVersion": PROBE_VERSION,
        "intentId": intent_id,
        "state": paper_order_pipeline.current_state(intent_id),
        "decision": decision,
        "reason": reason,
        "fillCount": fill_count,
        "idempotentReplay": False,
    }


def finalize_worker_rejection_probe(paper_run_id: str) -> dict[str, Any]:
    paper_run, session, _child = _paper_context(paper_run_id)
    trade_date = str(paper_run["trade_date"])
    event_prefix = f"certification-risk-reject:{PROBE_VERSION}:{trade_date}:"
    with db() as connection:
        intent = connection.execute(
            """
            select * from paper_order_intents
            where paper_run_id=? and event_key like ?
            order by created_at,id limit 1
            """,
            (paper_run_id, event_prefix + "%"),
        ).fetchone()
        reconciliation = connection.execute(
            """
            select * from paper_reconciliation_records
            where session_id=? and trade_date=?
            """,
            (session["id"], trade_date),
        ).fetchone()
    if not intent:
        raise ValueError("Certification rejection probe intent is missing.")
    if not reconciliation or str(reconciliation["status"]) != "RECONCILED":
        raise ValueError("Certification rejection probe cannot finalize without successful reconciliation.")
    intent_id = str(intent["id"])
    state = paper_order_pipeline.current_state(intent_id)
    if state == "RECONCILIATION_PENDING":
        paper_order_pipeline.append_transition(
            intent_id,
            "RECONCILED",
            event_type="certification_probe_reconciled",
            idempotency_key=f"{PROBE_VERSION}:reconciliation_result",
            payload={
                "probeVersion": PROBE_VERSION,
                "reconciliationRecordId": reconciliation["id"],
            },
        )
    elif state != "RECONCILED":
        raise ValueError(f"Certification rejection probe ended in unexpected state: {state}")
    with db() as connection:
        fill_count = int(
            connection.execute(
                "select count(*) as count from paper_order_fills where intent_id=?",
                (intent_id,),
            ).fetchone()["count"]
            or 0
        )
    if fill_count:
        raise ValueError("Rejected certification probe has a fill after reconciliation.")
    return {
        "probeVersion": PROBE_VERSION,
        "intentId": intent_id,
        "state": paper_order_pipeline.current_state(intent_id),
        "fillCount": fill_count,
        "reconciliationRecordId": str(reconciliation["id"]),
    }
