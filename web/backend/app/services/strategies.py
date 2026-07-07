import json
from pathlib import Path
from typing import Any

from ..core.config import PLATFORM_DIR


TEMPLATE_DIR = PLATFORM_DIR / "strategies" / "templates"


COMMON_HEADER = '''from AlgorithmImports import *
from datetime import datetime
import math

try:
    from ashare_execution import AShareExecutionHelper, apply_ashare_models
except Exception:
    AShareExecutionHelper = None

    def apply_ashare_models(algorithm, security):
        return None


def parameter_value(algorithm, key, default):
    value = algorithm.get_parameter(key)
    return default if value in (None, "") else value


class {class_name}(QCAlgorithm):
    def initialize(self):
        ticker = self.get_parameter("ticker", "SPY").upper()
        self.asset_class = self.get_parameter("assetClass", "equity").lower()
        market = self.get_parameter("market", "usa").lower()
        venue = self.get_parameter("venue", market).lower()
        resolution_name = self.get_parameter("resolution", "daily").lower()
        self.resolution = {{
            "daily": Resolution.DAILY,
            "hour": Resolution.HOUR,
            "minute": Resolution.MINUTE,
            "second": Resolution.SECOND,
            "tick": Resolution.TICK,
        }}.get(resolution_name, Resolution.DAILY)
        if market == "china":
            Market.Add("china", 101)
        elif market == "hongkong":
            Market.Add("hongkong", 102)

        start = datetime.strptime(self.get_parameter("start", "2018-01-01"), "%Y-%m-%d")
        end = datetime.strptime(self.get_parameter("end", "2024-12-31"), "%Y-%m-%d")
        cash = float(
            parameter_value(
                self,
                "initial_cash",
                parameter_value(self, "initialCash", parameter_value(self, "cash", "100000")),
            )
        )
        account_currency = "CNY" if market == "china" else "HKD" if market == "hongkong" else "USD"

        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_account_currency(account_currency)
        self.set_cash(cash)

        if self.asset_class == "crypto":
            security = self.add_crypto(ticker, self.resolution, venue)
            self.symbol = security.symbol
        elif self.asset_class == "future":
            security = self.add_future(
                ticker,
                self.resolution,
                market=venue,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
                contract_depth_offset=0,
            )
            security.set_filter(0, int(self.get_parameter("contractWindowDays", 180)))
            self.symbol = security.symbol
        else:
            security = self.add_equity(ticker, self.resolution, market, data_normalization_mode=DataNormalizationMode.RAW)
            self.symbol = security.symbol
        if market == "china":
            benchmark_ticker = self.get_parameter("benchmarkSymbol", "").upper()
            if not benchmark_ticker:
                raise ValueError("A-share benchmarkSymbol is required; constant benchmark fallback is disabled.")
            try:
                benchmark = self.add_equity(
                    benchmark_ticker,
                    self.resolution,
                    self.get_parameter("benchmarkMarket", market).lower(),
                    data_normalization_mode=DataNormalizationMode.RAW,
                )
                self.benchmark_security = benchmark
                self.set_benchmark(lambda time: self.benchmark_security.price)
            except Exception as exc:
                raise ValueError(f"A-share benchmark unavailable: {{benchmark_ticker}}; backtest is blocked.") from exc
        else:
            self.set_benchmark(self.symbol)
        self.ashare_execution = None
        ashare_rules = self.get_parameter("ashareRules", "False").lower() in {{"1", "true", "yes", "on"}}
        if market == "china" and ashare_rules and AShareExecutionHelper is not None:
            apply_ashare_models(self, security)
            self.ashare_execution = AShareExecutionHelper(self, self.get_parameter("ashareStatusFile", "/Lean/Run/ashare_trade_status.json"))
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
        self.fast = self.ema(self.symbol, fast_period, self.resolution)
        self.slow = self.ema(self.symbol, slow_period, self.resolution)
        self.set_warm_up(max(fast_period, slow_period), self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
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
        self.fast = self.sma(self.symbol, fast_period, self.resolution)
        self.slow = self.sma(self.symbol, slow_period, self.resolution)
        self.set_warm_up(max(fast_period, slow_period), self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
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
        self.macd = self.macd(self.symbol, fast, slow, signal, MovingAverageType.EXPONENTIAL, self.resolution)
        self.set_warm_up(slow + signal, self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.macd.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.macd.current.value > self.macd.signal.current.value and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.macd.current.value < self.macd.signal.current.value and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
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
        self.rsi = self.rsi(self.symbol, period, MovingAverageType.WILDERS, self.resolution)
        self.set_warm_up(period, self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.rsi.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.rsi.current.value < self.buy_below and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.rsi.current.value > self.sell_above and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("RSI", "RSI", self.rsi.current.value)
''',
    },
    "donchian_breakout": {
        "key": "donchian_breakout",
        "name": "Donchian Breakout",
        "description": "Trend-following breakout using rolling high and low channels.",
        "parameters": [
            {"key": "lookback", "label": "Lookback", "type": "number", "default": 20, "min": 2},
            {"key": "exitLookback", "label": "Exit Lookback", "type": "number", "default": 10, "min": 2},
        ],
        "body": '''        self.lookback = int(self.get_parameter("lookback", 20))
        self.exit_lookback = int(self.get_parameter("exitLookback", 10))
        self.highs = []
        self.lows = []
        self.set_warm_up(max(self.lookback, self.exit_lookback), self.resolution)

    def on_data(self, data):
        if not data.contains_key(self.symbol):
            return
        bar = data[self.symbol]
        previous_high = max(self.highs[-self.lookback:]) if len(self.highs) >= self.lookback else None
        previous_low = min(self.lows[-self.exit_lookback:]) if len(self.lows) >= self.exit_lookback else None
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        self.highs = self.highs[-max(self.lookback, self.exit_lookback):]
        self.lows = self.lows[-max(self.lookback, self.exit_lookback):]
        if self.is_warming_up or previous_high is None or previous_low is None:
            return
        invested = self.portfolio[self.symbol].invested
        if float(bar.close) > previous_high and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif float(bar.close) < previous_low and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("Donchian", "Upper", previous_high)
        self.plot("Donchian", "Lower", previous_low)
''',
    },
    "bollinger_reversion": {
        "key": "bollinger_reversion",
        "name": "Bollinger Reversion",
        "description": "Mean reversion template using rolling close bands.",
        "parameters": [
            {"key": "period", "label": "Period", "type": "number", "default": 20, "min": 2},
            {"key": "deviation", "label": "Deviation", "type": "number", "default": 2.0, "min": 0.1},
        ],
        "body": '''        self.period = int(self.get_parameter("period", 20))
        self.deviation = float(self.get_parameter("deviation", 2.0))
        self.closes = []
        self.set_warm_up(self.period, self.resolution)

    def on_data(self, data):
        if not data.contains_key(self.symbol):
            return
        close = float(data[self.symbol].close)
        self.closes.append(close)
        self.closes = self.closes[-self.period:]
        if self.is_warming_up or len(self.closes) < self.period:
            return
        mean = sum(self.closes) / len(self.closes)
        variance = sum((value - mean) ** 2 for value in self.closes) / len(self.closes)
        band_width = self.deviation * math.sqrt(variance)
        lower = mean - band_width
        upper = mean + band_width
        invested = self.portfolio[self.symbol].invested
        if close < lower and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif close > mean and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("Bollinger", "Middle", mean)
        self.plot("Bollinger", "Upper", upper)
        self.plot("Bollinger", "Lower", lower)
''',
    },
    "etf_rotation": {
        "key": "etf_rotation",
        "name": "ETF Momentum Rotation",
        "description": "Rotate into the strongest ETF by rolling momentum.",
        "parameters": [
            {"key": "symbols", "label": "ETF Symbols", "type": "text", "default": "SPY,QQQ,IWM"},
            {"key": "lookback", "label": "Momentum Lookback", "type": "number", "default": 63, "min": 2},
            {"key": "rebalanceDays", "label": "Rebalance Days", "type": "number", "default": 21, "min": 1},
        ],
        "body": '''        raw_symbols = self.get_parameter("symbols", ticker)
        self.lookback = int(self.get_parameter("lookback", 63))
        self.rebalance_days = int(self.get_parameter("rebalanceDays", 21))
        self.last_rebalance = None
        self.rotation_symbols = []
        self.price_history = {}
        seen = set()
        for item in raw_symbols.split(","):
            rotation_ticker = item.strip().upper()
            if not rotation_ticker or rotation_ticker in seen:
                continue
            seen.add(rotation_ticker)
            rotation_security = security if rotation_ticker == ticker else self.add_equity(rotation_ticker, self.resolution, market, data_normalization_mode=DataNormalizationMode.RAW)
            self.rotation_symbols.append(rotation_security.symbol)
            self.price_history[rotation_security.symbol] = []
        self.set_warm_up(self.lookback, self.resolution)

    def on_data(self, data):
        for rotation_symbol in self.rotation_symbols:
            if data.contains_key(rotation_symbol):
                history = self.price_history[rotation_symbol]
                history.append(float(data[rotation_symbol].close))
                self.price_history[rotation_symbol] = history[-self.lookback:]
        if self.is_warming_up:
            return
        today = self.time.date()
        if self.last_rebalance and (today - self.last_rebalance).days < self.rebalance_days:
            return
        scores = []
        for rotation_symbol in self.rotation_symbols:
            history = self.price_history.get(rotation_symbol) or []
            if len(history) >= self.lookback and history[0] > 0:
                scores.append((history[-1] / history[0] - 1.0, rotation_symbol))
        if not scores:
            return
        scores.sort(reverse=True, key=lambda item: item[0])
        winner = scores[0][1]
        for rotation_symbol in self.rotation_symbols:
            self.set_holdings(rotation_symbol, 1.0 if rotation_symbol == winner else 0.0)
        self.last_rebalance = today
        self.plot("Rotation", "BestMomentum", scores[0][0])
''',
    },
    "crypto_momentum": {
        "key": "crypto_momentum",
        "name": "Crypto Momentum",
        "description": "Momentum template for 24/7 crypto pairs using ROC.",
        "parameters": [
            {"key": "lookback", "label": "ROC Lookback", "type": "number", "default": 20, "min": 1},
            {"key": "threshold", "label": "Threshold", "type": "number", "default": 0, "min": -100},
        ],
        "body": '''        lookback = int(self.get_parameter("lookback", 20))
        self.threshold = float(self.get_parameter("threshold", 0))
        self.roc = self.roc(self.symbol, lookback, self.resolution)
        self.set_warm_up(lookback, self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.roc.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.roc.current.value > self.threshold and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.roc.current.value <= self.threshold and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("Momentum", "ROC", self.roc.current.value)
''',
    },
    "future_trend": {
        "key": "future_trend",
        "name": "Futures Trend",
        "description": "Continuous futures trend-following template with fractional exposure.",
        "parameters": [
            {"key": "fast", "label": "Fast EMA", "type": "number", "default": 5, "min": 1},
            {"key": "slow", "label": "Slow EMA", "type": "number", "default": 20, "min": 1},
            {"key": "target", "label": "Target Exposure", "type": "number", "default": 0.2, "min": 0},
            {"key": "contractWindowDays", "label": "Contract Window", "type": "number", "default": 180, "min": 1},
        ],
        "body": '''        fast_period = int(self.get_parameter("fast", 5))
        slow_period = int(self.get_parameter("slow", 20))
        self.target = float(self.get_parameter("target", 0.2))
        self.fast = self.ema(self.symbol, fast_period, self.resolution)
        self.slow = self.ema(self.symbol, slow_period, self.resolution)
        self.set_warm_up(max(fast_period, slow_period), self.resolution)

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.fast.current.value > self.slow.current.value and not invested:
            self.ashare_execution.target_percent(self.symbol, self.target) if self.ashare_execution else self.set_holdings(self.symbol, self.target)
        elif self.fast.current.value < self.slow.current.value and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("EMA", "Fast", self.fast.current.value)
        self.plot("EMA", "Slow", self.slow.current.value)
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
        self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        self.has_bought = True
''',
    },
    "blank": {
        "key": "blank",
        "name": "Blank Custom",
        "description": "Minimal project for writing a custom strategy.",
        "parameters": [],
        "body": '''        self.set_warm_up(1, self.resolution)

    def on_data(self, data):
        if self.is_warming_up:
            return
        # Write custom strategy logic here.
''',
    },
}


COMMON_FOOTER = '''
    def on_order_event(self, order_event):
        if self.ashare_execution:
            self.ashare_execution.on_order_event(order_event)
'''


def _file_templates() -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    if not TEMPLATE_DIR.exists():
        return templates
    for manifest_path in sorted(TEMPLATE_DIR.glob("*/manifest.json")):
        body_path = manifest_path.parent / "body.py"
        if not body_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid strategy template manifest: {manifest_path}") from exc
        key = str(manifest.get("key") or manifest_path.parent.name)
        templates[key] = {
            **manifest,
            "key": key,
            "body": body_path.read_text(encoding="utf-8"),
            "template_path": str(manifest_path.parent),
        }
    return templates


def _templates() -> dict[str, dict[str, Any]]:
    return {**TEMPLATES, **_file_templates()}


def list_templates() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in template.items() if key != "body"}
        for template in _templates().values()
    ]


def get_template(template_key: str | None) -> dict[str, Any]:
    key = template_key or "ema_cross"
    templates = _templates()
    if key not in templates:
        raise ValueError(f"Unknown strategy template: {template_key}")
    return templates[key]


def render_python_template(class_name: str, template_key: str | None = None) -> str:
    template = get_template(template_key)
    return COMMON_HEADER.format(class_name=class_name) + template["body"] + COMMON_FOOTER
