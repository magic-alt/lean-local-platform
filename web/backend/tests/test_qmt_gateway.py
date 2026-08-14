from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.broker.qmt_gateway import GatewaySettings, create_app
from app.broker.qmt_gateway.cli import _loopback_host
from app.broker.qmt_gateway.models import QmtAsset, QmtFill, QmtOrder, QmtPosition, QmtQuote
from app.broker.qmt_gateway.xtquant_client import (
    XtQuantReadOnlyClient,
    _event_time,
    platform_to_qmt_symbol,
    qmt_to_platform_symbol,
)


class FakeQmtClient:
    def __init__(self) -> None:
        self.connect_count = 0

    def ensure_connected(self) -> None:
        self.connect_count += 1

    def query_asset(self) -> QmtAsset:
        return QmtAsset(total_asset=1_150.0, cash=350.0)

    def query_positions(self) -> list[QmtPosition]:
        return [QmtPosition("600000.SH", 100.0, 100.0)]

    def query_orders(self) -> list[QmtOrder]:
        return [QmtOrder("order-1", "600000.SH", "BUY", 100.0, 20.0, 10.5, "PARTIALLY_FILLED", "2026-08-12T01:31:00Z", 55)]

    def query_fills(self) -> list[QmtFill]:
        return [QmtFill("trade-1", "order-1", "600000.SH", "BUY", 20.0, 10.5, "2026-08-12T01:31:00Z")]

    def query_quotes(self, instruments: list[str]) -> list[QmtQuote]:
        assert instruments == ["SH600000"]
        return [QmtQuote("600000.SH", 10.5, 0, 1, 0, 1_000_000.0, 10_000_000.0)]

    def close(self) -> None:
        return None


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _client(tmp_path: Path) -> tuple[TestClient, FakeQmtClient]:
    settings = GatewaySettings(tmp_path, "test-account", "STOCK", 18001, "test-token")
    fake = FakeQmtClient()
    return TestClient(create_app(settings, client=fake)), fake


def test_gateway_is_authenticated_get_only_and_returns_raw_broker_snapshots(tmp_path: Path):
    client, fake = _client(tmp_path)
    trade_date = _today()
    headers = {"Authorization": "Bearer test-token"}

    assert client.get("/v1/account", params={"trade_date": trade_date}).status_code == 401
    account = client.get("/v1/account", params={"trade_date": trade_date}, headers=headers)
    positions = client.get("/v1/positions", params={"trade_date": trade_date}, headers=headers)
    orders = client.get("/v1/orders", params={"trade_date": trade_date}, headers=headers)
    fills = client.get("/v1/fills", params={"trade_date": trade_date}, headers=headers)
    quotes = client.get(
        "/v1/quotes", params={"trade_date": trade_date, "instruments": "SH600000"}, headers=headers
    )

    assert account.json() == {
        "asOfTradeDate": trade_date,
        "snapshotAtUtc": account.json()["snapshotAtUtc"],
        "portfolioValue": 1150.0,
        "cash": 350.0,
    }
    assert "dailyPnlPct" not in account.json()
    assert positions.json()[0]["availableQuantity"] == 100.0
    assert orders.json()[0]["qmtOrderStatus"] == 55
    assert fills.json()[0]["fillId"] == "trade-1"
    assert quotes.json()[0]["adv20Volume"] == 1_000_000.0
    assert fake.connect_count >= 5

    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]) == {
        "/v1/health", "/v1/account", "/v1/positions", "/v1/orders", "/v1/fills", "/v1/quotes"
    }
    assert all(set(operations) == {"get"} for operations in schema["paths"].values())


def test_gateway_rejects_historical_dates_and_non_loopback_binding(tmp_path: Path):
    client, _ = _client(tmp_path)
    response = client.get(
        "/v1/positions",
        params={"trade_date": "2000-01-01"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 422
    assert _loopback_host("127.0.0.1") == "127.0.0.1"
    assert _loopback_host("::1") == "::1"
    with pytest.raises(Exception, match="loopback-only"):
        _loopback_host("0.0.0.0")


def test_symbol_and_qmt_timestamp_mapping_are_strict():
    assert qmt_to_platform_symbol("600000.SH") == "SH600000"
    assert platform_to_qmt_symbol("SZ000001") == "000001.SZ"
    assert _event_time(20260812103015) == "2026-08-12T02:30:15Z"
    assert _event_time(1786501815000) == "2026-08-12T02:30:15Z"


def test_xtquant_client_reconnects_without_exposing_write_operations(tmp_path: Path, monkeypatch):
    package = ModuleType("xtquant")
    constants = ModuleType("xtquant.xtconstant")
    constants.STOCK_BUY = 23
    constants.STOCK_SELL = 24
    trader_module = ModuleType("xtquant.xttrader")
    type_module = ModuleType("xtquant.xttype")

    class Callback:
        def on_disconnected(self) -> None:
            return None

    class Trader:
        instances: list["Trader"] = []

        def __init__(self, path: str, session_id: int) -> None:
            self.path, self.session_id, self.callback, self.stopped = path, session_id, None, False
            self.__class__.instances.append(self)

        def register_callback(self, callback) -> None:
            self.callback = callback

        def start(self) -> None:
            return None

        def connect(self) -> int:
            return 0

        def subscribe(self, account) -> int:
            return 0

        def stop(self) -> None:
            self.stopped = True

        def query_stock_asset(self, account):
            return SimpleNamespace(total_asset=100.0, cash=50.0)

    class Account:
        def __init__(self, account_id: str, account_type: str) -> None:
            self.account_id, self.account_type = account_id, account_type

    package.xtconstant = constants
    trader_module.XtQuantTrader = Trader
    trader_module.XtQuantTraderCallback = Callback
    type_module.StockAccount = Account
    monkeypatch.setitem(sys.modules, "xtquant", package)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", constants)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", trader_module)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", type_module)
    userdata = tmp_path / "userdata_mini"
    userdata.mkdir()
    client = XtQuantReadOnlyClient(GatewaySettings(userdata, "account", "STOCK", 18001, "token"))

    assert client.query_asset().cash == 50.0
    first = Trader.instances[0]
    first.callback.on_disconnected()
    assert client.query_asset().cash == 50.0
    assert len(Trader.instances) == 2
    assert first.stopped
    assert not any(name.startswith(("order_", "cancel_")) for name in dir(client))
