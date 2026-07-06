from AlgorithmImports import *
from datetime import datetime

try:
    from ashare_execution import AShareExecutionHelper, apply_ashare_models
except Exception:
    AShareExecutionHelper = None

    def apply_ashare_models(algorithm, security):
        return None


def parameter_value(algorithm, key, default):
    value = algorithm.get_parameter(key)
    return default if value in (None, "") else value


class DockerDemoAlgorithm(QCAlgorithm):
    def initialize(self):
        self.ticker = self.get_parameter("ticker", "SPY").upper()
        self.market = self.get_parameter("market", "usa").lower()
        self.ashare_rules = self.get_parameter("ashareRules", "False").lower() in {"1", "true", "yes", "on"}
        start = datetime.strptime(self.get_parameter("start", "2013-01-01"), "%Y-%m-%d")
        end = datetime.strptime(self.get_parameter("end", "2013-06-30"), "%Y-%m-%d")
        cash = float(
            parameter_value(
                self,
                "initial_cash",
                parameter_value(self, "initialCash", parameter_value(self, "cash", "100000")),
            )
        )
        fast_period = int(self.get_parameter("fast", 10))
        slow_period = int(self.get_parameter("slow", 30))

        if self.market == "china":
            Market.Add("china", 101)

        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_account_currency("CNY" if self.market == "china" else "USD")
        self.set_cash(cash)

        equity = self.add_equity(
            self.ticker,
            Resolution.DAILY,
            self.market,
            data_normalization_mode=DataNormalizationMode.RAW,
        )
        self.symbol = equity.symbol
        if self.market == "china":
            benchmark_ticker = self.get_parameter("benchmarkSymbol", "").upper()
            if not benchmark_ticker:
                raise ValueError("A-share benchmarkSymbol is required; constant benchmark fallback is disabled.")
            try:
                benchmark = self.add_equity(
                    benchmark_ticker,
                    Resolution.DAILY,
                    self.get_parameter("benchmarkMarket", self.market).lower(),
                    data_normalization_mode=DataNormalizationMode.RAW,
                )
                self.set_benchmark(benchmark.symbol)
            except Exception as exc:
                raise ValueError(f"A-share benchmark unavailable: {benchmark_ticker}; backtest is blocked.") from exc
        else:
            self.set_benchmark(self.symbol)
        self.ashare_execution = None
        if self.ashare_rules and AShareExecutionHelper is not None:
            apply_ashare_models(self, equity)
            self.ashare_execution = AShareExecutionHelper(self, self.get_parameter("ashareStatusFile", "/Lean/Run/ashare_trade_status.json"))
        self.fast = self.ema(self.symbol, fast_period, Resolution.DAILY)
        self.slow = self.ema(self.symbol, slow_period, Resolution.DAILY)

        self.set_warm_up(max(fast_period, slow_period), Resolution.DAILY)
        self.debug(
            f"Running EMA cross demo ticker={self.ticker} start={start:%Y-%m-%d} "
            f"end={end:%Y-%m-%d} fast={fast_period} slow={slow_period} cash={cash:.2f}"
        )

    def on_data(self, data):
        if self.is_warming_up or not self.fast.is_ready or not self.slow.is_ready:
            return

        invested = self.portfolio[self.symbol].invested
        fast = self.fast.current.value
        slow = self.slow.current.value

        if fast > slow and not invested:
            if self.ashare_execution:
                self.ashare_execution.target_percent(self.symbol, 1)
            else:
                self.set_holdings(self.symbol, 1)
            self.debug(f"BUY {self.ticker} fast={fast:.2f} slow={slow:.2f}")
        elif fast < slow and invested:
            if self.ashare_execution:
                self.ashare_execution.exit(self.symbol)
            else:
                self.liquidate(self.symbol)
            self.debug(f"SELL {self.ticker} fast={fast:.2f} slow={slow:.2f}")

        self.plot("EMA", "Fast", fast)
        self.plot("EMA", "Slow", slow)

    def on_order_event(self, order_event):
        if self.ashare_execution:
            self.ashare_execution.on_order_event(order_event)

    def on_end_of_algorithm(self):
        self.debug(f"Final portfolio value: {self.portfolio.total_portfolio_value:.2f}")
