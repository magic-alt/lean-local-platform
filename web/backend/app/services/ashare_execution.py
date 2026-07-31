from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ashare_repository import status_payload


ASHARE_EXECUTION_HELPER_SOURCE = r'''from AlgorithmImports import *
try:
    from QuantConnect.Orders.Fills import EquityFillModel
except ImportError:
    class EquityFillModel:
        def market_on_open_fill(self, asset, order):
            return None
import json
import math
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
        self.min_commission = _float_parameter(algorithm, "minCommission", 5.0)
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


def _status_document(path_value):
    path = Path(str(path_value))
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def _make_slippage_model(algorithm):
    mode = str(_parameter(algorithm, "slippageModel", "constant")).lower()
    if mode in {"participation", "participation_sqrt", "sqrt_participation"}:
        cached = getattr(algorithm, "_ashare_participation_slippage_model", None)
        if cached is not None:
            return cached

        class AShareParticipationSlippageModel:
            def __init__(self, selected_algorithm):
                self.base = _float_parameter(selected_algorithm, "slippageBps", 5.0) / 10000.0
                self.impact = _float_parameter(selected_algorithm, "participationImpactBps", 25.0) / 10000.0
                self.maximum = _float_parameter(selected_algorithm, "maxSlippageBps", 50.0) / 10000.0

            def get_slippage_approximation(self, asset, order):
                volume = max(0.0, float(getattr(asset, "volume", getattr(asset, "Volume", 0)) or 0))
                participation = abs(float(order.quantity)) / volume if volume > 0 else 1.0
                return float(asset.price) * min(self.maximum, self.base + self.impact * math.sqrt(participation))

        cached = AShareParticipationSlippageModel(algorithm)
        algorithm._ashare_participation_slippage_model = cached
        return cached
    model_class = globals().get("ConstantSlippageModel")
    if model_class is None:
        return AShareParticipationSlippageModel(algorithm)
    return model_class(_float_parameter(algorithm, "slippageBps", 5.0) / 10000.0)


def _make_next_open_fill_model(algorithm):
    enabled = str(_parameter(algorithm, "ashareNextOpenFillModel", "false")).lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None
    cached = getattr(algorithm, "_ashare_next_open_fill_model", None)
    if cached is not None:
        return cached

    class AShareNextOpenFillModel(EquityFillModel):
        def __init__(self, selected_algorithm):
            self.algorithm = selected_algorithm
            self.status = _status_document(_parameter(selected_algorithm, "ashareStatusFile", "/Lean/Run/ashare_trade_status.json"))

        @staticmethod
        def _near(left, right):
            if right in (None, 0):
                return False
            return abs(float(left) - float(right)) <= max(0.001, abs(float(right)) * 0.00005)

        def market_on_open_fill(self, asset, order):
            fill = super().market_on_open_fill(asset, order)
            date_value = self.algorithm.time.strftime("%Y-%m-%d")
            item = self.status.get(_symbol_key(asset.symbol), {}).get(date_value, {})
            direction = getattr(order, "direction", getattr(order, "Direction", None))
            open_price = float(getattr(asset, "open", getattr(asset, "Open", 0)) or 0)
            reason = None
            if not item:
                reason = "trade_status_missing"
            elif item.get("is_suspended"):
                reason = "suspended"
            elif direction == OrderDirection.BUY and self._near(open_price, item.get("limit_up")):
                reason = "limit_up_open"
            elif direction == OrderDirection.SELL and self._near(open_price, item.get("limit_down")):
                reason = "limit_down_open"
            if reason:
                fill.status = OrderStatus.CANCELED
                fill.fill_quantity = 0
                fill.fill_price = 0
                fill.message = f"ashare_next_open_blocked:{reason}"
            return fill

    cached = AShareNextOpenFillModel(algorithm)
    algorithm._ashare_next_open_fill_model = cached
    return cached


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
    fill_model = _make_next_open_fill_model(algorithm)
    if fill_model is not None:
        try:
            security.set_fill_model(fill_model)
        except AttributeError:
            security.FillModel = fill_model


class AShareExecutionHelper:
    def __init__(self, algorithm, status_file=None):
        self.algorithm = algorithm
        self.status_file = status_file or _parameter(algorithm, "ashareStatusFile", "/Lean/Run/ashare_trade_status.json")
        self.lot_size = _int_parameter(algorithm, "lotSize", 100)
        self.min_cash_buffer = _float_parameter(algorithm, "cashBuffer", 0.0)
        self.execution_policy = str(_parameter(algorithm, "executionPolicy", "next_open")).lower()
        self.allow_st_buy = str(_parameter(algorithm, "allowStBuy", "false")).lower() in {"1", "true", "yes", "on"}
        self.next_open_gap_buffer_bps = _float_parameter(algorithm, "nextOpenGapBufferBps", 2000.0)
        self.max_volume_participation = _float_parameter(algorithm, "maxVolumeParticipation", 0.0)
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

    def trade_status(self, symbol):
        return dict(self._status(symbol))

    def can_buy(self, symbol):
        item = self._status(symbol)
        if not item:
            return False, "trade_status_missing"
        if item.get("is_suspended"):
            return False, "suspended"
        if item.get("is_st") and not self.allow_st_buy:
            return False, "st_blocked"
        if not item.get("can_buy", True) or item.get("is_limit_up"):
            return False, "limit_up_or_blocked"
        return True, "ok"

    def can_sell(self, symbol):
        item = self._status(symbol)
        if not item:
            return False, "trade_status_missing"
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
        commission = max(trade_value * _float_parameter(self.algorithm, "commissionRate", 0.0001), _float_parameter(self.algorithm, "minCommission", 5.0))
        transfer = trade_value * _float_parameter(self.algorithm, "transferFeeRate", 0.00001)
        slippage = trade_value * _float_parameter(self.algorithm, "slippageBps", 5.0) / 10000.0
        return commission + transfer + slippage

    def _participation_quantity(self, symbol, quantity):
        volume = float(getattr(self.algorithm.securities[symbol], "volume", 0) or 0)
        if volume <= 0 or self.max_volume_participation <= 0:
            return self._round_to_lot(quantity)
        maximum = self._round_to_lot(volume * self.max_volume_participation)
        return self._round_to_lot(min(abs(quantity), abs(maximum))) * (1 if quantity > 0 else -1)

    def _can_submit_buy(self, symbol):
        item = self._status(symbol)
        if not item:
            return False, "trade_status_missing"
        if item.get("is_suspended"):
            return False, "suspended"
        if item.get("is_st") and not self.allow_st_buy:
            return False, "st_blocked"
        return True, "ok"

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

    def target_percent_moo(self, symbol, target_percent, tag=""):
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
            can_trade, reason = self._can_submit_buy(symbol)
            if not can_trade:
                self.algorithm.debug(f"AShare MOO buy blocked {_symbol_key(symbol)} {reason}")
                return None
            reserved_price = self._reserved_buy_price(price)
            affordable = self._round_to_lot(
                (self._available_cash() - self._buy_fee_buffer(delta * reserved_price)) / reserved_price
            )
            quantity = self._participation_quantity(symbol, min(delta, affordable))
            if quantity <= 0:
                self.algorithm.debug(f"AShare MOO buy blocked {_symbol_key(symbol)} insufficient_cash_capacity_or_lot")
                return None
            return self.algorithm.market_on_open_order(symbol, quantity, tag=tag)
        if delta < 0:
            can_trade, reason = self.can_sell(symbol)
            if not can_trade and reason not in {"limit_down_or_blocked"}:
                self.algorithm.debug(f"AShare MOO sell blocked {_symbol_key(symbol)} {reason}")
                return None
            quantity = self._participation_quantity(symbol, -min(abs(delta), max(0, current_quantity)))
            if quantity >= 0:
                return None
            return self.algorithm.market_on_open_order(symbol, quantity, tag=tag)
        return None

    def exit_moo(self, symbol, tag=""):
        self._ensure_models(symbol)
        if self._block_when_order_pending(symbol):
            return None
        current_quantity = self._holding_quantity(symbol)
        if current_quantity <= 0:
            return None
        can_trade, reason = self.can_sell(symbol)
        if not can_trade and reason not in {"limit_down_or_blocked"}:
            self.algorithm.debug(f"AShare MOO sell blocked {_symbol_key(symbol)} {reason}")
            return None
        quantity = self._participation_quantity(symbol, -current_quantity)
        if quantity >= 0:
            return None
        return self.algorithm.market_on_open_order(symbol, quantity, tag=tag)

    def limit_buy(self, symbol, quantity, limit_price, tag=""):
        self._ensure_models(symbol)
        if self._block_when_order_pending(symbol):
            return None
        can_trade, reason = self.can_buy(symbol)
        if not can_trade:
            self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} {reason}")
            return None
        price = float(limit_price)
        if price <= 0:
            self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} invalid_limit_price")
            return None
        rounded_quantity = self._round_to_lot(abs(int(quantity)))
        if rounded_quantity <= 0:
            self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} invalid_lot_quantity")
            return None
        trade_value = rounded_quantity * price
        affordable_quantity = self._round_to_lot(
            (self._available_cash() - self._buy_fee_buffer(trade_value)) / price
        )
        rounded_quantity = min(rounded_quantity, affordable_quantity)
        rounded_quantity = self._round_to_lot(rounded_quantity)
        if rounded_quantity <= 0:
            self.algorithm.debug(f"AShare buy blocked {_symbol_key(symbol)} insufficient_cash_or_lot")
            return None
        return self.algorithm.limit_order(
            symbol,
            rounded_quantity,
            price,
            tag=tag,
        )

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
    symbols = list(dict.fromkeys([symbol, *[str(value).upper() for value in parameters.get("universeSymbols") or []]]))
    start = str(parameters["start"])
    end = str(parameters["end"])
    run_dir.mkdir(parents=True, exist_ok=True)
    helper_path = run_dir / "ashare_execution.py"
    status_path = run_dir / "ashare_trade_status.json"
    helper_path.write_text(ASHARE_EXECUTION_HELPER_SOURCE, encoding="utf-8")
    payload: dict[str, Any] = {}
    for ticker in symbols:
        payload.update(status_payload(ticker, start, end))
    status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"helper": str(helper_path), "status": str(status_path)}
