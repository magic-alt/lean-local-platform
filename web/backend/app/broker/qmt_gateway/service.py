from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ..query_contract import BrokerQueryEnvelope, BrokerQueryRequest
from .adapter import QmtBrokerQueryClient
from .xtquant_client import QmtReadOnlyClient


class QmtGatewayService:
    """Read-only QMT boundary backed by the unified BrokerQueryClient contract."""

    def __init__(self, client: QmtReadOnlyClient):
        self.client = client
        settings = getattr(client, "settings", None)
        account_id = str(getattr(settings, "account_id", None) or "gateway-account")
        self.query_client = QmtBrokerQueryClient(client, account_id=account_id)

    @staticmethod
    def _trade_date(value: str) -> date:
        requested = date.fromisoformat(value)
        current = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if requested != current:
            raise ValueError("QMT gateway only supports the current Asia/Shanghai trade date")
        return requested

    @staticmethod
    def _snapshot_at_utc() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def health(self) -> dict[str, object]:
        try:
            self.client.ensure_connected()
        except Exception as exc:
            return {"status": "degraded", "reason": str(exc), "qmtConnected": False}
        return {"status": "ready", "qmtConnected": True}

    def capability(self) -> dict[str, object]:
        return self.query_client.descriptor.to_manifest()

    def query_envelope(
        self,
        operation: str,
        trade_date: str,
        *,
        instruments: list[str] | None = None,
    ) -> BrokerQueryEnvelope:
        # Preserve the public current-session boundary while the adapter carries
        # a machine-readable unsupported-history error for SDK callers.
        date.fromisoformat(trade_date)
        request = BrokerQueryRequest.for_trade_date(
            adapter_id=self.query_client.descriptor.adapter_id,
            operation=operation,
            account=self.query_client.account_ref,
            trade_date=trade_date,
            instruments=tuple(instruments or ()),
        )
        return self.query_client.query(request)

    @staticmethod
    def _require_source(envelope: BrokerQueryEnvelope) -> None:
        if envelope.source_errors:
            first = envelope.source_errors[0]
            raise RuntimeError(f"{first.code}: {first.message}")

    def account(self, trade_date: str) -> dict[str, object]:
        self._trade_date(trade_date)
        envelope = self.query_envelope("account", trade_date)
        self._require_source(envelope)
        if len(envelope.records) != 1:
            raise RuntimeError("qmt_account_snapshot_missing")
        record = envelope.records[0]
        return {
            "asOfTradeDate": trade_date,
            "snapshotAtUtc": envelope.snapshot_time,
            "portfolioValue": record["portfolioValue"],
            "cash": record["cash"],
        }

    def positions(self, trade_date: str) -> list[dict[str, object]]:
        self._trade_date(trade_date)
        envelope = self.query_envelope("positions", trade_date)
        self._require_source(envelope)
        return [
            {
                "instrument": item["instrument"],
                "quantity": item["quantity"],
                "availableQuantity": item["availableQuantity"],
                "asOfTradeDate": trade_date,
                "snapshotAtUtc": envelope.snapshot_time,
            }
            for item in envelope.records
        ]

    def orders(self, trade_date: str) -> list[dict[str, object]]:
        self._trade_date(trade_date)
        envelope = self.query_envelope("orders", trade_date)
        self._require_source(envelope)
        return [
            {
                "brokerOrderId": item["brokerOrderId"],
                "instrument": item["instrument"],
                "side": item["side"],
                "quantity": item["quantity"],
                "filledQuantity": item["filledQuantity"],
                "limitPrice": item["limitPrice"],
                "status": item["status"],
                "eventAtUtc": item["eventAtUtc"],
                "qmtOrderStatus": item["qmtOrderStatus"],
                "asOfTradeDate": trade_date,
                "snapshotAtUtc": envelope.snapshot_time,
            }
            for item in envelope.records
        ]

    def fills(self, trade_date: str) -> list[dict[str, object]]:
        self._trade_date(trade_date)
        envelope = self.query_envelope("fills", trade_date)
        self._require_source(envelope)
        return [
            {
                "fillId": item["fillId"],
                "brokerOrderId": item["brokerOrderId"],
                "instrument": item["instrument"],
                "side": item["side"],
                "quantity": item["quantity"],
                "price": item["price"],
                "eventAtUtc": item["eventAtUtc"],
                "asOfTradeDate": trade_date,
                "snapshotAtUtc": envelope.snapshot_time,
            }
            for item in envelope.records
        ]

    def quotes(self, trade_date: str, instruments: list[str]) -> list[dict[str, object]]:
        self._trade_date(trade_date)
        envelope = self.query_envelope("quotes", trade_date, instruments=instruments)
        self._require_source(envelope)
        return [
            {
                "instrument": item["instrument"],
                "price": item["price"],
                "paused": item["paused"],
                "isLimitUp": item["isLimitUp"],
                "isLimitDown": item["isLimitDown"],
                "adv20Volume": item["adv20Volume"],
                "adv20Amount": item["adv20Amount"],
                "asOfTradeDate": trade_date,
                "snapshotAtUtc": envelope.snapshot_time,
            }
            for item in envelope.records
        ]

    def close(self) -> None:
        self.query_client.close()
