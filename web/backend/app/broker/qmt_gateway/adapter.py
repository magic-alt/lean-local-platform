from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo

from ..query_contract import (
    BrokerCapabilityDescriptor,
    BrokerContractError,
    BrokerQueryEnvelope,
    BrokerQueryRequest,
    BrokerSourceError,
    opaque_account_ref,
)
from .xtquant_client import QmtReadOnlyClient, qmt_to_platform_symbol


QMT_QUERY_DESCRIPTOR = BrokerCapabilityDescriptor(
    adapter_id="qmt",
    version="1",
    account_types=("STOCK",),
    asset_classes=("equity", "etf", "index_quote"),
    order_types=("observed_buy", "observed_sell"),
    query_operations=("account", "positions", "orders", "fills", "quotes"),
    operation_windows=(
        ("account", "current_asia_shanghai_session_snapshot"),
        ("positions", "current_asia_shanghai_session_snapshot"),
        ("orders", "current_asia_shanghai_session_only"),
        ("fills", "current_asia_shanghai_session_only"),
        ("quotes", "current_asia_shanghai_session_snapshot"),
    ),
    supports_streaming=False,
    supports_replay=False,
    pagination="vendor_managed",
    rate_limits="vendor_defined",
    os_requirements=("windows", "miniqmt_host"),
    credential_scope="read_only",
    execution_authorized=False,
    sequence_scope="gateway_process_session",
)


class QmtBrokerQueryClient:
    """Unified read-only query adapter over the existing XtQuant boundary."""

    def __init__(self, client: QmtReadOnlyClient, *, account_id: str) -> None:
        self._client = client
        self._account_ref = opaque_account_ref("qmt", account_id)
        self._sequence = 0
        self._lock = Lock()

    @property
    def descriptor(self) -> BrokerCapabilityDescriptor:
        return QMT_QUERY_DESCRIPTOR

    @property
    def account_ref(self) -> str:
        return self._account_ref

    @staticmethod
    def _today() -> str:
        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    def _next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _validate_request(self, request: BrokerQueryRequest) -> tuple[str, str]:
        self.descriptor.assert_query_allowed(request.operation)
        if request.account != self._account_ref:
            raise BrokerContractError("account_scope_mismatch", "QMT request account does not match gateway account")
        current = self._today()
        start = request.history_start or current
        end = request.history_end or current
        if start != current or end != current:
            raise BrokerContractError(
                "unsupported_history",
                "QMT query adapter only supports the current Asia/Shanghai trade date",
                details={
                    "requestedStart": start,
                    "requestedEnd": end,
                    "supportedStart": current,
                    "supportedEnd": current,
                },
            )
        if request.operation == "quotes" and not request.instruments:
            raise BrokerContractError("instruments_required", "quotes query requires at least one instrument")
        return start, end

    def _session_correlation(self) -> str:
        settings = getattr(self._client, "settings", None)
        session_id = getattr(settings, "session_id", None)
        generation = getattr(self._client, "_connection_generation", None)
        return f"qmt-session:{session_id if session_id is not None else 'opaque'}:{generation if generation is not None else 'current'}"

    def _records(self, request: BrokerQueryRequest) -> tuple[dict[str, Any], ...]:
        operation = request.operation
        if operation == "account":
            asset = self._client.query_asset()
            return (
                {
                    "portfolioValue": asset.total_asset,
                    "cash": asset.cash,
                },
            )
        if operation == "positions":
            return tuple(
                {
                    "instrument": qmt_to_platform_symbol(item.stock_code),
                    "quantity": item.volume,
                    "availableQuantity": item.can_use_volume,
                }
                for item in self._client.query_positions()
            )
        if operation == "orders":
            correlation = self._session_correlation()
            return tuple(
                {
                    "brokerOrderId": item.order_id,
                    "clientRequestId": None,
                    "sessionCorrelation": correlation,
                    "instrument": qmt_to_platform_symbol(item.stock_code),
                    "side": item.side,
                    "quantity": item.order_volume,
                    "filledQuantity": item.traded_volume,
                    "limitPrice": item.price,
                    "status": item.status,
                    "eventAtUtc": item.event_at_utc,
                    "qmtOrderStatus": item.raw_status,
                }
                for item in self._client.query_orders()
            )
        if operation == "fills":
            correlation = self._session_correlation()
            return tuple(
                {
                    "fillId": item.trade_id,
                    "brokerOrderId": item.order_id,
                    "clientRequestId": None,
                    "sessionCorrelation": correlation,
                    "instrument": qmt_to_platform_symbol(item.stock_code),
                    "side": item.side,
                    "quantity": item.traded_volume,
                    "price": item.traded_price,
                    "fee": None,
                    "feeCurrency": None,
                    "eventAtUtc": item.event_at_utc,
                }
                for item in self._client.query_fills()
            )
        if operation == "quotes":
            return tuple(
                {
                    "instrument": qmt_to_platform_symbol(item.stock_code),
                    "price": item.price,
                    "paused": item.paused,
                    "isLimitUp": item.is_limit_up,
                    "isLimitDown": item.is_limit_down,
                    "adv20Volume": item.adv20_volume,
                    "adv20Amount": item.adv20_amount,
                }
                for item in self._client.query_quotes(list(request.instruments))
            )
        raise BrokerContractError("query_operation_unsupported", f"unsupported QMT query operation: {operation}")

    def query(self, request: BrokerQueryRequest) -> BrokerQueryEnvelope:
        start, end = self._validate_request(request)
        sequence = self._next_sequence()
        snapshot_time = datetime.now(timezone.utc).isoformat()
        try:
            self._client.ensure_connected()
            records = self._records(request)
        except BrokerContractError:
            raise
        except Exception:
            return BrokerQueryEnvelope(
                adapter_id=self.descriptor.adapter_id,
                operation=request.operation,
                account=self._account_ref,
                client_request_id=request.client_request_id,
                snapshot_time=snapshot_time,
                sequence=sequence,
                history_start=start,
                history_end=end,
                history_scope=self.descriptor.history_window_for(request.operation),
                complete=False,
                records=(),
                source_errors=(
                    BrokerSourceError(
                        source="qmt",
                        code="qmt_query_failed",
                        message=f"QMT {request.operation} query failed",
                        retryable=True,
                    ),
                ),
            )

        # Current account/position/quote snapshots can be complete for their
        # declared snapshot scope. QMT order/fill retention is explicitly not
        # treated as complete historical execution evidence.
        complete = request.operation not in {"orders", "fills"}
        return BrokerQueryEnvelope(
            adapter_id=self.descriptor.adapter_id,
            operation=request.operation,
            account=self._account_ref,
            client_request_id=request.client_request_id,
            snapshot_time=snapshot_time,
            sequence=sequence,
            history_start=start,
            history_end=end,
            history_scope=self.descriptor.history_window_for(request.operation),
            complete=complete,
            records=records,
            source_errors=(),
        )

    def close(self) -> None:
        self._client.close()
