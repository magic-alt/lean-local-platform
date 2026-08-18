        fast = int(self.get_parameter("fast", 12))
        slow = int(self.get_parameter("slow", 26))
        signal = int(self.get_parameter("signal", 9))
        self.macd = self.macd(self.symbol, fast, slow, signal, MovingAverageType.EXPONENTIAL, self.resolution)
        self.set_warm_up(slow + signal, self.resolution)

    def on_data(self, data):
        if not has_fresh_data(data, self.symbol) or self.is_warming_up or not self.macd.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.macd.current.value > self.macd.signal.current.value and not invested:
            self.ashare_execution.target_percent_moo(self.symbol, 1, "macd_buy") if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.macd.current.value < self.macd.signal.current.value and invested:
            self.ashare_execution.exit_moo(self.symbol, "macd_sell") if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("MACD", "MACD", self.macd.current.value)
        self.plot("MACD", "Signal", self.macd.signal.current.value)
