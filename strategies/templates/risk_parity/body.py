        raw_symbols = self.get_parameter("symbols", ticker)
        self.lookback = int(self.get_parameter("lookback", 60))
        self.rebalance_days = int(self.get_parameter("rebalanceDays", 20))
        self.max_weight = float(self.get_parameter("maxWeight", 0.6))
        self.last_rebalance = None
        self.risk_symbols = []
        self.price_history = {}
        seen = set()
        for item in raw_symbols.split(","):
            asset_ticker = item.strip().upper()
            if not asset_ticker or asset_ticker in seen:
                continue
            seen.add(asset_ticker)
            asset = security if asset_ticker == ticker else self.add_equity(asset_ticker, self.resolution, market, data_normalization_mode=DataNormalizationMode.RAW)
            self.risk_symbols.append(asset.symbol)
            self.price_history[asset.symbol] = []
        self.set_warm_up(self.lookback + 1, self.resolution)

    def on_data(self, data):
        for asset_symbol in self.risk_symbols:
            if data.contains_key(asset_symbol):
                history = self.price_history[asset_symbol]
                history.append(float(data[asset_symbol].close))
                self.price_history[asset_symbol] = history[-(self.lookback + 1):]
        if self.is_warming_up:
            return
        today = self.time.date()
        if self.last_rebalance and (today - self.last_rebalance).days < self.rebalance_days:
            return
        inverse_volatility = {}
        for asset_symbol in self.risk_symbols:
            prices = self.price_history.get(asset_symbol) or []
            if len(prices) < self.lookback + 1:
                continue
            returns = [prices[index] / prices[index - 1] - 1.0 for index in range(1, len(prices)) if prices[index - 1] > 0]
            if len(returns) < 2:
                continue
            mean_return = sum(returns) / len(returns)
            variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
            volatility = variance ** 0.5
            if volatility > 0:
                inverse_volatility[asset_symbol] = 1.0 / volatility
        if not inverse_volatility:
            return
        total_inverse_volatility = sum(inverse_volatility.values())
        raw_weights = {symbol: value / total_inverse_volatility for symbol, value in inverse_volatility.items()}
        capped_weights = {symbol: min(weight, self.max_weight) for symbol, weight in raw_weights.items()}
        invested_weight = sum(capped_weights.values())
        if invested_weight <= 0:
            return
        weights = {symbol: weight / invested_weight for symbol, weight in capped_weights.items()}
        for asset_symbol in self.risk_symbols:
            self.set_holdings(asset_symbol, weights.get(asset_symbol, 0.0))
        self.last_rebalance = today
        self.plot("RiskParity", "Assets", len(weights))
