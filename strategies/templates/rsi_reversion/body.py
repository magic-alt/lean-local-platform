        period = int(self.get_parameter("period", 14))
        self.buy_below = float(self.get_parameter("buyBelow", 30))
        self.sell_above = float(self.get_parameter("sellAbove", 55))
        self.rsi = self.rsi(self.symbol, period, MovingAverageType.WILDERS, self.resolution)
        self.set_warm_up(period, self.resolution)

    def on_data(self, data):
        if not has_fresh_data(data, self.symbol) or self.is_warming_up or not self.rsi.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.rsi.current.value < self.buy_below and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.rsi.current.value > self.sell_above and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("RSI", "RSI", self.rsi.current.value)
