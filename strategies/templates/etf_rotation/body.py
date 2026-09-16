        raw_symbols = self.get_parameter("symbols", ticker)
        self.lookback = self._strict_int_parameter("lookback", 63, 2, 504)
        self.rebalance_days = self._strict_int_parameter("rebalanceDays", 21, 1, 126)
        self.selection_count = self._strict_int_parameter("selectionCount", 2, 1, 20)
        self.volatility_lookback = self._strict_int_parameter("volatilityLookback", 60, 2, 252)
        self.target_volatility = self._strict_float_parameter("targetVolatility", 0.10, 0.01, 1.0)
        self.max_weight = self._strict_float_parameter("maxWeight", 0.60, 0.01, 1.0)
        self.max_turnover = self._strict_float_parameter("maxTurnover", 0.25, 0.01, 1.0)
        self.commission_per_order = self._strict_float_parameter("commissionPerOrder", 1.0, 0.0, 100.0)
        self.slippage_bps = self._strict_float_parameter("slippageBps", 2.0, 0.0, 100.0)
        self.cost_model_id = self.get_parameter("costModelId", "lean-constant-fee-slippage-v1").strip()
        if not self.cost_model_id:
            raise ValueError("costModelId must be non-empty.")

        self.rotation_symbols = []
        self.price_history = {}
        self._ticker_by_symbol = {}
        seen = set()
        normalization_mode = DataNormalizationMode.ADJUSTED if market == "usa" else DataNormalizationMode.RAW
        for item in raw_symbols.split(","):
            rotation_ticker = item.strip().upper()
            if not rotation_ticker or rotation_ticker in seen:
                continue
            seen.add(rotation_ticker)
            if rotation_ticker == ticker:
                rotation_security = security
                if market == "usa":
                    try:
                        rotation_security.set_data_normalization_mode(normalization_mode)
                    except AttributeError:
                        pass
            else:
                rotation_security = self.add_equity(
                    rotation_ticker,
                    self.resolution,
                    market,
                    data_normalization_mode=normalization_mode,
                )
            if market == "usa":
                self._apply_etf_execution_models(rotation_security)
            self.rotation_symbols.append(rotation_security.symbol)
            self.price_history[rotation_security.symbol] = []
            self._ticker_by_symbol[rotation_security.symbol] = rotation_ticker

        if len(self.rotation_symbols) < 2:
            raise ValueError("ETF rotation requires at least two unique symbols.")
        if self.selection_count > len(self.rotation_symbols):
            raise ValueError(
                f"selectionCount={self.selection_count} exceeds symbol count={len(self.rotation_symbols)}."
            )

        self.history_limit = max(self.lookback, self.volatility_lookback) + 1
        self._last_session_date = None
        self._sessions_since_rebalance = self.rebalance_days
        self.rotation_total_turnover = 0.0
        self.rotation_trade_count = 0
        self.rotation_last_failure = ""
        self.set_warm_up(self.history_limit, self.resolution)

    def _strict_int_parameter(self, key, default, minimum, maximum):
        raw = self.get_parameter(key, str(default))
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be an integer.") from exc
        if not math.isfinite(number) or int(number) != number:
            raise ValueError(f"{key} must be an integer.")
        value = int(number)
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be in [{minimum}, {maximum}].")
        return value

    def _strict_float_parameter(self, key, default, minimum, maximum):
        raw = self.get_parameter(key, str(default))
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
        if not math.isfinite(value) or value < minimum or value > maximum:
            raise ValueError(f"{key} must be finite and in [{minimum}, {maximum}].")
        return value

    def _apply_etf_execution_models(self, rotation_security):
        # Costs are delegated to LEAN security models rather than deducted from PnL in strategy logic.
        try:
            fee_model = ConstantFeeModel(self.commission_per_order, "USD")
        except TypeError:
            fee_model = ConstantFeeModel(self.commission_per_order)
        try:
            rotation_security.set_fee_model(fee_model)
        except AttributeError:
            rotation_security.FeeModel = fee_model
        slippage_model = ConstantSlippageModel(self.slippage_bps / 10000.0)
        try:
            rotation_security.set_slippage_model(slippage_model)
        except AttributeError:
            rotation_security.SlippageModel = slippage_model

    def _symbol_key(self, symbol):
        return self._ticker_by_symbol.get(
            symbol,
            str(getattr(symbol, "value", getattr(symbol, "Value", symbol))).upper(),
        )

    def _finite_positive_prices(self, values):
        return bool(values) and all(math.isfinite(value) and value > 0 for value in values)

    def _momentum_and_volatility(self, symbol):
        prices = self.price_history.get(symbol) or []
        required = max(self.lookback, self.volatility_lookback) + 1
        if len(prices) < required:
            return None
        momentum_prices = prices[-(self.lookback + 1):]
        volatility_prices = prices[-(self.volatility_lookback + 1):]
        if not self._finite_positive_prices(momentum_prices):
            return None
        if not self._finite_positive_prices(volatility_prices):
            return None
        momentum = momentum_prices[-1] / momentum_prices[0] - 1.0
        returns = [
            volatility_prices[index] / volatility_prices[index - 1] - 1.0
            for index in range(1, len(volatility_prices))
        ]
        if len(returns) < 2 or not all(math.isfinite(value) for value in returns):
            return None
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
        if not math.isfinite(variance) or variance <= 1e-16:
            return None
        annualized_volatility = math.sqrt(variance) * math.sqrt(252.0)
        if not math.isfinite(momentum) or not math.isfinite(annualized_volatility):
            return None
        if annualized_volatility <= 1e-8:
            return None
        return momentum, annualized_volatility

    def _inverse_volatility_weights(self, selected):
        inverse = {
            symbol: 1.0 / volatility
            for symbol, volatility in selected.items()
            if math.isfinite(volatility) and volatility > 1e-8
        }
        active = sorted(inverse, key=self._symbol_key)
        weights = {}
        remaining_mass = 1.0
        while active and remaining_mass > 1e-12:
            denominator = sum(inverse[symbol] for symbol in active)
            if denominator <= 0 or not math.isfinite(denominator):
                break
            proposed = {
                symbol: remaining_mass * inverse[symbol] / denominator
                for symbol in active
            }
            capped = [
                symbol
                for symbol in active
                if proposed[symbol] > self.max_weight + 1e-12
            ]
            if not capped:
                weights.update(proposed)
                remaining_mass = 0.0
                break
            for symbol in sorted(capped, key=self._symbol_key):
                weights[symbol] = self.max_weight
                remaining_mass = max(0.0, remaining_mass - self.max_weight)
                active.remove(symbol)
        return weights

    def _volatility_scaled_targets(self, weights, volatilities):
        estimate = math.sqrt(
            sum(
                (weights.get(symbol, 0.0) * volatilities[symbol]) ** 2
                for symbol in weights
            )
        )
        if not math.isfinite(estimate) or estimate <= 1e-12:
            return {}, None
        scale = min(1.0, self.target_volatility / estimate)
        return {symbol: weight * scale for symbol, weight in weights.items()}, estimate

    def _current_weights(self):
        total_value = float(self.portfolio.total_portfolio_value)
        if not math.isfinite(total_value) or total_value <= 0:
            return {symbol: 0.0 for symbol in self.rotation_symbols}
        result = {}
        for symbol in self.rotation_symbols:
            holding = self.portfolio[symbol]
            value = float(
                getattr(
                    holding,
                    "holdings_value",
                    getattr(holding, "HoldingsValue", 0.0),
                )
                or 0.0
            )
            weight = value / total_value
            result[symbol] = weight if math.isfinite(weight) else 0.0
        return result

    def _turnover_limited_targets(self, requested_targets, tradable_symbols):
        tradable = set(tradable_symbols)
        current = self._current_weights()
        frozen_gross = sum(
            max(0.0, current.get(symbol, 0.0))
            for symbol in self.rotation_symbols
            if symbol not in tradable
        )
        available_gross = max(0.0, 1.0 - frozen_gross)
        requested_gross = sum(
            max(0.0, requested_targets.get(symbol, 0.0))
            for symbol in self.rotation_symbols
            if symbol in tradable
        )
        allocation_scale = (
            min(1.0, available_gross / requested_gross)
            if requested_gross > 1e-12
            else 0.0
        )
        desired = {}
        for symbol in self.rotation_symbols:
            desired[symbol] = (
                requested_targets.get(symbol, 0.0) * allocation_scale
                if symbol in tradable
                else current.get(symbol, 0.0)
            )
        requested_turnover = 0.5 * sum(
            abs(desired[symbol] - current.get(symbol, 0.0))
            for symbol in self.rotation_symbols
        )
        if requested_turnover <= self.max_turnover + 1e-12:
            return desired, requested_turnover, requested_turnover
        scale = self.max_turnover / requested_turnover
        limited = {
            symbol: current.get(symbol, 0.0)
            + (desired[symbol] - current.get(symbol, 0.0)) * scale
            for symbol in self.rotation_symbols
        }
        applied_turnover = 0.5 * sum(
            abs(limited[symbol] - current.get(symbol, 0.0))
            for symbol in self.rotation_symbols
        )
        return limited, requested_turnover, applied_turnover

    def _submit_target(self, symbol, target):
        target = max(0.0, min(float(target), self.max_weight))
        if self.ashare_execution:
            self.ashare_execution.target_percent_moo(
                symbol,
                target,
                "etf_rotation_certified_rebalance",
            )
        else:
            self.set_holdings(symbol, target, False, "etf_rotation_certified_rebalance")

    def _execute_targets(self, targets, tradable_symbols):
        tradable = set(tradable_symbols)
        current = self._current_weights()
        reductions = []
        increases = []
        for symbol in sorted(self.rotation_symbols, key=self._symbol_key):
            if symbol not in tradable:
                continue
            target = targets.get(symbol, 0.0)
            delta = target - current.get(symbol, 0.0)
            if abs(delta) <= 1e-4:
                continue
            (reductions if delta < 0 else increases).append((symbol, target))
        for symbol, target in reductions + increases:
            self._submit_target(symbol, target)

    def _strategy_on_order_event(self, order_event):
        status = str(getattr(order_event, "status", getattr(order_event, "Status", ""))).lower()
        if "filled" in status:
            self.rotation_trade_count += 1

    def on_data(self, data):
        today = self.time.date()
        fresh_symbols = []
        for rotation_symbol in self.rotation_symbols:
            if not has_fresh_data(data, rotation_symbol):
                continue
            close = float(data[rotation_symbol].close)
            if not math.isfinite(close) or close <= 0:
                continue
            fresh_symbols.append(rotation_symbol)
            history = self.price_history[rotation_symbol]
            history.append(close)
            self.price_history[rotation_symbol] = history[-self.history_limit:]

        if not fresh_symbols:
            return
        if self._last_session_date != today:
            self._last_session_date = today
            self._sessions_since_rebalance += 1
        if self.is_warming_up or self._sessions_since_rebalance < self.rebalance_days:
            return

        ranked = []
        volatilities = {}
        for rotation_symbol in sorted(fresh_symbols, key=self._symbol_key):
            stats = self._momentum_and_volatility(rotation_symbol)
            if stats is None:
                continue
            momentum, annualized_volatility = stats
            if momentum <= 0:
                continue
            ranked.append((momentum, self._symbol_key(rotation_symbol), rotation_symbol))
            volatilities[rotation_symbol] = annualized_volatility

        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected_rows = ranked[: self.selection_count]
        selected_volatilities = {
            symbol: volatilities[symbol]
            for _, _, symbol in selected_rows
        }

        requested_targets = {}
        estimated_volatility = None
        if selected_volatilities:
            risk_weights = self._inverse_volatility_weights(selected_volatilities)
            requested_targets, estimated_volatility = self._volatility_scaled_targets(
                risk_weights,
                selected_volatilities,
            )
            self.rotation_last_failure = ""
        else:
            # Zero eligible candidates is an explicit risk-off state: move toward cash
            # subject to the one-rebalance turnover cap and market tradability.
            self.rotation_last_failure = "zero_eligible_candidates"

        limited_targets, requested_turnover, applied_turnover = self._turnover_limited_targets(
            requested_targets,
            fresh_symbols,
        )
        self._execute_targets(limited_targets, fresh_symbols)
        self.rotation_total_turnover += applied_turnover
        self._sessions_since_rebalance = 0

        best_momentum = selected_rows[0][0] if selected_rows else 0.0
        gross_exposure = sum(limited_targets.values())
        self.plot("Rotation", "BestMomentum", best_momentum)
        self.plot("Rotation", "GrossExposure", gross_exposure)
        self.plot("Rotation", "RebalanceTurnover", applied_turnover)
        if estimated_volatility is not None:
            self.plot("Rotation", "DiagonalVolEstimate", estimated_volatility)
        if requested_turnover > self.max_turnover + 1e-12:
            self.debug(
                f"ETF rotation turnover capped requested={requested_turnover:.6f} "
                f"applied={applied_turnover:.6f}"
            )
        if self.rotation_last_failure:
            self.debug(f"ETF rotation risk-off reason={self.rotation_last_failure}")

    def on_end_of_algorithm(self):
        self.debug(
            "ETF_ROTATION_SUMMARY|"
            f"estimatedTurnover={self.rotation_total_turnover:.8f}|"
            f"tradeCount={self.rotation_trade_count}|"
            f"costModelId={self.cost_model_id}"
        )
