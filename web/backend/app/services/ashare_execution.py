from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ashare_repository import status_payload


ASHARE_EXECUTION_HELPER_SOURCE = r'''from AlgorithmImports import *
import json
from pathlib import Path


def _parameter(algorithm, key, default=None):
    try:
        value = algorithm.get_parameter(key, default)
    except TypeError:
        value = algorithm.get_parameter(key)
    return default if value in (None, "") else value


def _float_parameter(algorithm, key, default):
    try:
        return float(_parameter(algorithm, key, default))
    except (TypeError, ValueError):
        return float(default)


def _int_parameter(algorithm, key, default):
    try:
        return int(float(_parameter(algorithm, key, default)))
    except (TypeError, ValueError):
        return int(default)


def _date_key(algorithm):
    return algorithm.time.strftime("%Y-%m-%d")


def _symbol_key(symbol):
    value = getattr(symbol, "value", None) or getattr(symbol, "Value", None) or str(symbol)
    return str(value).upper()


class AShareFeeModel(FeeModel):
    def __init__(self, algorithm):
        self.currency = "CNY"
        self.commission_rate = _float_parameter(algorithm, "commissionRate", 0.0001)
        self.min_commission = _float_parameter(algorithm, "minCommission", 0.0)
        self.stamp_tax_sell = _float_parameter(algorithm, "stampTaxSell", 0.0005)
        self.transfer_fee_rate = _float_parameter(algorithm, "transferFeeRate", 0.00001)

    def GetOrderFee(self, parameters):
        price = float(parameters.Security.Price)
        quantity = float(parameters.Order.Quantity)
        trade_value = abs(price * quantity)
        commission = max(trade_value * self.commission_rate, self.min_commission) if trade_value > 0 else 0
        stamp_tax = trade_value * self.stamp_tax_sell if quantity < 0 else 0
        transfer_fee = trade_value * self.transfer_fee_rate
        return OrderFee(CashAmount(commission + stamp_tax + transfer_fee, self.currency))


def _make_slippage_model(algorithm):
    model_class = globals().get("ConstantSlippageModel")
    if model_class is None:
        return None
    return model_class(_float_parameter(algorithm, "slippageBps", 5.0) / 10000.0)


def apply_ashare_models(algorithm, security):
    fee_model = AShareFeeModel(algorithm)
    try:
        security.set_fee_model(fee_model)
    except AttributeError:
        security.FeeModel = fee_model
    slippage_model = _make_slippage_model(algorithm)
    if slippage_model is None:
        algorithm.debug("AShare slippage model unavailable in this LEAN image; using cash-side slippage buffer only.")
        return
    try:
        security.set_slippage_model(slippage_model)
    except AttributeError:
        security.SlippageModel = slippage_model


class AShareExecutionHelper:
    def __init__(self, algorithm, status_file=None):
        self.algorithm = algorithm
        self.status_file = status_file or _parameter(algorithm, "ashareStatusFile", "/Lean/Run/ashare_trade_status.json")
        self.lot_size = _int_parameter(algorithm, "lotSize", 100)
        self.min_cash_buffer = _float_parameter(algorithm, "cashBuffer", 0.0)
        self.execution_policy = str(_parameter(algorithm, "executionPolicy", "next_open")).lower()
        self.next_open_gap_buffer_bps = _float_parameter(algorithm, "nextOpenGapBufferBps", 2000.0)
        self.buy_dates = {}
        self.registered_symbols = set()
        self.status = self._load_status()

    def _load_status(self):
        path = Path(str(self.status_file))
        if not path.exists():
            self.algorithm.debug(f"AShare status file missing: {path}")
            return {}
        try:
            with path.open(encoding="utf-8") as file:
                return json.load(file)
        except Exception as exc:
            self.algorithm.debug(f"AShare status file could not be read: {exc}")
            return {}

    def _status(self, symbol):
        return self.status.get(_symbol_key(symbol), {}).get(_date_key(self.algorithm), {})

    def can_buy(self, symbol):
        item = self._status(symbol)
        if item.get("is_suspended"):
            return False, "suspended"
        if not item.get("can_buy", True) or item.get("is_limit_up"):
            return False, "limit_up_or_blocked"
        return True, "ok"

    def can_sell(self, symbol):
        item = self._status(symbol)
        if item.get("is_suspended"):
            return False, "suspended"
        if not item.get("can_sell", True) or item.get("is_limit_down"):
            return False, "limit_down_or_blocked"
        if self.buy_dates.get(_symbol_key(symbol)) == _date_key(self.algorithm):
            return False, "t_plus_1"
        return True, "ok"

    def on_order_event(self, order_event):
        status = str(getattr(order_event, "status", getattr(order_event, "Status", ""))).lower()
        if "filled" not in status:
            return
        quantity = float(getattr(order_event, "fill_quantity", getattr(order_event, "FillQuantity", 0)) or 0)
        if quantity <= 0:
            return
        symbol = getattr(order_event, "symbol", getattr(order_event, "Symbol", None))
        if symbol is None:
            return
        self.buy_dates[_symbol_key(symbol)] = _date_key(self.algorithm)

    def _round_to_lot(self, quantity):
        if quantity == 0:
            return 0
        sign = 1 if quantity > 0 else -1
        return sign * (abs(int(quantity)) // self.lot_size) * self.lot_size

    def _price(self, symbol):
        return float(self.algorithm.securities[symbol].price)

    def _holding_quantity(self, symbol):
        return int(float(self.algorithm.portfolio[symbol].quantity))

    def _open_orders(self, symbol):
        transactions = getattr(self.algorithm, "transactions", getattr(self.algorithm, "Transactions", None))
        if transactions is None:
            return []
        try:
            return list(transactions.get_open_orders(symbol))
        except AttributeError:
            try:
                return list(transactions.GetOpenOrders(symbol))
            except AttributeError:
                return []

    def _block_when_order_pending(self, symbol):
        if not self._open_orders(symbol):
            return False
        self.algorithm.debug(f"AShare order blocked {_symbol_key(symbol)} pending_open_order")
        return True

    def _ensure_models(self, symbol):
        key = _symbol_key(symbol)
        if key in self.registered_symbols:
            return
        apply_ashare_models(self.algorithm, self.algorithm.securities[symbol])
        self.registered_symbols.add(key)

    def _available_cash(self):
        try:
            return float(self.algorithm.portfolio.cash) - self.min_cash_buffer
        except Exception:
            return float(self.algorithm.portfolio.total_portfolio_value) - self.min_cash_buffer

    def _buy_fee_buffer(self, trade_value):
        commission = max(trade_value * _float_parameter(self.algorithm, "commissionRate", 0.0001), _float_parameter(self.algorithm, "minCommission", 0.0))
        transfer = trade_value * _float_parameter(self.algorithm, "transferFeeRate", 0.00001)
        slippage = trade_value * _float_parameter(self.algorithm, "slippageBps", 5.0) / 10000.0
        return commission + transfer + slippage

    def _reserved_buy_price(self, price):
        if self.execution_policy != "next_open":
            return price
        return price * (1.0 + max(0.0, self.next_open_gap_buffer_bps) / 10000.0)

    def target_percent(self, symbol, target_percent):
        target_percent = max(0.0, float(target_percent))
        self._ensure_models(symbol)
        if self._block_when_order_pending(symbol):
            return None
        price = self._price(symbol)
        if price <= 0:
            return None
        total_value = float(self.algorithm.portfolio.total_portfolio_value)
        current_quantity = self._holding_quantity(symbol)
        desired_quantity = self._round_to_lot((total_value * target_percent) / price)
        delta = desired_quantity - current_quantity
        if delta > 0:
            can_trade, reason = self.can_buy(symbol)
            if not can_trade:
                self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} {reason}")
                return None
            reserved_price = self._reserved_buy_price(price)
            max_affordable = self._round_to_lot(
                (self._available_cash() - self._buy_fee_buffer(delta * reserved_price)) / reserved_price
            )
            quantity = min(delta, max_affordable)
            quantity = self._round_to_lot(quantity)
            if quantity <= 0:
                self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} insufficient_cash_or_lot")
                return None
            self.buy_dates[_symbol_key(symbol)] = _date_key(self.algorithm)
            return self.algorithm.market_order(symbol, quantity)
        if delta < 0:
            can_trade, reason = self.can_sell(symbol)
            if not can_trade:
                self.algorithm.debug(f"AShare sell blocked {_symbol_key(symbol)} {reason}")
                return None
            available_to_sell = max(0, current_quantity)
            quantity = -self._round_to_lot(min(abs(delta), available_to_sell))
            if quantity == 0:
                self.algorithm.debug(f"AShare sell blocked {_symbol_key(symbol)} no_available_long_position")
                return None
            return self.algorithm.market_order(symbol, quantity)
        return None

    def exit(self, symbol):
        self._ensure_models(symbol)
        if self._block_when_order_pending(symbol):
            return None
        current_quantity = self._holding_quantity(symbol)
        if current_quantity <= 0:
            return None
        can_trade, reason = self.can_sell(symbol)
        if not can_trade:
            self.algorithm.debug(f"AShare sell blocked {_symbol_key(symbol)} {reason}")
            return None
        sell_quantity = -self._round_to_lot(current_quantity)
        if sell_quantity == 0:
            return None
        return self.algorithm.market_order(symbol, sell_quantity)
'''


def write_ashare_execution_artifacts(run_dir: Path, parameters: dict[str, Any]) -> dict[str, str] | None:
    if not parameters.get("ashareRules"):
        return None
    symbol = str(parameters["ticker"]).upper()
    start = str(parameters["start"])
    end = str(parameters["end"])
    run_dir.mkdir(parents=True, exist_ok=True)
    helper_path = run_dir / "ashare_execution.py"
    status_path = run_dir / "ashare_trade_status.json"
    helper_path.write_text(ASHARE_EXECUTION_HELPER_SOURCE, encoding="utf-8")
    status_path.write_text(json.dumps(status_payload(symbol, start, end), indent=2), encoding="utf-8")
    return {"helper": str(helper_path), "status": str(status_path)}
