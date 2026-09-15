from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from hashlib import sha256
import json
from typing import Any, Protocol


BROKER_QUERY_SCHEMA_VERSION = 1
KNOWN_QUERY_OPERATIONS = frozenset({"account", "positions", "orders", "fills", "quotes"})


class BrokerContractError(ValueError):
    """Fail-closed broker SDK contract violation."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


def _required_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise BrokerContractError("missing_field", f"{field_name} is required")
    return text


def _iso_date(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    text = _required_text(value, field_name)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise BrokerContractError("invalid_date", f"{field_name} must be an ISO date") from exc
    return text


def opaque_account_ref(adapter_id: str, account_id: str) -> str:
    """Return a stable non-secret account reference for envelopes and logs."""

    adapter = _required_text(adapter_id, "adapter_id").lower()
    raw = _required_text(account_id, "account_id")
    digest = sha256(f"{adapter}:{raw}".encode("utf-8")).hexdigest()[:20]
    return f"{adapter}:{digest}"


def stable_query_request_id(
    *,
    adapter_id: str,
    account: str,
    operation: str,
    history_start: str | None,
    history_end: str | None,
    instruments: tuple[str, ...] = (),
) -> str:
    payload = {
        "adapter": adapter_id,
        "account": account,
        "operation": operation,
        "historyStart": history_start,
        "historyEnd": history_end,
        "instruments": list(instruments),
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
    return f"brq-{digest}"


@dataclass(frozen=True)
class BrokerCapabilityDescriptor:
    adapter_id: str
    version: str
    account_types: tuple[str, ...]
    asset_classes: tuple[str, ...]
    order_types: tuple[str, ...]
    query_operations: tuple[str, ...]
    operation_windows: tuple[tuple[str, str], ...]
    supports_streaming: bool
    supports_replay: bool
    pagination: str
    rate_limits: str
    os_requirements: tuple[str, ...]
    credential_scope: str = "read_only"
    execution_authorized: bool = False
    sequence_scope: str = "adapter_session"
    test_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _required_text(self.adapter_id, "adapter_id").lower())
        object.__setattr__(self, "version", _required_text(self.version, "version"))
        operations = tuple(str(item).strip().lower() for item in self.query_operations)
        if not operations or any(item not in KNOWN_QUERY_OPERATIONS for item in operations):
            raise BrokerContractError("invalid_query_operations", "descriptor query operations are invalid")
        if len(set(operations)) != len(operations):
            raise BrokerContractError("duplicate_query_operation", "descriptor query operations must be unique")
        object.__setattr__(self, "query_operations", operations)
        windows = tuple((str(key).strip().lower(), _required_text(value, "history_window")) for key, value in self.operation_windows)
        window_keys = {key for key, _ in windows}
        if window_keys != set(operations):
            raise BrokerContractError(
                "history_window_mismatch",
                "every broker query operation must declare one history window",
            )
        object.__setattr__(self, "operation_windows", windows)
        if self.execution_authorized or self.credential_scope != "read_only":
            raise BrokerContractError(
                "execution_scope_forbidden",
                "Issue #64 broker query descriptors must remain read-only",
            )

    def history_window_for(self, operation: str) -> str:
        key = str(operation or "").strip().lower()
        try:
            return dict(self.operation_windows)[key]
        except KeyError as exc:
            raise BrokerContractError(
                "query_operation_unsupported",
                f"broker adapter {self.adapter_id} does not support query operation {operation!r}",
            ) from exc

    def assert_query_allowed(self, operation: str, *, execution: bool = False) -> None:
        if execution:
            raise BrokerContractError(
                "execution_not_certified",
                f"broker adapter {self.adapter_id} has no execution authority",
            )
        self.history_window_for(operation)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schemaVersion": BROKER_QUERY_SCHEMA_VERSION,
            "adapterId": self.adapter_id,
            "version": self.version,
            "accountTypes": list(self.account_types),
            "assetClasses": list(self.asset_classes),
            "orderTypes": list(self.order_types),
            "queryOperations": list(self.query_operations),
            "historyWindows": dict(self.operation_windows),
            "supportsStreaming": self.supports_streaming,
            "supportsReplay": self.supports_replay,
            "pagination": self.pagination,
            "rateLimits": self.rate_limits,
            "osRequirements": list(self.os_requirements),
            "credentialScope": self.credential_scope,
            "executionAuthorized": self.execution_authorized,
            "sequenceScope": self.sequence_scope,
            "testOnly": self.test_only,
        }


@dataclass(frozen=True)
class BrokerSourceError:
    source: str
    code: str
    message: str
    retryable: bool = False

    def to_manifest(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class BrokerQueryRequest:
    operation: str
    account: str
    client_request_id: str
    history_start: str | None = None
    history_end: str | None = None
    instruments: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        operation = _required_text(self.operation, "operation").lower()
        account = _required_text(self.account, "account")
        client_request_id = _required_text(self.client_request_id, "client_request_id")
        start = _iso_date(self.history_start, "history_start")
        end = _iso_date(self.history_end, "history_end")
        if (start is None) != (end is None):
            raise BrokerContractError("incomplete_history_range", "history_start and history_end must be supplied together")
        if start and end and start > end:
            raise BrokerContractError("invalid_history_range", "history_start must not be after history_end")
        instruments = tuple(dict.fromkeys(str(item).strip().upper() for item in self.instruments if str(item).strip()))
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "account", account)
        object.__setattr__(self, "client_request_id", client_request_id)
        object.__setattr__(self, "history_start", start)
        object.__setattr__(self, "history_end", end)
        object.__setattr__(self, "instruments", instruments)

    @classmethod
    def for_trade_date(
        cls,
        *,
        adapter_id: str,
        operation: str,
        account: str,
        trade_date: str,
        instruments: tuple[str, ...] = (),
    ) -> "BrokerQueryRequest":
        day = _iso_date(trade_date, "trade_date")
        assert day is not None
        request_id = stable_query_request_id(
            adapter_id=adapter_id,
            account=account,
            operation=operation,
            history_start=day,
            history_end=day,
            instruments=instruments,
        )
        return cls(
            operation=operation,
            account=account,
            client_request_id=request_id,
            history_start=day,
            history_end=day,
            instruments=instruments,
        )


@dataclass(frozen=True)
class BrokerQueryEnvelope:
    adapter_id: str
    operation: str
    account: str
    client_request_id: str
    snapshot_time: str
    sequence: int
    history_start: str | None
    history_end: str | None
    history_scope: str
    complete: bool
    records: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_errors: tuple[BrokerSourceError, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise BrokerContractError("invalid_sequence", "sequence must be non-negative")
        if self.complete and self.source_errors:
            raise BrokerContractError("invalid_completeness", "an envelope with source errors cannot be complete")
        start = _iso_date(self.history_start, "history_start")
        end = _iso_date(self.history_end, "history_end")
        if start and end and start > end:
            raise BrokerContractError("invalid_history_range", "history_start must not be after history_end")
        object.__setattr__(self, "history_start", start)
        object.__setattr__(self, "history_end", end)
        object.__setattr__(self, "records", tuple(dict(item) for item in self.records))
        object.__setattr__(self, "source_errors", tuple(self.source_errors))

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schemaVersion": BROKER_QUERY_SCHEMA_VERSION,
            "adapterId": self.adapter_id,
            "operation": self.operation,
            "account": self.account,
            "clientRequestId": self.client_request_id,
            "snapshotTime": self.snapshot_time,
            "sequence": self.sequence,
            "historyStart": self.history_start,
            "historyEnd": self.history_end,
            "historyScope": self.history_scope,
            "complete": self.complete,
            "records": [dict(item) for item in self.records],
            "sourceErrors": [item.to_manifest() for item in self.source_errors],
        }


class InstrumentResolver(Protocol):
    def resolve_instrument(self, external_symbol: str, *, as_of: str | None = None) -> str: ...


class MarketDataClient(Protocol):
    def query_market_data(self, instrument_ids: tuple[str, ...], *, as_of: str) -> BrokerQueryEnvelope: ...


class BrokerQueryClient(Protocol):
    @property
    def descriptor(self) -> BrokerCapabilityDescriptor: ...

    def query(self, request: BrokerQueryRequest) -> BrokerQueryEnvelope: ...

    def close(self) -> None: ...


# A state-changing broker client is intentionally not defined in this issue.
# Any submit/cancel/replace surface requires a separately approved execution boundary.
