from typing import Any


COMMON_HEADER = '''from AlgorithmImports import *
from datetime import datetime


class {class_name}(QCAlgorithm):
    def initialize(self):
        ticker = self.get_parameter("ticker", "SPY").upper()
        market = self.get_parameter("market", "usa").lower()
        if market == "china":
            Market.Add("china", 101)
        elif market == "hongkong":
            Market.Add("hongkong", 102)

        start = datetime.strptime(self.get_parameter("start", "2018-01-01"), "%Y-%m-%d")
        end = datetime.strptime(self.get_parameter("end", "2024-12-31"), "%Y-%m-%d")
        cash = float(self.get_parameter("cash", 100000))
        account_currency = "CNY" if market == "china" else "HKD" if market == "hongkong" else "USD"

        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_account_currency(account_currency)
        self.set_cash(cash)

        equity = self.add_equity(ticker, Resolution.DAILY, market, data_normalization_mode=DataNormalizationMode.RAW)
        self.symbol = equity.symbol
'''


TEMPLATES: dict[str, dict[str, Any]] = {
    "ema_cross": {
        "key": "ema_cross",
        "name": "EMA Cross",
        "description": "Buy when fast EMA is above slow EMA; liquidate when it crosses below.",
        "parameters": [
            {"key": "fast", "label": "Fast EMA", "type": "number", "default": 10, "min": 1},
            {"key": "slow", "label": "Slow EMA", "type": "number", "default": 30, "min": 1},
        ],
        "body": '''        fast_period = int(self.get_parameter("fast", 10))
        slow_period = int(self.get_parameter("slow", 30))
        self.fast = self.ema(self.symbol, fast_period, Resolution.DAILY)
        self.slow = self.ema(self.symbol, slow_period, Resolution.DAILY)
        self.set_warm_up(max(fast_period, slow_period), Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.set_holdings(self.symbol, 1)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.liquidate(self.symbol)
        self.plot("EMA", "Fast", self.fast.current.value)
        self.plot("EMA", "Slow", self.slow.current.value)
''',
    },
    "sma_cross": {
        "key": "sma_cross",
        "name": "SMA Cross",
        "description": "Simple moving average cross-over strategy.",
        "parameters": [
            {"key": "fast", "label": "Fast SMA", "type": "number", "default": 20, "min": 1},
            {"key": "slow", "label": "Slow SMA", "type": "number", "default": 60, "min": 1},
        ],
        "body": '''        fast_period = int(self.get_parameter("fast", 20))
        slow_period = int(self.get_parameter("slow", 60))
        self.fast = self.sma(self.symbol, fast_period, Resolution.DAILY)
        self.slow = self.sma(self.symbol, slow_period, Resolution.DAILY)
        self.set_warm_up(max(fast_period, slow_period), Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.set_holdings(self.symbol, 1)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.liquidate(self.symbol)
        self.plot("SMA", "Fast", self.fast.current.value)
        self.plot("SMA", "Slow", self.slow.current.value)
''',
    },
    "macd": {
        "key": "macd",
        "name": "MACD Trend",
        "description": "Buy on positive MACD histogram, exit on negative histogram.",
        "parameters": [
            {"key": "fast", "label": "Fast", "type": "number", "default": 12, "min": 1},
            {"key": "slow", "label": "Slow", "type": "number", "default": 26, "min": 1},
            {"key": "signal", "label": "Signal", "type": "number", "default": 9, "min": 1},
        ],
        "body": '''        fast = int(self.get_parameter("fast", 12))
        slow = int(self.get_parameter("slow", 26))
        signal = int(self.get_parameter("signal", 9))
        self.macd = self.macd(self.symbol, fast, slow, signal, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
        self.set_warm_up(slow + signal, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self.macd.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.macd.current.value > self.macd.signal.current.value and not invested:
            self.set_holdings(self.symbol, 1)
        elif self.macd.current.value < self.macd.signal.current.value and invested:
            self.liquidate(self.symbol)
        self.plot("MACD", "MACD", self.macd.current.value)
        self.plot("MACD", "Signal", self.macd.signal.current.value)
''',
    },
    "rsi_reversion": {
        "key": "rsi_reversion",
        "name": "RSI Mean Reversion",
        "description": "Buy oversold RSI and exit when RSI recovers.",
        "parameters": [
            {"key": "period", "label": "RSI Period", "type": "number", "default": 14, "min": 1},
            {"key": "buyBelow", "label": "Buy Below", "type": "number", "default": 30, "min": 1},
            {"key": "sellAbove", "label": "Sell Above", "type": "number", "default": 55, "min": 1},
        ],
        "body": '''        period = int(self.get_parameter("period", 14))
        self.buy_below = float(self.get_parameter("buyBelow", 30))
        self.sell_above = float(self.get_parameter("sellAbove", 55))
        self.rsi = self.rsi(self.symbol, period, MovingAverageType.WILDERS, Resolution.DAILY)
        self.set_warm_up(period, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self.rsi.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.rsi.current.value < self.buy_below and not invested:
            self.set_holdings(self.symbol, 1)
        elif self.rsi.current.value > self.sell_above and invested:
            self.liquidate(self.symbol)
        self.plot("RSI", "RSI", self.rsi.current.value)
''',
    },
    "buy_hold": {
        "key": "buy_hold",
        "name": "Buy & Hold",
        "description": "Invest once after the first bar and hold.",
        "parameters": [],
        "body": '''        self.has_bought = False

    def on_data(self, data):
        if self.has_bought or not data.contains_key(self.symbol):
            return
        self.set_holdings(self.symbol, 1)
        self.has_bought = True
''',
    },
    "blank": {
        "key": "blank",
        "name": "Blank Custom",
        "description": "Minimal project for writing a custom strategy.",
        "parameters": [],
        "body": '''        self.set_warm_up(1, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return
        # Write custom strategy logic here.
''',
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in template.items() if key != "body"}
        for template in TEMPLATES.values()
    ]


def get_template(template_key: str | None) -> dict[str, Any]:
    key = template_key or "ema_cross"
    if key not in TEMPLATES:
        raise ValueError(f"Unknown strategy template: {template_key}")
    return TEMPLATES[key]


def render_python_template(class_name: str, template_key: str | None = None) -> str:
    template = get_template(template_key)
    return COMMON_HEADER.format(class_name=class_name) + template["body"]
