from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Any

from .query_contract import BrokerQueryEnvelope, BrokerSourceError


_TERMINAL_CANCELLED = {"CANCELLED", "CANCELED"}
_STATUS_RANK = {
    "UNKNOWN": 0,
    "SUBMITTED": 10,
    "ACKNOWLEDGED": 20,
    "PARTIALLY_FILLED": 30,
    "CANCEL_REQUESTED": 40,
    "CANCELLED": 50,
    "CANCELED": 50,
    "REJECTED": 60,
    "FILLED": 70,
}


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    if not number.is_finite():
        return Decimal("0")
    return number


def _source_error_key(item: BrokerSourceError) -> tuple[str, str, str, bool]:
    return (item.source, item.code, item.message, item.retryable)


@dataclass(frozen=True)
class BrokerReconciliationSnapshot:
    account: str
    history_start: str | None
    history_end: str | None
    complete: bool
    economics_proven: bool
    orders: tuple[dict[str, Any], ...]
    orphan_fills: tuple[dict[str, Any], ...]
    raw_facts: tuple[dict[str, Any], ...]
    source_errors: tuple[BrokerSourceError, ...]
    fingerprint: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "account": self.account,
            "historyStart": self.history_start,
            "historyEnd": self.history_end,
            "complete": self.complete,
            "economicsProven": self.economics_proven,
            "orders": [dict(item) for item in self.orders],
            "orphanFills": [dict(item) for item in self.orphan_fills],
            "rawFacts": [dict(item) for item in self.raw_facts],
            "sourceErrors": [item.to_manifest() for item in self.source_errors],
            "fingerprint": self.fingerprint,
        }


def reconcile_broker_history(
    orders: BrokerQueryEnvelope,
    fills: BrokerQueryEnvelope,
) -> BrokerReconciliationSnapshot:
    """Reconcile read-only broker facts without manufacturing portfolio economics.

    The function is intentionally pure: replaying the same retained facts after
    process restart yields the same snapshot. Raw facts, including duplicates,
    remain available for audit while the derived view de-duplicates exact
    callback replays and fill IDs deterministically.
    """

    if orders.operation != "orders" or fills.operation != "fills":
        raise ValueError("reconciliation requires orders and fills envelopes")
    if orders.account != fills.account:
        raise ValueError("reconciliation envelopes must belong to one account")

    raw_facts: list[dict[str, Any]] = []
    for record in orders.records:
        raw_facts.append({"kind": "order", "record": dict(record)})
    for record in fills.records:
        raw_facts.append({"kind": "fill", "record": dict(record)})

    errors: list[BrokerSourceError] = [*orders.source_errors, *fills.source_errors]

    unique_order_events: list[dict[str, Any]] = []
    seen_order_facts: set[str] = set()
    for record in orders.records:
        fingerprint = _canonical(record)
        if fingerprint in seen_order_facts:
            continue
        seen_order_facts.add(fingerprint)
        unique_order_events.append(dict(record))

    unique_fills: dict[str, dict[str, Any]] = {}
    anonymous_fills: list[dict[str, Any]] = []
    for record in fills.records:
        item = dict(record)
        fill_id = str(item.get("fillId") or "").strip()
        if not fill_id:
            anonymous_fills.append(item)
            errors.append(
                BrokerSourceError(
                    source=fills.adapter_id,
                    code="fill_id_missing",
                    message="broker fill has no stable fillId",
                    retryable=False,
                )
            )
            continue
        prior = unique_fills.get(fill_id)
        if prior is None:
            unique_fills[fill_id] = item
        elif _canonical(prior) != _canonical(item):
            errors.append(
                BrokerSourceError(
                    source=fills.adapter_id,
                    code="conflicting_fill_duplicate",
                    message=f"broker fillId {fill_id} has conflicting duplicate observations",
                    retryable=False,
                )
            )

    events_by_order: dict[str, list[dict[str, Any]]] = {}
    for record in unique_order_events:
        broker_order_id = str(record.get("brokerOrderId") or "").strip()
        if not broker_order_id:
            errors.append(
                BrokerSourceError(
                    source=orders.adapter_id,
                    code="broker_order_id_missing",
                    message="broker order observation has no stable brokerOrderId",
                    retryable=False,
                )
            )
            continue
        events_by_order.setdefault(broker_order_id, []).append(record)

    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    for record in unique_fills.values():
        broker_order_id = str(record.get("brokerOrderId") or "").strip()
        fills_by_order.setdefault(broker_order_id, []).append(record)

    reconciled_orders: list[dict[str, Any]] = []
    for broker_order_id, lifecycle in sorted(events_by_order.items()):
        lifecycle.sort(
            key=lambda item: (
                str(item.get("eventAtUtc") or ""),
                _STATUS_RANK.get(str(item.get("status") or "UNKNOWN").upper(), 0),
                _canonical(item),
            )
        )
        latest = dict(lifecycle[-1])
        order_fills = sorted(
            fills_by_order.get(broker_order_id, []),
            key=lambda item: (str(item.get("eventAtUtc") or ""), str(item.get("fillId") or "")),
        )
        fill_quantity = sum((_decimal(item.get("quantity")) for item in order_fills), Decimal("0"))
        order_quantity = _decimal(latest.get("quantity"))
        status = str(latest.get("status") or "UNKNOWN").upper()
        if status in _TERMINAL_CANCELLED and fill_quantity > 0:
            reconciled_status = "CANCELLED_PARTIAL"
        elif order_quantity > 0 and fill_quantity >= order_quantity:
            reconciled_status = "FILLED"
        elif fill_quantity > 0 and status not in {"FILLED", "REJECTED"}:
            reconciled_status = "PARTIALLY_FILLED"
        else:
            reconciled_status = status
        reconciled_orders.append(
            {
                **latest,
                "status": reconciled_status,
                "observedFillQuantity": format(fill_quantity, "f"),
                "fills": [dict(item) for item in order_fills],
            }
        )

    orphan_fills = tuple(
        dict(item)
        for broker_order_id, items in sorted(fills_by_order.items())
        if broker_order_id not in events_by_order
        for item in items
    ) + tuple(anonymous_fills)

    deduped_errors: list[BrokerSourceError] = []
    seen_errors: set[tuple[str, str, str, bool]] = set()
    for item in errors:
        key = _source_error_key(item)
        if key not in seen_errors:
            seen_errors.add(key)
            deduped_errors.append(item)

    same_window = (
        orders.history_start == fills.history_start
        and orders.history_end == fills.history_end
    )
    complete = bool(
        orders.complete
        and fills.complete
        and same_window
        and not deduped_errors
        and not orphan_fills
    )
    all_fees_known = all(item.get("fee") is not None for item in unique_fills.values())
    economics_proven = complete and all_fees_known

    payload = {
        "account": orders.account,
        "historyStart": orders.history_start if same_window else None,
        "historyEnd": orders.history_end if same_window else None,
        "complete": complete,
        "economicsProven": economics_proven,
        "orders": reconciled_orders,
        "orphanFills": list(orphan_fills),
        "rawFacts": raw_facts,
        "sourceErrors": [item.to_manifest() for item in deduped_errors],
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
    return BrokerReconciliationSnapshot(
        account=orders.account,
        history_start=orders.history_start if same_window else None,
        history_end=orders.history_end if same_window else None,
        complete=complete,
        economics_proven=economics_proven,
        orders=tuple(reconciled_orders),
        orphan_fills=orphan_fills,
        raw_facts=tuple(raw_facts),
        source_errors=tuple(deduped_errors),
        fingerprint=digest,
    )


def resolve_unknown_request_outcome(
    client_request_id: str,
    orders: BrokerQueryEnvelope,
) -> dict[str, Any]:
    """Resolve an unknown outcome from observations only; never authorize resend."""

    matches = [
        dict(record)
        for record in orders.records
        if str(record.get("clientRequestId") or "") == client_request_id
    ]
    matches.sort(key=lambda item: (str(item.get("eventAtUtc") or ""), _canonical(item)))
    if not matches:
        return {
            "clientRequestId": client_request_id,
            "status": "UNKNOWN",
            "brokerOrderId": None,
            "sourceComplete": orders.complete,
            "resendAllowed": False,
        }
    latest = matches[-1]
    return {
        "clientRequestId": client_request_id,
        "status": "OBSERVED",
        "brokerOrderId": latest.get("brokerOrderId"),
        "brokerStatus": latest.get("status"),
        "sourceComplete": orders.complete,
        "resendAllowed": False,
    }
