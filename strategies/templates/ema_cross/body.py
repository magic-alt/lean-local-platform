        fast_period = int(self.get_parameter("fast", 10))
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
