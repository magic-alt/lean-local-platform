        raw_symbols = self.get_parameter("symbols", ticker)
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
            if has_fresh_data(data, rotation_symbol):
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
        ordered_symbols = [symbol for symbol in self.rotation_symbols if symbol != winner] + [winner]
        for rotation_symbol in ordered_symbols:
            target = 1.0 if rotation_symbol == winner else 0.0
            self.ashare_execution.target_percent_moo(rotation_symbol, target, "etf_rotation_rebalance") if self.ashare_execution else self.set_holdings(rotation_symbol, target)
        self.last_rebalance = today
        self.plot("Rotation", "BestMomentum", scores[0][0])
