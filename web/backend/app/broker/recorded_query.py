from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .query_contract import (
    BrokerCapabilityDescriptor,
    BrokerContractError,
    BrokerQueryEnvelope,
    BrokerQueryRequest,
    BrokerSourceError,
)


RECORDED_QUERY_DESCRIPTOR = BrokerCapabilityDescriptor(
    adapter_id="recorded",
    version="1",
    account_types=("fixture",),
    asset_classes=("equity", "etf"),
    order_types=("observed",),
    query_operations=("account", "positions", "orders", "fills", "quotes"),
    operation_windows=(
        ("account", "recorded_fixture_range"),
        ("positions", "recorded_fixture_range"),
        ("orders", "recorded_fixture_range"),
        ("fills", "recorded_fixture_range"),
        ("quotes", "recorded_fixture_range"),
    ),
    supports_streaming=False,
    supports_replay=True,
    pagination="none",
    rate_limits="none",
    os_requirements=("portable",),
    sequence_scope="recorded_fixture",
    test_only=True,
)


class RecordedBrokerQueryClient:
    """Deterministic read-only adapter for conformance and recovery tests."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self._fixture = dict(fixture)
        self._account = str(self._fixture.get("account") or "").strip()
        self._history_start = str(self._fixture.get("historyStart") or "").strip()
        self._history_end = str(self._fixture.get("historyEnd") or "").strip()
        self._snapshot_time = str(self._fixture.get("snapshotTime") or "").strip()
        self._operations = self._fixture.get("operations")
        if not self._account or not self._history_start or not self._history_end or not self._snapshot_time:
            raise BrokerContractError("invalid_recorded_fixture", "recorded broker fixture metadata is incomplete")
        if not isinstance(self._operations, dict):
            raise BrokerContractError("invalid_recorded_fixture", "recorded broker fixture operations are missing")

    @classmethod
    def from_path(cls, path: Path) -> "RecordedBrokerQueryClient":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @property
    def descriptor(self) -> BrokerCapabilityDescriptor:
        return RECORDED_QUERY_DESCRIPTOR

    @property
    def account_ref(self) -> str:
        return self._account

    def query(self, request: BrokerQueryRequest) -> BrokerQueryEnvelope:
        self.descriptor.assert_query_allowed(request.operation)
        if request.account != self._account:
            raise BrokerContractError("account_scope_mismatch", "recorded query account does not match fixture account")
        start = request.history_start or self._history_start
        end = request.history_end or self._history_end
        if start < self._history_start or end > self._history_end:
            raise BrokerContractError(
                "unsupported_history",
                "recorded adapter does not contain the requested history range",
                details={"availableStart": self._history_start, "availableEnd": self._history_end},
            )
        payload = self._operations.get(request.operation)
        if not isinstance(payload, dict):
            raise BrokerContractError(
                "query_operation_unsupported",
                f"recorded fixture has no operation {request.operation!r}",
            )
        errors = tuple(
            BrokerSourceError(
                source=str(item.get("source") or "recorded"),
                code=str(item.get("code") or "recorded_source_error"),
                message=str(item.get("message") or "recorded source failed"),
                retryable=bool(item.get("retryable")),
            )
            for item in payload.get("sourceErrors", [])
            if isinstance(item, dict)
        )
        records = tuple(dict(item) for item in payload.get("records", []) if isinstance(item, dict))
        complete = bool(payload.get("complete", True)) and not errors
        return BrokerQueryEnvelope(
            adapter_id=self.descriptor.adapter_id,
            operation=request.operation,
            account=self._account,
            client_request_id=request.client_request_id,
            snapshot_time=str(payload.get("snapshotTime") or self._snapshot_time),
            sequence=int(payload.get("sequence") or 0),
            history_start=start,
            history_end=end,
            history_scope=self.descriptor.history_window_for(request.operation),
            complete=complete,
            records=records,
            source_errors=errors,
        )

    def close(self) -> None:
        return None
