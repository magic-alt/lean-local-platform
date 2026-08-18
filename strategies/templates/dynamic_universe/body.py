        import json
        self.universe_schedule = json.loads(self.get_parameter("universeSchedule", "[]"))
        if not self.universe_schedule:
            raise ValueError("universeSchedule is required for a dynamic universe strategy.")
        self.weighting = self.get_parameter("weighting", "equal").lower()
        self.top_n = int(self.get_parameter("topN", 20))
        self.lookback = int(self.get_parameter("lookback", 60))
        self.rebalance_days = int(self.get_parameter("rebalanceDays", 20))
        self.last_rebalance = None
        self.dynamic_symbols = {}
        self.momentum = {}
        market_name = self.get_parameter("market", "china").lower()
        for ticker_value in sorted({row["symbol"] for row in self.universe_schedule}):
            if ticker_value == ticker:
                asset = security
            else:
                asset = self.add_equity(ticker_value, self.resolution, market_name, data_normalization_mode=DataNormalizationMode.RAW)
                if market_name == "china" and self.ashare_execution is not None:
                    apply_ashare_models(self, asset)
            self.dynamic_symbols[ticker_value] = asset.symbol
            self.momentum[ticker_value] = self.roc(asset.symbol, self.lookback, self.resolution)
        self.set_warm_up(self.lookback, self.resolution)

    def _active_tickers(self):
        today = self.time.date().isoformat()
        return {
            row["symbol"] for row in self.universe_schedule
            if row["startDate"] <= today and (not row.get("endDate") or row["endDate"] >= today)
        }

    def on_data(self, data):
        if self.is_warming_up:
            return
        if self.last_rebalance is not None and (self.time.date() - self.last_rebalance).days < self.rebalance_days:
            return
        active = self._active_tickers()
        selected = list(active)
        if self.weighting == "momentum":
            ready = [ticker_value for ticker_value in active if self.momentum[ticker_value].is_ready]
            selected = sorted(ready, key=lambda value: self.momentum[value].current.value, reverse=True)[:self.top_n]
        selected_symbols = {self.dynamic_symbols[value] for value in selected}
        for ticker_value, symbol_value in self.dynamic_symbols.items():
            if self.portfolio[symbol_value].invested and symbol_value not in selected_symbols:
                self.ashare_execution.exit(symbol_value) if self.ashare_execution else self.liquidate(symbol_value)
        if selected_symbols:
            target = 0.95 / len(selected_symbols)
            for symbol_value in selected_symbols:
                if data.contains_key(symbol_value) and not bool(getattr(data[symbol_value], "is_fill_forward", False)):
                    self.ashare_execution.target_percent_moo(symbol_value, target, "dynamic_universe_rebalance") if self.ashare_execution else self.set_holdings(symbol_value, target)
        self.last_rebalance = self.time.date()
