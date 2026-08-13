        self.lookback = int(self.get_parameter("lookback", 20))
        self.exit_lookback = int(self.get_parameter("exitLookback", 10))
        self.highs = []
        self.lows = []
        self.set_warm_up(max(self.lookback, self.exit_lookback), self.resolution)

    def on_data(self, data):
        if not has_fresh_data(data, self.symbol):
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
            self.ashare_execution.target_percent_moo(self.symbol, 1, "donchian_breakout_buy") if self.ashare_execution else self.set_holdings(self.symbol, 1)
        elif float(bar.close) < previous_low and invested:
            self.ashare_execution.exit_moo(self.symbol, "donchian_breakout_sell") if self.ashare_execution else self.liquidate(self.symbol)
        self.plot("Donchian", "Upper", previous_high)
        self.plot("Donchian", "Lower", previous_low)
