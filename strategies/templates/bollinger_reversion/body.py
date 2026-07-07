        self.period = int(self.get_parameter("period", 20))
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
