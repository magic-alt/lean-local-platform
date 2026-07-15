        lookback = int(self.get_parameter("lookback", 20))
        self.threshold = float(self.get_parameter("threshold", 0))
        self.roc = self.roc(self.symbol, lookback, self.resolution)
        self.set_warm_up(lookback, self.resolution)

    def on_data(self, data):
        if not has_fresh_data(data, self.symbol) or self.is_warming_up or not self.roc.is_ready:
            return
        invested = self.portfolio[self.symbol].invested
        if self.roc.current.value > self.threshold and not invested:
            self.ashare_execution.target_percent(self.symbol, 1) if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif self.roc.current.value <= self.threshold and invested:
            self.ashare_execution.exit(self.symbol) if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("Momentum", "ROC", self.roc.current.value)
