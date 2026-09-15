from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.architecture.state_ownership import CANONICAL_TABLE_WRITERS
from app.broker.qmt_gateway.adapter import QMT_QUERY_DESCRIPTOR, QmtBrokerQueryClient
from app.broker.qmt_gateway.models import QmtAsset, QmtFill, QmtOrder, QmtPosition, QmtQuote
from app.broker.query_contract import BrokerContractError, BrokerQueryEnvelope, BrokerQueryRequest
from app.broker.recorded_query import RecordedBrokerQueryClient
from app.broker.reconciliation import reconcile_broker_history, resolve_unknown_request_outcome


FIXTURE = Path(__file__).parent / "fixtures" / "broker_query" / "recorded_replay.json"


class FakeQmtReadClient:
    def __init__(self) -> None:
        self.connect_count = 0
        self.closed = False

    def ensure_connected(self) -> None:
        self.connect_count += 1

    def query_asset(self) -> QmtAsset:
        return QmtAsset(total_asset=1150.0, cash=350.0)

    def query_positions(self) -> list[QmtPosition]:
        return [QmtPosition("600000.SH", 100.0, 80.0)]

    def query_orders(self) -> list[QmtOrder]:
        return [
            QmtOrder(
                "order-1",
                "600000.SH",
                "BUY",
                100.0,
                20.0,
                10.5,
                "PARTIALLY_FILLED",
                "2026-09-15T01:31:00Z",
                55,
            )
        ]

    def query_fills(self) -> list[QmtFill]:
        return [
            QmtFill(
                "fill-1",
                "order-1",
                "600000.SH",
                "BUY",
                20.0,
                10.5,
                "2026-09-15T01:31:00Z",
            )
        ]

    def query_quotes(self, instruments: list[str]) -> list[QmtQuote]:
        assert instruments == ["SH600000"]
        return [QmtQuote("600000.SH", 10.5, 0, 0, 0, 1000000.0, 10000000.0)]

    def close(self) -> None:
        self.closed = True


class FailingPositionClient(FakeQmtReadClient):
    def query_positions(self) -> list[QmtPosition]:
        raise RuntimeError("simulated provider permission failure")


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _qmt_request(client: QmtBrokerQueryClient, operation: str, *, instruments: tuple[str, ...] = ()) -> BrokerQueryRequest:
    return BrokerQueryRequest.for_trade_date(
        adapter_id="qmt",
        operation=operation,
        account=client.account_ref,
        trade_date=_today(),
        instruments=instruments,
    )


def _recorded_request(client: RecordedBrokerQueryClient, operation: str) -> BrokerQueryRequest:
    return BrokerQueryRequest(
        operation=operation,
        account=client.account_ref,
        client_request_id=f"fixture-{operation}",
        history_start="2026-09-14",
        history_end="2026-09-15",
    )


def test_qmt_and_recorded_clients_share_one_query_envelope_contract():
    qmt = QmtBrokerQueryClient(FakeQmtReadClient(), account_id="sensitive-account-id")
    recorded = RecordedBrokerQueryClient.from_path(FIXTURE)

    qmt_envelope = qmt.query(_qmt_request(qmt, "account"))
    recorded_envelope = recorded.query(_recorded_request(recorded, "account"))

    assert isinstance(qmt_envelope, BrokerQueryEnvelope)
    assert isinstance(recorded_envelope, BrokerQueryEnvelope)
    required = {
        "schemaVersion",
        "adapterId",
        "operation",
        "account",
        "clientRequestId",
        "snapshotTime",
        "sequence",
        "historyStart",
        "historyEnd",
        "historyScope",
        "complete",
        "records",
        "sourceErrors",
    }
    assert required <= set(qmt_envelope.to_manifest())
    assert required <= set(recorded_envelope.to_manifest())
    assert "sensitive-account-id" not in qmt_envelope.account
    assert qmt_envelope.complete is True


def test_qmt_history_is_explicitly_bounded_and_order_fill_history_is_not_overclaimed():
    qmt = QmtBrokerQueryClient(FakeQmtReadClient(), account_id="account")
    orders = qmt.query(_qmt_request(qmt, "orders"))
    fills = qmt.query(_qmt_request(qmt, "fills"))

    assert orders.history_start == _today() == orders.history_end
    assert orders.history_scope == "current_asia_shanghai_session_only"
    assert orders.complete is False
    assert fills.complete is False
    assert fills.records[0]["fee"] is None
    assert fills.records[0]["feeCurrency"] is None
    assert fills.records[0]["sessionCorrelation"].startswith("qmt-session:")

    request = BrokerQueryRequest(
        operation="orders",
        account=qmt.account_ref,
        client_request_id="historical-request",
        history_start="2000-01-01",
        history_end="2000-01-01",
    )
    with pytest.raises(BrokerContractError) as excinfo:
        qmt.query(request)
    assert excinfo.value.code == "unsupported_history"
    assert excinfo.value.details["supportedStart"] == _today()


def test_qmt_partial_source_failure_is_not_an_empty_success():
    qmt = QmtBrokerQueryClient(FailingPositionClient(), account_id="account")
    envelope = qmt.query(_qmt_request(qmt, "positions"))

    assert envelope.records == ()
    assert envelope.complete is False
    assert len(envelope.source_errors) == 1
    assert envelope.source_errors[0].code == "qmt_query_failed"
    assert envelope.source_errors[0].retryable is True


def test_recorded_adapter_preserves_partial_records_and_source_error():
    recorded = RecordedBrokerQueryClient.from_path(FIXTURE)
    positions = recorded.query(_recorded_request(recorded, "positions"))

    assert len(positions.records) == 1
    assert positions.complete is False
    assert positions.source_errors[0].code == "permission_denied"

    outside = BrokerQueryRequest(
        operation="orders",
        account=recorded.account_ref,
        client_request_id="outside-range",
        history_start="2026-09-01",
        history_end="2026-09-01",
    )
    with pytest.raises(BrokerContractError) as excinfo:
        recorded.query(outside)
    assert excinfo.value.code == "unsupported_history"


def test_recorded_reconciliation_is_deterministic_across_duplicates_out_of_order_and_restart():
    first_client = RecordedBrokerQueryClient.from_path(FIXTURE)
    first = reconcile_broker_history(
        first_client.query(_recorded_request(first_client, "orders")),
        first_client.query(_recorded_request(first_client, "fills")),
    )
    second_client = RecordedBrokerQueryClient.from_path(FIXTURE)
    second = reconcile_broker_history(
        second_client.query(_recorded_request(second_client, "orders")),
        second_client.query(_recorded_request(second_client, "fills")),
    )

    assert first.fingerprint == second.fingerprint
    assert first.to_manifest() == second.to_manifest()
    by_id = {item["brokerOrderId"]: item for item in first.orders}
    assert by_id["order-1"]["status"] == "CANCELLED_PARTIAL"
    assert by_id["order-1"]["observedFillQuantity"] == "20.0"
    assert by_id["order-3"]["status"] == "FILLED"
    assert by_id["order-3"]["fills"][0]["eventAtUtc"] < by_id["order-3"]["eventAtUtc"]
    assert first.orphan_fills == ()
    assert len(first.raw_facts) == 8
    assert first.complete is True
    # One fill has no fee evidence, so a bounded report must not prove PnL.
    assert first.economics_proven is False


def test_unknown_request_outcome_reconciles_from_observation_without_resend():
    recorded = RecordedBrokerQueryClient.from_path(FIXTURE)
    orders = recorded.query(_recorded_request(recorded, "orders"))

    resolved = resolve_unknown_request_outcome("intent-unknown-1", orders)
    unresolved = resolve_unknown_request_outcome("intent-never-observed", orders)

    assert resolved == {
        "clientRequestId": "intent-unknown-1",
        "status": "OBSERVED",
        "brokerOrderId": "order-2",
        "brokerStatus": "ACKNOWLEDGED",
        "sourceComplete": True,
        "resendAllowed": False,
    }
    assert unresolved["status"] == "UNKNOWN"
    assert unresolved["resendAllowed"] is False


def test_query_capability_is_read_only_and_execution_cannot_be_inherited():
    manifest = QMT_QUERY_DESCRIPTOR.to_manifest()
    assert manifest["credentialScope"] == "read_only"
    assert manifest["executionAuthorized"] is False
    assert manifest["osRequirements"] == ["windows", "miniqmt_host"]
    assert manifest["historyWindows"]["fills"] == "current_asia_shanghai_session_only"

    with pytest.raises(BrokerContractError) as excinfo:
        QMT_QUERY_DESCRIPTOR.assert_query_allowed("orders", execution=True)
    assert excinfo.value.code == "execution_not_certified"
    with pytest.raises(BrokerContractError) as excinfo:
        QMT_QUERY_DESCRIPTOR.assert_query_allowed("unknown-operation")
    assert excinfo.value.code == "query_operation_unsupported"


def test_broker_query_domain_has_no_qlib_dependency_or_second_ledger_writer():
    backend = Path(__file__).resolve().parents[1]
    files = [
        backend / "app" / "broker" / "query_contract.py",
        backend / "app" / "broker" / "recorded_query.py",
        backend / "app" / "broker" / "reconciliation.py",
        backend / "app" / "broker" / "qmt_gateway" / "adapter.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "qlib" not in source.lower()
    assert "paper_ledger_entries" not in source
    assert "from ..db" not in source
    assert CANONICAL_TABLE_WRITERS["paper_ledger_entries"] == "app/services/paper_order_pipeline.py"
    assert not hasattr(QmtBrokerQueryClient, "submit_order")
    assert not hasattr(QmtBrokerQueryClient, "cancel_order")
