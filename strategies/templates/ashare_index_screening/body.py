        import json
        self._json = json
        self.universe_code = self.get_parameter("universeCode", "CSI300").upper()
        self.universe_schedule = json.loads(self.get_parameter("universeSchedule", "[]"))
        self.fundamental_schedule = json.loads(self.get_parameter("fundamentalSchedule", "[]"))
        if not self.universe_schedule:
            raise ValueError("universeSchedule is required for A-share index screening.")
        if not self.fundamental_schedule:
            raise ValueError("fundamentalSchedule is required; missing fundamentals must not be treated as a buy signal.")

        self.fast_period = int(self.get_parameter("fastPeriod", 20))
        self.slow_period = int(self.get_parameter("slowPeriod", 60))
        self.rsi_period = int(self.get_parameter("rsiPeriod", 14))
        self.rebalance_days = int(self.get_parameter("rebalanceDays", 20))
        self.top_n = int(self.get_parameter("topN", 20))
        self.technical_threshold = float(self.get_parameter("technicalThreshold", 70))
        self.fundamental_threshold = float(self.get_parameter("fundamentalThreshold", 60))
        self.min_fundamental_fields = int(self.get_parameter("minFundamentalFields", 2))
        self.min_roe = float(self.get_parameter("minRoe", 8))
        self.max_debt_ratio = float(self.get_parameter("maxDebtRatio", 70))
        self.max_pe = float(self.get_parameter("maxPe", 60))
        self.max_pb = float(self.get_parameter("maxPb", 8))
        self.max_volatility = float(self.get_parameter("maxVolatility", 0.04))
        self.trend_threshold = float(self.get_parameter("trendThreshold", 0.02))
        if self.fast_period >= self.slow_period:
            raise ValueError("fastPeriod must be smaller than slowPeriod.")

        self.screening_symbols = {}
        self.price_history = {}
        market_name = self.get_parameter("market", "china").lower()
        tickers = sorted({row["symbol"] for row in self.universe_schedule})
        for ticker_value in tickers:
            if ticker_value == ticker:
                asset = security
            else:
                asset = self.add_equity(
                    ticker_value,
                    self.resolution,
                    market_name,
                    data_normalization_mode=DataNormalizationMode.RAW,
                )
                if market_name == "china" and self.ashare_execution is not None:
                    apply_ashare_models(self, asset)
            self.screening_symbols[ticker_value] = asset.symbol
            self.price_history[ticker_value] = []

        self.fundamentals = {}
        for row in sorted(self.fundamental_schedule, key=lambda value: (value["symbol"], value["effectiveDate"])):
            self.fundamentals.setdefault(row["symbol"], []).append(row)
        self.last_rebalance = None
        self.latest_screening = []
        self.latest_selected = []
        self.history_size = max(self.slow_period + 1, self.rsi_period + 1, 21)
        self.set_warm_up(self.history_size, self.resolution)

    @staticmethod
    def _percent(value):
        number = float(value)
        return number * 100.0 if abs(number) <= 1.0 else number

    def _active_tickers(self):
        today = self.time.date().isoformat()
        return {
            row["symbol"] for row in self.universe_schedule
            if row["startDate"] <= today and (not row.get("endDate") or row["endDate"] >= today)
        }

    def _fundamentals_as_of(self, ticker_value):
        today = self.time.date().isoformat()
        metrics = {}
        for row in self.fundamentals.get(ticker_value, []):
            if row["effectiveDate"] > today:
                break
            metrics.update(row.get("metrics") or {})
        return metrics

    def _rsi(self, prices):
        changes = [prices[index] - prices[index - 1] for index in range(1, len(prices))]
        changes = changes[-self.rsi_period:]
        gains = sum(max(value, 0.0) for value in changes) / self.rsi_period
        losses = sum(max(-value, 0.0) for value in changes) / self.rsi_period
        if losses == 0:
            return 100.0 if gains > 0 else 50.0
        relative_strength = gains / losses
        return 100.0 - 100.0 / (1.0 + relative_strength)

    def _technical_evaluation(self, ticker_value):
        prices = self.price_history.get(ticker_value) or []
        required = max(self.slow_period, self.rsi_period + 1, 21)
        if len(prices) < required:
            return {
                "trend": "数据不足",
                "technicalScore": 0.0,
                "close": prices[-1] if prices else None,
                "smaFast": None,
                "smaSlow": None,
                "return20": None,
                "rsi": None,
                "volatility20": None,
                "technicalReasons": [f"有效行情少于{required}日"],
            }
        close = prices[-1]
        sma_fast = sum(prices[-self.fast_period:]) / self.fast_period
        sma_slow = sum(prices[-self.slow_period:]) / self.slow_period
        return20 = close / prices[-21] - 1.0 if prices[-21] > 0 else 0.0
        rsi = self._rsi(prices)
        returns = [
            prices[index] / prices[index - 1] - 1.0
            for index in range(len(prices) - 20, len(prices))
            if prices[index - 1] > 0
        ]
        mean_return = sum(returns) / len(returns)
        volatility = (
            sum((value - mean_return) ** 2 for value in returns) / max(1, len(returns) - 1)
        ) ** 0.5
        if close > sma_fast > sma_slow and return20 >= self.trend_threshold:
            trend = "持续上涨"
        elif close < sma_fast < sma_slow and return20 <= -self.trend_threshold:
            trend = "持续下跌"
        else:
            trend = "横盘震荡"

        checks = [
            (close > sma_fast, 30.0, "收盘价高于快速均线"),
            (sma_fast > sma_slow, 25.0, "快速均线高于慢速均线"),
            (return20 > 0, 20.0, "20日收益为正"),
            (45.0 <= rsi <= 70.0, 15.0, "RSI处于45至70"),
            (volatility <= self.max_volatility, 10.0, "20日波动率受控"),
        ]
        return {
            "trend": trend,
            "technicalScore": sum(weight for passed, weight, _reason in checks if passed),
            "close": round(close, 4),
            "smaFast": round(sma_fast, 4),
            "smaSlow": round(sma_slow, 4),
            "return20": round(return20, 6),
            "rsi": round(rsi, 2),
            "volatility20": round(volatility, 6),
            "technicalReasons": [reason for passed, _weight, reason in checks if passed],
        }

    def _fundamental_evaluation(self, ticker_value):
        metrics = self._fundamentals_as_of(ticker_value)
        checks = []
        if metrics.get("roe") is not None:
            value = self._percent(metrics["roe"])
            checks.append((value >= self.min_roe, f"ROE {value:.2f}%"))
        if metrics.get("revenueGrowth") is not None:
            value = self._percent(metrics["revenueGrowth"])
            checks.append((value >= 0, f"营收增长 {value:.2f}%"))
        if metrics.get("profitGrowth") is not None:
            value = self._percent(metrics["profitGrowth"])
            checks.append((value >= 0, f"利润增长 {value:.2f}%"))
        if metrics.get("debtRatio") is not None:
            value = self._percent(metrics["debtRatio"])
            checks.append((value <= self.max_debt_ratio, f"资产负债率 {value:.2f}%"))
        if metrics.get("pe") is not None:
            value = float(metrics["pe"])
            checks.append((0 < value <= self.max_pe, f"PE {value:.2f}"))
        if metrics.get("pb") is not None:
            value = float(metrics["pb"])
            checks.append((0 < value <= self.max_pb, f"PB {value:.2f}"))
        if metrics.get("netProfit") is not None:
            value = float(metrics["netProfit"])
            checks.append((value > 0, "净利润为正"))
        score = 100.0 * sum(1 for passed, _reason in checks if passed) / len(checks) if checks else 0.0
        return {
            "fundamentalScore": round(score, 2),
            "fundamentalFieldCount": len(checks),
            "fundamentalReasons": [reason for passed, reason in checks if passed],
            "fundamentalRisks": [reason for passed, reason in checks if not passed],
            "fundamentals": metrics,
        }

    def _evaluate(self, active):
        rows = []
        for ticker_value in sorted(active):
            technical = self._technical_evaluation(ticker_value)
            fundamental = self._fundamental_evaluation(ticker_value)
            suitable = (
                technical["trend"] == "持续上涨"
                and technical["technicalScore"] >= self.technical_threshold
                and fundamental["fundamentalFieldCount"] >= self.min_fundamental_fields
                and fundamental["fundamentalScore"] >= self.fundamental_threshold
            )
            reasons = list(technical["technicalReasons"]) + list(fundamental["fundamentalReasons"])
            risks = list(fundamental["fundamentalRisks"])
            if fundamental["fundamentalFieldCount"] < self.min_fundamental_fields:
                risks.append("基本面字段覆盖不足")
            rows.append({
                "symbol": ticker_value,
                **technical,
                **fundamental,
                "overallScore": round(
                    technical["technicalScore"] * 0.6 + fundamental["fundamentalScore"] * 0.4,
                    2,
                ),
                "suitableToBuy": suitable,
                "reasons": reasons,
                "risks": risks,
            })
        return rows

    def _publish_summary(self, rows, selected):
        counts = {
            "持续上涨": sum(1 for row in rows if row["trend"] == "持续上涨"),
            "持续下跌": sum(1 for row in rows if row["trend"] == "持续下跌"),
            "横盘震荡": sum(1 for row in rows if row["trend"] == "横盘震荡"),
        }
        self.plot("Screening", "Universe", len(rows))
        self.plot("Screening", "Rising", counts["持续上涨"])
        self.plot("Screening", "Falling", counts["持续下跌"])
        self.plot("Screening", "Sideways", counts["横盘震荡"])
        self.plot("Screening", "Qualified", sum(1 for row in rows if row["suitableToBuy"]))
        self.set_runtime_statistic("指数股票池", self.universe_code)
        self.set_runtime_statistic("评估股票数", str(len(rows)))
        self.set_runtime_statistic("符合标准数", str(sum(1 for row in rows if row["suitableToBuy"])))
        self.set_runtime_statistic("当前持仓候选", ",".join(row["symbol"] for row in selected) or "无")

    def on_data(self, data):
        for ticker_value, symbol_value in self.screening_symbols.items():
            if has_fresh_data(data, symbol_value):
                prices = self.price_history[ticker_value]
                prices.append(float(data[symbol_value].close))
                self.price_history[ticker_value] = prices[-self.history_size:]
        if self.is_warming_up:
            return
        if self.last_rebalance is not None and (self.time.date() - self.last_rebalance).days < self.rebalance_days:
            return
        rows = self._evaluate(self._active_tickers())
        qualified = sorted(
            (row for row in rows if row["suitableToBuy"]),
            key=lambda row: (-row["overallScore"], row["symbol"]),
        )
        selected = qualified[:self.top_n]
        selected_symbols = {self.screening_symbols[row["symbol"]] for row in selected}
        exit_orders_submitted = False
        for symbol_value in self.screening_symbols.values():
            if self.portfolio[symbol_value].invested and symbol_value not in selected_symbols:
                ticket = (
                    self.ashare_execution.exit(symbol_value)
                    if self.ashare_execution
                    else self.liquidate(symbol_value)
                )
                exit_orders_submitted = ticket is not None or exit_orders_submitted
        if selected_symbols and not exit_orders_submitted:
            target = min(0.95 / len(selected_symbols), 0.10)
            for row in selected:
                symbol_value = self.screening_symbols[row["symbol"]]
                if has_fresh_data(data, symbol_value):
                    self.ashare_execution.target_percent(symbol_value, target) if self.ashare_execution else self.set_holdings(symbol_value, target)
        self.latest_screening = rows
        self.latest_selected = selected
        if not exit_orders_submitted:
            self.last_rebalance = self.time.date()
        self._publish_summary(rows, selected)

    def on_end_of_algorithm(self):
        rows = self._evaluate(self._active_tickers())
        qualified = sorted(
            (row for row in rows if row["suitableToBuy"]),
            key=lambda row: (-row["overallScore"], row["symbol"]),
        )
        selected = qualified[:self.top_n]
        self._publish_summary(rows, selected)
        summary = {
            "schemaVersion": 1,
            "asOfDate": self.time.date().isoformat(),
            "universeCode": self.universe_code,
            "evaluated": len(rows),
            "qualified": len(qualified),
            "selected": [row["symbol"] for row in selected],
        }
        self.debug("LEAN_SCREENING_SUMMARY|" + self._json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        for row in rows:
            self.debug("LEAN_SCREENING|" + self._json.dumps(row, ensure_ascii=False, separators=(",", ":")))
