from __future__ import annotations

from pathlib import Path
from typing import Any


HK_EXECUTION_HELPER_SOURCE = r'''from AlgorithmImports import *


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


class HongKongFeeModel(FeeModel):
    def __init__(self, algorithm):
        self.commission_rate = _float_parameter(algorithm, "commissionRate", 0.0003)
        self.min_commission = _float_parameter(algorithm, "minCommission", 3.0)
        self.stamp_tax_buy = _float_parameter(algorithm, "stampTaxBuy", 0.001)
        self.stamp_tax_sell = _float_parameter(algorithm, "stampTaxSell", 0.001)
        self.sfc_levy = _float_parameter(algorithm, "sfcLevyRate", 0.000027)
        self.afrc_levy = _float_parameter(algorithm, "afrcLevyRate", 0.0000015)
        self.exchange_fee = _float_parameter(algorithm, "exchangeTradingFeeRate", 0.0000565)
        self.settlement_fee = _float_parameter(algorithm, "settlementFeeRate", 0.000042)

    def GetOrderFee(self, parameters):
        price = float(parameters.Security.Price)
        quantity = float(parameters.Order.Quantity)
        value = abs(price * quantity)
        if value <= 0:
            return OrderFee(CashAmount(0, "HKD"))
        commission = max(value * self.commission_rate, self.min_commission)
        stamp_tax = value * (self.stamp_tax_buy if quantity > 0 else self.stamp_tax_sell)
        statutory = value * (self.sfc_levy + self.afrc_levy + self.exchange_fee + self.settlement_fee)
        return OrderFee(CashAmount(commission + stamp_tax + statutory, "HKD"))


def apply_hk_models(algorithm, security):
    fee_model = HongKongFeeModel(algorithm)
    try:
        security.set_fee_model(fee_model)
    except AttributeError:
        security.FeeModel = fee_model
    model_class = globals().get("ConstantSlippageModel")
    if model_class is not None:
        model = model_class(_float_parameter(algorithm, "slippageBps", 5.0) / 10000.0)
        try:
            security.set_slippage_model(model)
        except AttributeError:
            security.SlippageModel = model


class HongKongExecutionHelper:
    def __init__(self, algorithm):
        self.algorithm = algorithm
        self.lot_size = max(1, _int_parameter(algorithm, "lotSize", 1))
        self.cash_buffer = max(0.0, _float_parameter(algorithm, "cashBuffer", 0.0))
        self.gap_buffer = max(0.0, _float_parameter(algorithm, "nextOpenGapBufferBps", 2000.0)) / 10000.0

    def on_order_event(self, order_event):
        return None

    def _round_lot(self, quantity):
        return (max(0, int(quantity)) // self.lot_size) * self.lot_size

    def _open_orders(self, symbol):
        try:
            return list(self.algorithm.transactions.get_open_orders(symbol))
        except AttributeError:
            return list(self.algorithm.Transactions.GetOpenOrders(symbol))

    def _holding(self, symbol):
        return max(0, int(float(self.algorithm.portfolio[symbol].quantity)))

    def _fee_buffer(self, value):
        commission = max(value * _float_parameter(self.algorithm, "commissionRate", 0.0003), _float_parameter(self.algorithm, "minCommission", 3.0))
        rates = (
            _float_parameter(self.algorithm, "stampTaxBuy", 0.001)
            + _float_parameter(self.algorithm, "sfcLevyRate", 0.000027)
            + _float_parameter(self.algorithm, "afrcLevyRate", 0.0000015)
            + _float_parameter(self.algorithm, "exchangeTradingFeeRate", 0.0000565)
            + _float_parameter(self.algorithm, "settlementFeeRate", 0.000042)
            + _float_parameter(self.algorithm, "slippageBps", 5.0) / 10000.0
        )
        return commission + value * rates

    def target_percent(self, symbol, target_percent):
        if self._open_orders(symbol):
            self.algorithm.debug("HongKong order blocked: pending_open_order")
            return None
        price = float(self.algorithm.securities[symbol].price)
        if price <= 0:
            return None
        current = self._holding(symbol)
        desired = self._round_lot(float(self.algorithm.portfolio.total_portfolio_value) * max(0.0, float(target_percent)) / price)
        delta = desired - current
        if delta > 0:
            reserved_price = price * (1.0 + self.gap_buffer)
            try:
                cash = float(self.algorithm.portfolio.cash) - self.cash_buffer
            except Exception:
                cash = float(self.algorithm.portfolio.total_portfolio_value) - self.cash_buffer
            affordable = self._round_lot(max(0.0, cash - self._fee_buffer(delta * reserved_price)) / reserved_price)
            quantity = self._round_lot(min(delta, affordable))
            return self.algorithm.market_order(symbol, quantity) if quantity > 0 else None
        if delta < 0:
            quantity = self._round_lot(min(abs(delta), current))
            return self.algorithm.market_order(symbol, -quantity) if quantity > 0 else None
        return None

    def exit(self, symbol):
        if self._open_orders(symbol):
            return None
        quantity = self._round_lot(self._holding(symbol))
        return self.algorithm.market_order(symbol, -quantity) if quantity > 0 else None
'''


def write_hk_execution_artifacts(run_dir: Path, parameters: dict[str, Any]) -> dict[str, str] | None:
    if not parameters.get("hkRules"):
        return None
    run_dir.mkdir(parents=True, exist_ok=True)
    helper_path = run_dir / "hk_execution.py"
    helper_path.write_text(HK_EXECUTION_HELPER_SOURCE, encoding="utf-8")
    return {"helper": str(helper_path)}
