        raw_symbols = self.get_parameter("symbols", ticker)
        self.lookback = int(self.get_parameter("lookback", 20))
        self.top_n = int(self.get_parameter("topN", 2))
        self.rebalance_days = int(self.get_parameter("rebalanceDays", 5))
        self.gap_weight = float(self.get_parameter("gapWeight", 0.25))
        self.volume_weight = float(self.get_parameter("volumeWeight", 0.1))
        self.last_rebalance = None
        self.selection_symbols = []
        self.bar_history = {}
        seen = set()
        for item in raw_symbols.split(","):
            asset_ticker = item.strip().upper()
            if not asset_ticker or asset_ticker in seen:
                continue
            seen.add(asset_ticker)
            asset = security if asset_ticker == ticker else self.add_equity(asset_ticker, self.resolution, market, data_normalization_mode=DataNormalizationMode.RAW)
            self.selection_symbols.append(asset.symbol)
            self.bar_history[asset.symbol] = []
        self.set_warm_up(self.lookback + 1, self.resolution)

    def on_data(self, data):
        for asset_symbol in self.selection_symbols:
            if data.contains_key(asset_symbol):
                bar = data[asset_symbol]
                history = self.bar_history[asset_symbol]
                history.append((float(bar.open), float(bar.close), float(bar.volume)))
                self.bar_history[asset_symbol] = history[-(self.lookback + 1):]
        if self.is_warming_up:
            return
        today = self.time.date()
        if self.last_rebalance and (today - self.last_rebalance).days < self.rebalance_days:
            return
        scores = []
        for asset_symbol in self.selection_symbols:
            history = self.bar_history.get(asset_symbol) or []
            if len(history) < self.lookback + 1:
                continue
            previous_close = history[-2][1]
            start_close = history[0][1]
            average_volume = sum(item[2] for item in history[:-1]) / max(1, len(history) - 1)
            if previous_close <= 0 or start_close <= 0 or average_volume <= 0:
                continue
            latest = history[-1]
            momentum = latest[1] / start_close - 1.0
            opening_gap = latest[0] / previous_close - 1.0
            relative_volume = latest[2] / average_volume - 1.0
            score = momentum + self.gap_weight * opening_gap + self.volume_weight * relative_volume
            scores.append((score, asset_symbol))
        if not scores:
            return
        scores.sort(reverse=True, key=lambda item: item[0])
        winners = {symbol for _, symbol in scores[:min(self.top_n, len(scores))]}
        target_weight = 1.0 / len(winners)
        for asset_symbol in self.selection_symbols:
            self.set_holdings(asset_symbol, target_weight if asset_symbol in winners else 0.0)
        self.last_rebalance = today
        self.plot("TurningPoint", "BestScore", scores[0][0])
