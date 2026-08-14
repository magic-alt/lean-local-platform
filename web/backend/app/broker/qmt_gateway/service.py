from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .xtquant_client import QmtReadOnlyClient, qmt_to_platform_symbol


class QmtGatewayService:
    """Expose raw broker observations; risk, PnL and ledger logic stay in platform."""

    def __init__(self, client: QmtReadOnlyClient) -> None:
        self.client = client

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

    def account(self, trade_date: str) -> dict[str, object]:
        requested = self._trade_date(trade_date)
        self.client.ensure_connected()
        asset = self.client.query_asset()
        return {
            "asOfTradeDate": requested.isoformat(),
            "snapshotAtUtc": self._snapshot_at_utc(),
            "portfolioValue": asset.total_asset,
            "cash": asset.cash,
        }

    def positions(self, trade_date: str) -> list[dict[str, object]]:
        requested = self._trade_date(trade_date)
        self.client.ensure_connected()
        snapshot_at = self._snapshot_at_utc()
        return [
            {
                "instrument": qmt_to_platform_symbol(item.stock_code),
                "quantity": item.volume,
                "availableQuantity": item.can_use_volume,
                "asOfTradeDate": requested.isoformat(),
                "snapshotAtUtc": snapshot_at,
            }
            for item in self.client.query_positions()
        ]

    def orders(self, trade_date: str) -> list[dict[str, object]]:
        requested = self._trade_date(trade_date)
        self.client.ensure_connected()
        snapshot_at = self._snapshot_at_utc()
        return [
            {
                "brokerOrderId": item.order_id,
                "instrument": qmt_to_platform_symbol(item.stock_code),
                "side": item.side,
                "quantity": item.order_volume,
                "filledQuantity": item.traded_volume,
                "limitPrice": item.price,
                "status": item.status,
                "eventAtUtc": item.event_at_utc,
                "qmtOrderStatus": item.raw_status,
                "asOfTradeDate": requested.isoformat(),
                "snapshotAtUtc": snapshot_at,
            }
            for item in self.client.query_orders()
        ]

    def fills(self, trade_date: str) -> list[dict[str, object]]:
        requested = self._trade_date(trade_date)
        self.client.ensure_connected()
        snapshot_at = self._snapshot_at_utc()
        return [
            {
                "fillId": item.trade_id,
                "brokerOrderId": item.order_id,
                "instrument": qmt_to_platform_symbol(item.stock_code),
                "side": item.side,
                "quantity": item.traded_volume,
                "price": item.traded_price,
                "eventAtUtc": item.event_at_utc,
                "asOfTradeDate": requested.isoformat(),
                "snapshotAtUtc": snapshot_at,
            }
            for item in self.client.query_fills()
        ]

    def quotes(self, trade_date: str, instruments: list[str]) -> list[dict[str, object]]:
        requested = self._trade_date(trade_date)
        self.client.ensure_connected()
        snapshot_at = self._snapshot_at_utc()
        return [
            {
                "instrument": qmt_to_platform_symbol(item.stock_code),
                "price": item.price,
                "paused": item.paused,
                "isLimitUp": item.is_limit_up,
                "isLimitDown": item.is_limit_down,
                "adv20Volume": item.adv20_volume,
                "adv20Amount": item.adv20_amount,
                "asOfTradeDate": requested.isoformat(),
                "snapshotAtUtc": snapshot_at,
            }
            for item in self.client.query_quotes(instruments)
        ]
