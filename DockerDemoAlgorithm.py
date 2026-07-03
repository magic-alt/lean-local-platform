from AlgorithmImports import *
from datetime import datetime


class DockerDemoAlgorithm(QCAlgorithm):
    def initialize(self):
        self.ticker = self.get_parameter("ticker", "SPY").upper()
        start = datetime.strptime(self.get_parameter("start", "2013-01-01"), "%Y-%m-%d")
        end = datetime.strptime(self.get_parameter("end", "2013-06-30"), "%Y-%m-%d")
        cash = float(self.get_parameter("cash", 100000))
        fast_period = int(self.get_parameter("fast", 10))
        slow_period = int(self.get_parameter("slow", 30))

        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_cash(cash)

        equity = self.add_equity(
            self.ticker,
            Resolution.DAILY,
            data_normalization_mode=DataNormalizationMode.RAW,
        )
        self.symbol = equity.symbol
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
            self.set_holdings(self.symbol, 1)
            self.debug(f"BUY {self.ticker} fast={fast:.2f} slow={slow:.2f}")
        elif fast < slow and invested:
            self.liquidate(self.symbol)
            self.debug(f"SELL {self.ticker} fast={fast:.2f} slow={slow:.2f}")

        self.plot("EMA", "Fast", fast)
        self.plot("EMA", "Slow", slow)

    def on_end_of_algorithm(self):
        self.debug(f"Final portfolio value: {self.portfolio.total_portfolio_value:.2f}")
