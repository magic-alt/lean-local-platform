        import json
        import statistics

        if market != "china" or self.asset_class != "equity":
            raise ValueError("Gap source replica requires China equities.")
        if self.resolution != Resolution.DAILY:
            raise ValueError("Gap source replica requires daily resolution.")

        self.gap_sigma_lookback = int(self.get_parameter("sigmaLookback", 90))
        self.gap_ma_lookback = int(self.get_parameter("maLookback", 20))
        self.gap_sigma_multiple = float(self.get_parameter("gapSigma", 1.0))
        self.gap_top_n = int(self.get_parameter("topN", 10))
        self.gap_synthetic_equity = 1.0
        self.gap_universe_schedule = json.loads(self.get_parameter("universeSchedule", "[]"))
        if not self.gap_universe_schedule:
            raise ValueError(
                "universeSchedule is required; use the PIT A_SHARE_L3P_50 universe."
            )

        self.gap_symbols = {}
        self.gap_states = {}
        scheduled_tickers = sorted({str(row["symbol"]).upper() for row in self.gap_universe_schedule})
        for ticker_value in scheduled_tickers:
            asset = security if ticker_value == ticker else self.add_equity(
                ticker_value,
                Resolution.DAILY,
                "china",
                data_normalization_mode=DataNormalizationMode.ADJUSTED,
            )
            try:
                asset.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            except AttributeError:
                asset.SetDataNormalizationMode(DataNormalizationMode.ADJUSTED)
            self.gap_symbols[ticker_value] = asset.symbol
            self.gap_states[asset.symbol] = {"closes": [], "returns": [], "prev_low": None}

        self.debug(
            "GAP_SOURCE_REPLICA research_only=true tradable=false "
            "admission_eligible=false fill_assumption=official_open"
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

    def _gap_update_state(self, state, bar):
        close = float(bar.close)
        if state["closes"] and state["closes"][-1] > 0:
            state["returns"].append(close / state["closes"][-1] - 1.0)
            state["returns"] = state["returns"][-self.gap_sigma_lookback:]
        state["closes"].append(close)
        state["closes"] = state["closes"][-max(self.gap_sigma_lookback + 1, self.gap_ma_lookback):]
        state["prev_low"] = float(bar.low)

    def on_data(self, data):
        import json
        import statistics

        active = self._gap_active_tickers()
        candidates = []
        observed = []
        for ticker_value, symbol_value in self.gap_symbols.items():
            if not has_fresh_data(data, symbol_value):
                continue
            bar = data[symbol_value]
            state = self.gap_states[symbol_value]
            observed.append((state, bar))
            if ticker_value not in active or not self._gap_state_ready(state):
                continue

            official_open = float(bar.open)
            prev_low = float(state["prev_low"])
            if official_open <= 0 or prev_low <= 0:
                continue
            sigma = statistics.stdev(state["returns"][-self.gap_sigma_lookback:])
            ma = statistics.mean(state["closes"][-self.gap_ma_lookback:])
            trigger = prev_low * (1.0 - self.gap_sigma_multiple * sigma)
            gap_return = official_open / prev_low - 1.0
            if official_open < trigger and official_open > ma:
                candidates.append(
                    {
                        "symbol": ticker_value,
                        "gap_return": gap_return,
                        "trigger_price": trigger,
                        "official_open": official_open,
                        "ma": ma,
                        "sigma": sigma,
                        "day_return": float(bar.close) / official_open - 1.0,
                    }
                )

        candidates.sort(key=lambda item: item["gap_return"])
        selected = candidates[:self.gap_top_n]
        daily_return = (
            sum(item["day_return"] for item in selected) / len(selected)
            if selected
            else 0.0
        )
        self.gap_synthetic_equity *= 1.0 + daily_return
        if selected:
            self.debug(
                "GAP_SOURCE_SIGNAL "
                + json.dumps(
                    {
                        "trade_date": self.time.date().isoformat(),
                        "fill_assumption": "official_open",
                        "exit_assumption": "same_day_close",
                        "daily_return": daily_return,
                        "synthetic_equity": self.gap_synthetic_equity,
                        "candidates": selected,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        self.plot("Gap Source Replica", "Synthetic Equity", self.gap_synthetic_equity)

        # State mutation is deliberately last: today's values cannot enter
        # today's sigma, moving average, or previous-low signal inputs.
        for state, bar in observed:
            self._gap_update_state(state, bar)
