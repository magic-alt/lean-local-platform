        if market != "usa":
            raise ValueError("Certified ETF static baseline supports market=usa only.")
        raw_symbols = self.get_parameter("symbols", ticker)
        self.commission_per_order = self._strict_float_parameter(
            "commissionPerOrder", 1.0, 0.0, 100.0
        )
        self.slippage_bps = self._strict_float_parameter(
            "slippageBps", 2.0, 0.0, 100.0
        )
        self.cost_model_id = self.get_parameter(
            "costModelId", "lean-constant-fee-slippage-v1"
        ).strip()
        if not self.cost_model_id:
            raise ValueError("costModelId must be non-empty.")

        self.baseline_symbols = []
        self._ticker_by_symbol = {}
        seen = set()
        for item in raw_symbols.split(","):
            baseline_ticker = item.strip().upper()
            if not baseline_ticker or baseline_ticker in seen:
                continue
            seen.add(baseline_ticker)
            if baseline_ticker == ticker:
                baseline_security = security
                try:
                    baseline_security.set_data_normalization_mode(
                        DataNormalizationMode.ADJUSTED
                    )
                except AttributeError:
                    pass
            else:
                baseline_security = self.add_equity(
                    baseline_ticker,
                    self.resolution,
                    market,
                    data_normalization_mode=DataNormalizationMode.ADJUSTED,
                )
            self._apply_execution_models(baseline_security)
            self.baseline_symbols.append(baseline_security.symbol)
            self._ticker_by_symbol[baseline_security.symbol] = baseline_ticker

        if len(self.baseline_symbols) < 2:
            raise ValueError("Static ETF baseline requires at least two unique symbols.")
        self.target_weight = 1.0 / len(self.baseline_symbols)
        self._invested = False
        self.baseline_trade_count = 0

    def _strict_float_parameter(self, key, default, minimum, maximum):
        raw = self.get_parameter(key, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise ValueError(
                f"{key} must be finite and in [{minimum}, {maximum}]."
            )
        return value

    def _apply_execution_models(self, baseline_security):
        try:
            fee_model = ConstantFeeModel(self.commission_per_order, "USD")
        except TypeError:
            fee_model = ConstantFeeModel(self.commission_per_order)
        try:
            baseline_security.set_fee_model(fee_model)
        except AttributeError:
            baseline_security.FeeModel = fee_model
        slippage_model = ConstantSlippageModel(self.slippage_bps / 10000.0)
        try:
            baseline_security.set_slippage_model(slippage_model)
        except AttributeError:
            baseline_security.SlippageModel = slippage_model

    def _strategy_on_order_event(self, order_event):
        status = str(
            getattr(order_event, "status", getattr(order_event, "Status", ""))
        ).lower()
        if "filled" in status:
            self.baseline_trade_count += 1

    def on_data(self, data):
        if self._invested:
            self.plot("Baseline", "GrossExposure", 1.0)
            return
        if any(
            not has_fresh_data(data, symbol)
            for symbol in self.baseline_symbols
        ):
            return
        for symbol in sorted(
            self.baseline_symbols,
            key=lambda value: self._ticker_by_symbol.get(value, str(value)),
        ):
            self.set_holdings(
                symbol,
                self.target_weight,
                False,
                "etf_static_equal_weight_initial_allocation",
            )
        self._invested = True
        self.plot("Baseline", "GrossExposure", 1.0)

    def on_end_of_algorithm(self):
        self.debug(
            "ETF_STATIC_BASELINE_SUMMARY|"
            f"tradeCount={self.baseline_trade_count}|"
            f"costModelId={self.cost_model_id}"
        )
