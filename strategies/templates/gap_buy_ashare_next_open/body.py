        import json

        if market != "china" or self.asset_class != "equity":
            raise ValueError("Executable gap strategy requires China equities.")
        if self.resolution != Resolution.MINUTE:
            raise ValueError("Executable gap strategy requires minute resolution.")
        if self.ashare_execution is None:
            raise ValueError("Executable gap strategy requires ashareRules=true.")

        self.gap_sigma_lookback = int(self.get_parameter("sigmaLookback", 90))
        self.gap_ma_lookback = int(self.get_parameter("maLookback", 20))
        self.gap_sigma_multiple = float(self.get_parameter("gapSigma", 1.0))
        self.gap_top_n = int(self.get_parameter("topN", 10))
        self.gap_max_chase_bps = float(self.get_parameter("maxChaseBps", 15.0))
        self.gap_gross_exposure = float(self.get_parameter("grossExposure", 0.80))
        self.gap_max_participation = float(self.get_parameter("maxParticipation", 0.05))
        self.gap_tick_size = float(self.get_parameter("tickSize", 0.01))
        self.gap_universe_schedule = json.loads(self.get_parameter("universeSchedule", "[]"))
        if not self.gap_universe_schedule:
            raise ValueError(
                "universeSchedule is required; use the PIT A_SHARE_L3P_50 universe."
            )

        self.gap_symbols = {}
        self.gap_states = {}
        self.gap_pending_selection = []
        self.gap_selection_date = None
        scheduled_tickers = sorted({str(row["symbol"]).upper() for row in self.gap_universe_schedule})
        for ticker_value in scheduled_tickers:
            asset = security if ticker_value == ticker else self.add_equity(
                ticker_value,
                Resolution.MINUTE,
                "china",
                data_normalization_mode=DataNormalizationMode.ADJUSTED,
            )
            try:
                asset.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            except AttributeError:
                asset.SetDataNormalizationMode(DataNormalizationMode.ADJUSTED)
            apply_ashare_models(self, asset)
            self.gap_symbols[ticker_value] = asset.symbol
            self.gap_states[asset.symbol] = {"closes": [], "returns": [], "prev_low": None}
            self.consolidate(
                asset.symbol,
                Resolution.DAILY,
                lambda bar, selected_symbol=asset.symbol: self._gap_on_daily_bar(
                    selected_symbol, bar
                ),
            )

        self.debug(
            "GAP_A_SHARE_EXECUTABLE signal=first_minute "
            "order=next_minute_limit exit=next_trade_date"
        )

    def _gap_active_tickers(self):
        today = self.time.date().isoformat()
        return {
            str(row["symbol"]).upper()
            for row in self.gap_universe_schedule
            if row["startDate"] <= today
            and (not row.get("endDate") or row["endDate"] >= today)
        }

    def _gap_state_ready(self, state):
        return (
            len(state["returns"]) >= self.gap_sigma_lookback
            and len(state["closes"]) >= self.gap_ma_lookback
            and state["prev_low"] is not None
        )

    def _gap_on_daily_bar(self, symbol_value, bar):
        state = self.gap_states[symbol_value]
        close = float(bar.close)
        if state["closes"] and state["closes"][-1] > 0:
            state["returns"].append(close / state["closes"][-1] - 1.0)
            state["returns"] = state["returns"][-self.gap_sigma_lookback:]
        state["closes"].append(close)
        state["closes"] = state["closes"][-max(self.gap_sigma_lookback + 1, self.gap_ma_lookback):]
        state["prev_low"] = float(bar.low)

    def _gap_floor_to_tick(self, price):
        return math.floor(float(price) / self.gap_tick_size + 1e-12) * self.gap_tick_size

    def _gap_select(self, data):
        import statistics

        active = self._gap_active_tickers()
        candidates = []
        for ticker_value, symbol_value in self.gap_symbols.items():
            if ticker_value not in active or not has_fresh_data(data, symbol_value):
                continue
            state = self.gap_states[symbol_value]
            if not self._gap_state_ready(state):
                continue
            can_buy, reason = self.ashare_execution.can_buy(symbol_value)
            if not can_buy:
                self.debug(f"GAP_REJECT {ticker_value} {reason}")
                continue
            status = self.ashare_execution.trade_status(symbol_value)
            if status.get("is_one_word_limit_down"):
                self.debug(f"GAP_REJECT {ticker_value} one_word_limit_down")
                continue

            first_bar = data[symbol_value]
            observed_open = float(first_bar.open)
            prev_low = float(state["prev_low"])
            if observed_open <= 0 or prev_low <= 0:
                continue
            sigma = statistics.stdev(state["returns"][-self.gap_sigma_lookback:])
            ma = statistics.mean(state["closes"][-self.gap_ma_lookback:])
            trigger = prev_low * (1.0 - self.gap_sigma_multiple * sigma)
            gap_return = observed_open / prev_low - 1.0
            if observed_open >= trigger or observed_open <= ma:
                continue

            chase_cap = observed_open * (1.0 + self.gap_max_chase_bps / 10000.0)
            limit_price = self._gap_floor_to_tick(min(trigger, chase_cap))
            if limit_price <= 0:
                continue
            candidates.append(
                {
                    "ticker": ticker_value,
                    "symbol": symbol_value,
                    "gap_return": gap_return,
                    "trigger_price": trigger,
                    "official_open": observed_open,
                    "first_minute_volume": float(first_bar.volume),
                    "limit_price": limit_price,
                    "sigma": sigma,
                    "ma": ma,
                }
            )
        candidates.sort(key=lambda item: item["gap_return"])
        return candidates[:self.gap_top_n]

    def _gap_exit_old_positions(self):
        for symbol_value in self.gap_symbols.values():
            if not self.portfolio[symbol_value].invested:
                continue
            can_sell, reason = self.ashare_execution.can_sell(symbol_value)
            if not can_sell:
                symbol_key = getattr(
                    symbol_value,
                    "value",
                    getattr(symbol_value, "Value", str(symbol_value)),
                )
                self.debug(f"GAP_EXIT_DEFER {symbol_key} {reason}")
                continue
            self.ashare_execution.exit(symbol_value)

    def _gap_submit_pending(self):
        import json

        self._gap_exit_old_positions()
        selected = self.gap_pending_selection
        self.gap_pending_selection = []
        if not selected:
            return

        invested_value = sum(
            abs(float(self.portfolio[item].holdings_value))
            for item in self.gap_symbols.values()
            if self.portfolio[item].invested
        )
        total_value = float(self.portfolio.total_portfolio_value)
        deployable = max(0.0, total_value * self.gap_gross_exposure - invested_value)
        per_position_cash = deployable / len(selected) if selected else 0.0
        for item in selected:
            symbol_value = item["symbol"]
            if self.portfolio[symbol_value].invested:
                continue
            capital_quantity = math.floor(
                per_position_cash / item["limit_price"] / self.ashare_execution.lot_size
            ) * self.ashare_execution.lot_size
            liquidity_quantity = math.floor(
                item["first_minute_volume"]
                * self.gap_max_participation
                / self.ashare_execution.lot_size
            ) * self.ashare_execution.lot_size
            quantity = min(capital_quantity, liquidity_quantity)
            if quantity <= 0:
                self.debug(f"GAP_REJECT {item['ticker']} quantity_zero")
                continue
            tag = (
                "GAP_BUY;"
                f"gap={item['gap_return']:.6f};"
                f"trigger={item['trigger_price']:.4f};"
                f"official_open={item['official_open']:.4f};"
                f"signal_time={self.time.date().isoformat()}T09:31:00+08:00"
            )
            ticket = self.ashare_execution.limit_buy(
                symbol_value,
                quantity,
                item["limit_price"],
                tag=tag,
            )
            decision = "ordered" if ticket is not None else "rejected"
            self.debug(
                "GAP_EXECUTION_DECISION "
                + json.dumps(
                    {
                        "trade_date": self.time.date().isoformat(),
                        "instrument_id": item["ticker"],
                        "signal_time": "09:31:00",
                        "order_time": "09:32:00",
                        "prev_low": self.gap_states[symbol_value]["prev_low"],
                        "sigma90": item["sigma"],
                        "ma20": item["ma"],
                        "trigger_price": item["trigger_price"],
                        "official_open": item["official_open"],
                        "gap_return": item["gap_return"],
                        "limit_price": item["limit_price"],
                        "target_quantity": quantity,
                        "decision": decision,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

    def on_data(self, data):
        today = self.time.date()
        if self.time.hour == 9 and self.time.minute == 31:
            if self.gap_selection_date == today:
                return
            self.gap_selection_date = today
            self.gap_pending_selection = self._gap_select(data)
            return
        if self.time.hour == 9 and self.time.minute == 32:
            self._gap_submit_pending()
