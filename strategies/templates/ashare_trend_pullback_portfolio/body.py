        import gzip
        import hashlib
        import json
        from pathlib import Path

        if market != "china" or self.asset_class != "equity" or self.resolution != Resolution.DAILY:
            raise ValueError("A-share trend-pullback requires China equities at daily resolution.")
        if self.ashare_execution is None:
            raise ValueError("A-share trend-pullback requires ashareRules=true.")
        input_path = Path(self.get_parameter(
            "trendPullbackInputFile", "/Lean/Run/ashare-trend-pullback-input.json.gz"
        ))
        if not input_path.exists():
            raise ValueError(f"Trend-pullback PIT input is missing: {input_path}")
        with gzip.open(input_path, "rb") as input_file:
            input_bytes = input_file.read()
        expected_hash = self.get_parameter("trendPullbackInputSha256", "")
        actual_hash = hashlib.sha256(input_bytes).hexdigest()
        if not expected_hash or actual_hash != expected_hash:
            raise ValueError("Trend-pullback PIT input hash mismatch.")
        self.tp_input = json.loads(input_bytes.decode("utf-8"))
        if int(self.tp_input.get("schemaVersion") or 0) != 1:
            raise ValueError("Unsupported trend-pullback PIT input schema.")
        if not (self.tp_input.get("coverage") or {}).get("passed"):
            raise ValueError("Trend-pullback PIT input did not pass coverage gates.")

        self.tp_json = json
        self.tp_variant = self.get_parameter("modelVariant", "B").upper()
        if self.tp_variant not in {"A", "B", "C"}:
            raise ValueError("modelVariant must be A, B or C.")
        self.tp_top_n = int(self.get_parameter("topN", 18))
        self.tp_gross = float(self.get_parameter("grossExposure", 0.90))
        self.tp_stock_cap = float(self.get_parameter("maxPositionWeight", 0.06))
        self.tp_industry_cap = float(self.get_parameter("maxIndustryWeight", 0.25))
        self.tp_turnover_cap = float(self.get_parameter("maxTurnover", 0.40))
        self.tp_min_bars = int(self.get_parameter("minListedBars", 250))
        self.tp_min_amount = float(self.get_parameter("minAmount20Cny", 50000000))
        self.tp_min_close = float(self.get_parameter("minRawClose", 2.0))
        self.tp_drawdown_min = float(self.get_parameter("drawdownMin", 0.03))
        self.tp_drawdown_max = float(self.get_parameter("drawdownMax", 0.12))
        self.tp_initial_atr = float(self.get_parameter("initialStopAtr", 2.0))
        self.tp_trailing_atr = float(self.get_parameter("trailingStopAtr", 3.0))
        self.tp_max_hold = int(self.get_parameter("maxHoldBars", 20))
        self.tp_regime_mode = self.get_parameter("marketRegimeMode", "off").lower()
        if not 0 <= self.tp_drawdown_min < self.tp_drawdown_max:
            raise ValueError("drawdownMin must be smaller than drawdownMax.")

        self.tp_universe = self.tp_input["universeSchedule"]
        self.tp_industries = {}
        for row in self.tp_input.get("industrySchedule") or []:
            self.tp_industries.setdefault(row["symbol"], []).append(row)
        self.tp_fundamentals = {}
        for row in self.tp_input.get("fundamentalSchedule") or []:
            self.tp_fundamentals.setdefault(row["symbol"], []).append(row)
        self.tp_lifecycle = {
            row["symbol"]: row for row in self.tp_input.get("securityLifecycle") or []
        }
        self.tp_liquidity = self.tp_input.get("liquidityByRebalanceDate") or {}
        self.tp_factor_events = {
            ticker_value: {row["date"]: float(row["value"]) for row in rows}
            for ticker_value, rows in (self.tp_input.get("factorChanges") or {}).items()
        }
        self.tp_factors = {ticker_value: 1.0 for ticker_value in self.tp_factor_events}
        self.tp_rebalance_dates = set(self.tp_input.get("rebalanceDates") or [])
        self.tp_symbols = {}
        self.tp_symbol_keys = {}
        self.tp_history = {}
        self.tp_positions = {}
        self.tp_pending_targets = {}
        self.tp_last_rebalance = None
        market_name = self.get_parameter("market", "china").lower()
        for ticker_value in self.tp_input["symbols"]:
            asset = security if ticker_value == ticker else self.add_equity(
                ticker_value,
                Resolution.DAILY,
                market_name,
                data_normalization_mode=DataNormalizationMode.RAW,
            )
            apply_ashare_models(self, asset)
            self.tp_symbols[ticker_value] = asset.symbol
            self.tp_symbol_keys[str(asset.symbol)] = ticker_value
            self.tp_symbol_keys[str(getattr(asset.symbol, "value", ticker_value)).upper()] = ticker_value
            self.tp_history[ticker_value] = []
        self.tp_benchmark_history = []
        self.set_warm_up(270, Resolution.DAILY)
        self.debug(
            "ASHARE_TREND_PULLBACK signal=close order=next_open "
            f"variant={self.tp_variant} snapshot={self.get_parameter('trendPullbackInputSha256', '')}"
        )

    @staticmethod
    def _tp_mean(values):
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _tp_median(values):
        ordered = sorted(values)
        if not ordered:
            return 0.0
        middle = len(ordered) // 2
        return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0

    @staticmethod
    def _tp_percent(value):
        number = float(value)
        return number * 100.0 if abs(number) <= 1.0 else number

    def _tp_active(self, as_of):
        return {
            row["symbol"] for row in self.tp_universe
            if row["startDate"] <= as_of and (not row.get("endDate") or row["endDate"] >= as_of)
        }

    def _tp_industry(self, ticker_value, as_of):
        current = None
        for row in self.tp_industries.get(ticker_value, []):
            if row["inDate"] <= as_of and (not row.get("outDate") or row["outDate"] >= as_of):
                current = row["industryCode"]
        return current

    def _tp_metrics(self, ticker_value, as_of):
        metrics = {}
        for row in self.tp_fundamentals.get(ticker_value, []):
            if row["effectiveDate"] > as_of:
                break
            metrics.update(row.get("metrics") or {})
        return metrics

    def _tp_rank(self, rows, field, reverse=False):
        valid = [row for row in rows if row.get(field) is not None]
        ordered = sorted(valid, key=lambda row: (float(row[field]), row["symbol"]), reverse=reverse)
        size = len(ordered)
        for index, row in enumerate(ordered):
            row[field + "Rank"] = (index + 1) / size
        for row in rows:
            row.setdefault(field + "Rank", 0.0)

    def _tp_atr(self, history):
        if len(history) < 15:
            return None
        ranges = []
        for index in range(len(history) - 14, len(history)):
            bar = history[index]
            previous = history[index - 1]["closeAdj"]
            ranges.append(max(
                bar["highAdj"] - bar["lowAdj"],
                abs(bar["highAdj"] - previous),
                abs(bar["lowAdj"] - previous),
            ))
        return self._tp_mean(ranges)

    def _tp_base_row(self, ticker_value, as_of):
        history = self.tp_history[ticker_value]
        if len(history) < self.tp_min_bars:
            return None, "insufficient_history"
        closes = [row["closeAdj"] for row in history]
        current = history[-1]
        if current["closeRaw"] < self.tp_min_close:
            return None, "raw_price"
        liquidity = (self.tp_liquidity.get(ticker_value) or {}).get(as_of)
        if not liquidity:
            return None, "liquidity_missing"
        if float(liquidity.get("amountMedian20Cny") or 0) < self.tp_min_amount:
            return None, "liquidity_floor"
        ma20 = self._tp_mean(closes[-20:])
        ma60 = self._tp_mean(closes[-60:])
        ma120 = self._tp_mean(closes[-120:])
        ma60_lag20 = self._tp_mean(closes[-80:-20])
        slope = ma60 / ma60_lag20 - 1.0 if ma60_lag20 > 0 else -1.0
        if not (closes[-1] > ma120 and ma20 > ma60 > ma120 and slope > 0):
            return None, "trend"
        high60 = max(row["highAdj"] for row in history[-60:])
        drawdown = closes[-1] / high60 - 1.0
        if not -self.tp_drawdown_max <= drawdown <= -self.tp_drawdown_min:
            return None, "drawdown"
        if float(liquidity.get("amountRatio5To20") or 0) >= 1.0:
            return None, "volume_contraction"
        previous_high5 = max(row["highAdj"] for row in history[-6:-1])
        if closes[-1] <= previous_high5:
            return None, "trigger"
        atr = self._tp_atr(history)
        if atr is None or atr <= 0:
            return None, "atr"
        returns20 = [closes[index] / closes[index - 1] - 1.0 for index in range(len(closes) - 19, len(closes))]
        mean20 = self._tp_mean(returns20)
        variance = sum((value - mean20) ** 2 for value in returns20) / max(1, len(returns20) - 1)
        industry = self._tp_industry(ticker_value, as_of)
        return {
            "symbol": ticker_value,
            "industry": industry or (f"UNKNOWN:{ticker_value}" if self.tp_variant == "A" else None),
            "closeRaw": current["closeRaw"],
            "closeAdj": closes[-1],
            "ma20": ma20,
            "ma60Slope20": slope,
            "drawdown60": drawdown,
            "pullbackQuality": max(0.0, 1.0 - abs(drawdown + 0.06) / 0.06),
            "volatility20": variance ** 0.5 * math.sqrt(252),
            "liquidity": float(liquidity["amountMedian20Cny"]),
            "amountRatio5To20": float(liquidity["amountRatio5To20"]),
            "atr": atr,
            "atrPct": atr / closes[-1],
            "return60": closes[-1] / closes[-61] - 1.0,
        }, None

    def _tp_quality(self, row, as_of):
        metrics = self._tp_metrics(row["symbol"], as_of)
        observed = [key for key in ("roe", "netProfit", "revenueGrowth", "profitGrowth", "operatingCashFlowToProfit") if metrics.get(key) is not None]
        revenue = metrics.get("revenueGrowth")
        profit = metrics.get("profitGrowth")
        passed = (
            len(observed) >= 3
            and metrics.get("roe") is not None and self._tp_percent(metrics["roe"]) > 0
            and metrics.get("netProfit") is not None and float(metrics["netProfit"]) > 0
            and ((revenue is not None and self._tp_percent(revenue) >= 0) or (profit is not None and self._tp_percent(profit) >= 0))
        )
        cash_ratio = metrics.get("operatingCashFlowToProfit")
        if cash_ratio is not None:
            cash_ratio = float(cash_ratio)
        row["qualityObserved"] = len(observed)
        row["qualityRaw"] = (
            max(-1.0, min(1.0, self._tp_percent(metrics.get("roe") or 0) / 30.0))
            + max(-1.0, min(1.0, self._tp_percent(revenue or 0) / 50.0))
            + max(-1.0, min(1.0, self._tp_percent(profit or 0) / 50.0))
            + max(-1.0, min(1.0, cash_ratio or 0.0))
        ) / 4.0
        row["qualityRisk"] = cash_ratio is not None and cash_ratio <= 0
        return passed

    def _tp_market_exposure(self):
        if self.tp_regime_mode != "tiered" or len(self.tp_benchmark_history) < 120:
            return self.tp_gross
        closes = self.tp_benchmark_history
        conditions = int(closes[-1] > self._tp_mean(closes[-120:])) + int(
            self._tp_mean(closes[-20:]) > self._tp_mean(closes[-60:])
        )
        return min(self.tp_gross, 0.90 if conditions == 2 else 0.60 if conditions == 1 else 0.20)

    def _tp_targets(self, rows):
        selected = sorted(rows, key=lambda row: (-row["score"], row["symbol"]))[:self.tp_top_n]
        gross = self._tp_market_exposure()
        raw = {row["symbol"]: row["score"] / max(row["atrPct"], 0.01) for row in selected}
        weights = {symbol: 0.0 for symbol in raw}
        industries = {row["symbol"]: row["industry"] for row in selected}
        remaining = gross
        for _iteration in range(100):
            eligible = [symbol for symbol in raw if weights[symbol] < self.tp_stock_cap - 1e-9]
            if not eligible or remaining <= 1e-9:
                break
            total_raw = sum(raw[symbol] for symbol in eligible)
            allocated = 0.0
            for symbol in eligible:
                industry = industries[symbol]
                industry_used = sum(weights[item] for item in weights if industries[item] == industry)
                room = min(self.tp_stock_cap - weights[symbol], self.tp_industry_cap - industry_used)
                addition = min(room, remaining * raw[symbol] / total_raw) if total_raw > 0 else 0.0
                if addition > 0:
                    weights[symbol] += addition
                    allocated += addition
            if allocated <= 1e-10:
                break
            remaining -= allocated
        current = {}
        total_value = float(self.portfolio.total_portfolio_value)
        for ticker_value, symbol_value in self.tp_symbols.items():
            if self.portfolio[symbol_value].invested and total_value > 0:
                current[ticker_value] = float(self.portfolio[symbol_value].holdings_value) / total_value
        turnover = 0.5 * sum(abs(weights.get(symbol, 0.0) - current.get(symbol, 0.0)) for symbol in set(weights) | set(current))
        if turnover > self.tp_turnover_cap > 0:
            scale = self.tp_turnover_cap / turnover
            weights = {
                symbol: max(0.0, current.get(symbol, 0.0) + (weights.get(symbol, 0.0) - current.get(symbol, 0.0)) * scale)
                for symbol in set(weights) | set(current)
            }
        return selected, weights, turnover, gross

    def _tp_evaluate(self, as_of):
        active = self._tp_active(as_of)
        peer_returns = {}
        market_returns = []
        for ticker_value in sorted(active):
            history = self.tp_history.get(ticker_value) or []
            industry = self._tp_industry(ticker_value, as_of)
            if len(history) < 61 or not industry:
                continue
            closes = [item["closeAdj"] for item in history]
            return60 = closes[-1] / closes[-61] - 1.0
            peer_returns.setdefault(industry, []).append(return60)
            market_returns.append(return60)
        industry_returns = {
            industry: self._tp_median(values) for industry, values in peer_returns.items()
        }
        rows = []
        rejected = {}
        for ticker_value in sorted(active):
            row, reason = self._tp_base_row(ticker_value, as_of)
            if row is None:
                rejected[reason] = rejected.get(reason, 0) + 1
                continue
            if self.tp_variant in {"B", "C"} and not row["industry"]:
                rejected["industry_missing"] = rejected.get("industry_missing", 0) + 1
                continue
            rows.append(row)
        benchmark_return = None
        if len(self.tp_benchmark_history) >= 61:
            benchmark_return = self.tp_benchmark_history[-1] / self.tp_benchmark_history[-61] - 1.0
        for row in rows:
            row["benchmarkRs60"] = row["return60"] - benchmark_return if benchmark_return is not None else None
            row["industryRs60"] = row["return60"] - industry_returns.get(row["industry"], row["return60"])
            row["benchmarkRs60Rank"] = (
                sum(1 for value in market_returns if value <= row["return60"]) / len(market_returns)
                if market_returns else 0.0
            )
        if self.tp_variant in {"B", "C"}:
            filtered = []
            for row in rows:
                if row["benchmarkRs60"] is None or row["benchmarkRs60"] <= 0 or row["industryRs60"] <= 0 or row["benchmarkRs60Rank"] < 0.70:
                    rejected["relative_strength"] = rejected.get("relative_strength", 0) + 1
                elif self.tp_variant == "C" and not self._tp_quality(row, as_of):
                    rejected["quality"] = rejected.get("quality", 0) + 1
                else:
                    filtered.append(row)
            rows = filtered
        self._tp_rank(rows, "ma60Slope20")
        self._tp_rank(rows, "pullbackQuality")
        self._tp_rank(rows, "volatility20", reverse=True)
        self._tp_rank(rows, "liquidity")
        if self.tp_variant == "C":
            self._tp_rank(rows, "qualityRaw")
        for row in rows:
            if self.tp_variant == "A":
                row["score"] = 0.35 * row["ma60Slope20Rank"] + 0.30 * row["pullbackQualityRank"] + 0.20 * row["volatility20Rank"] + 0.15 * row["liquidityRank"]
            elif self.tp_variant == "B":
                row["score"] = 0.30 * row["benchmarkRs60Rank"] + 0.25 * row["ma60Slope20Rank"] + 0.20 * row["pullbackQualityRank"] + 0.15 * row["volatility20Rank"] + 0.10 * row["liquidityRank"]
            else:
                row["score"] = 0.25 * row["benchmarkRs60Rank"] + 0.20 * row["qualityRawRank"] + 0.20 * row["ma60Slope20Rank"] + 0.15 * row["pullbackQualityRank"] + 0.10 * row["volatility20Rank"] + 0.10 * row["liquidityRank"]
        return rows, rejected

    def _tp_tag(self, ticker_value, as_of, reason, row=None, target=None):
        payload = {
            "signalDate": as_of,
            "modelVariant": self.tp_variant,
            "reason": reason,
            "targetPercent": target,
            "score": None if row is None else round(row.get("score", 0), 8),
            "snapshotSha256": self.get_parameter("trendPullbackInputSha256", ""),
        }
        return "ASHARE_TREND|" + self.tp_json.dumps(payload, separators=(",", ":"))

    def _tp_apply_pending(self, as_of):
        if not self.tp_pending_targets:
            return
        for ticker_value, symbol_value in self.tp_symbols.items():
            target = float(self.tp_pending_targets.get(ticker_value, 0.0))
            current = float(self.portfolio[symbol_value].holdings_value) / max(1.0, float(self.portfolio.total_portfolio_value))
            if target < current - 1e-6:
                self.ashare_execution.target_percent_moo(symbol_value, target, self._tp_tag(ticker_value, as_of, "rebalance_reduce", target=target))
        for ticker_value, target in sorted(self.tp_pending_targets.items(), key=lambda item: item[0]):
            symbol_value = self.tp_symbols[ticker_value]
            current = float(self.portfolio[symbol_value].holdings_value) / max(1.0, float(self.portfolio.total_portfolio_value))
            if target > current + 1e-6:
                self.ashare_execution.target_percent_moo(symbol_value, target, self._tp_tag(ticker_value, as_of, "rebalance_buy", target=target))

    def _tp_check_exits(self, as_of):
        active = self._tp_active(as_of)
        for ticker_value, symbol_value in self.tp_symbols.items():
            if not self.portfolio[symbol_value].invested:
                continue
            history = self.tp_history[ticker_value]
            if not history:
                continue
            state = self.tp_positions.get(ticker_value)
            if state is None:
                factor = self.tp_factors.get(ticker_value, 1.0)
                state = {"entryDate": as_of, "entryAdj": float(self.portfolio[symbol_value].average_price) * factor, "highestAdj": history[-1]["closeAdj"], "entryAtr": self._tp_atr(history) or 0}
                self.tp_positions[ticker_value] = state
            state["highestAdj"] = max(state["highestAdj"], history[-1]["closeAdj"])
            atr = self._tp_atr(history) or state["entryAtr"]
            ma20 = self._tp_mean([row["closeAdj"] for row in history[-20:]])
            held_bars = sum(1 for row in history if row["date"] >= state["entryDate"])
            initial_stop = state["entryAdj"] - self.tp_initial_atr * state["entryAtr"]
            trailing_stop = state["highestAdj"] - self.tp_trailing_atr * atr
            close = history[-1]["closeAdj"]
            reason = None
            if ticker_value not in active:
                reason = "universe_exit"
            elif close <= initial_stop:
                reason = "initial_stop"
            elif close <= trailing_stop:
                reason = "trailing_stop"
            elif close < ma20:
                reason = "ma20_exit"
            elif held_bars >= self.tp_max_hold:
                reason = "max_hold"
            if reason:
                self.tp_pending_targets[ticker_value] = 0.0
                self.ashare_execution.exit_moo(symbol_value, self._tp_tag(ticker_value, as_of, reason))

    def on_data(self, data):
        as_of = self.time.date().isoformat()
        for ticker_value, symbol_value in self.tp_symbols.items():
            if as_of in self.tp_factor_events.get(ticker_value, {}):
                self.tp_factors[ticker_value] = self.tp_factor_events[ticker_value][as_of]
            if not has_fresh_data(data, symbol_value):
                continue
            bar = data[symbol_value]
            factor = self.tp_factors.get(ticker_value, 1.0)
            history = self.tp_history[ticker_value]
            history.append({
                "date": as_of,
                "openAdj": float(bar.open) * factor,
                "highAdj": float(bar.high) * factor,
                "lowAdj": float(bar.low) * factor,
                "closeAdj": float(bar.close) * factor,
                "closeRaw": float(bar.close),
            })
            self.tp_history[ticker_value] = history[-320:]
        benchmark_symbol = self.benchmark_security.symbol
        if has_fresh_data(data, benchmark_symbol):
            self.tp_benchmark_history.append(float(data[benchmark_symbol].close))
            self.tp_benchmark_history = self.tp_benchmark_history[-320:]
        if self.is_warming_up:
            return
        self._tp_check_exits(as_of)
        if as_of in self.tp_rebalance_dates and self.tp_last_rebalance != as_of:
            rows, rejected = self._tp_evaluate(as_of)
            selected, targets, turnover, gross = self._tp_targets(rows)
            self.tp_pending_targets = {ticker_value: targets.get(ticker_value, 0.0) for ticker_value in set(targets) | {key for key, symbol_value in self.tp_symbols.items() if self.portfolio[symbol_value].invested}}
            selected_by_symbol = {row["symbol"]: row for row in selected}
            for ticker_value, target in targets.items():
                row = selected_by_symbol.get(ticker_value)
                self.debug("LEAN_TREND_PULLBACK|" + self.tp_json.dumps({
                    "date": as_of,
                    "symbol": ticker_value,
                    "industry": row["industry"],
                    "variant": self.tp_variant,
                    "score": round(row["score"], 8),
                    "targetWeight": round(target, 8),
                    "close": round(row["closeRaw"], 4),
                    "entryReference": round(row["closeRaw"], 4),
                    "initialStopAdjusted": round(row["closeAdj"] - self.tp_initial_atr * row["atr"], 4),
                    "atrPct": round(row["atrPct"], 8),
                    "drawdown60": round(row["drawdown60"], 8),
                    "benchmarkRs60": row.get("benchmarkRs60"),
                    "industryRs60": row.get("industryRs60"),
                    "amountMedian20Cny": row["liquidity"],
                    "qualityRisk": row.get("qualityRisk", False),
                }, ensure_ascii=False, separators=(",", ":")))
            self.debug("LEAN_TREND_PULLBACK_SUMMARY|" + self.tp_json.dumps({
                "schemaVersion": 1,
                "date": as_of,
                "universeCode": self.tp_input["universeCode"],
                "variant": self.tp_variant,
                "selected": [row["symbol"] for row in selected],
                "targetGross": gross,
                "estimatedTurnover": turnover,
                "rejected": rejected,
            }, ensure_ascii=False, separators=(",", ":")))
            self.tp_last_rebalance = as_of
        self._tp_apply_pending(as_of)

    def _strategy_on_order_event(self, order_event):
        status = str(getattr(order_event, "status", getattr(order_event, "Status", ""))).lower()
        if "filled" not in status:
            return
        quantity = float(getattr(order_event, "fill_quantity", getattr(order_event, "FillQuantity", 0)) or 0)
        symbol_value = getattr(order_event, "symbol", getattr(order_event, "Symbol", None))
        ticker_value = self.tp_symbol_keys.get(str(getattr(symbol_value, "value", symbol_value)).upper())
        if not ticker_value:
            return
        if quantity > 0:
            factor = self.tp_factors.get(ticker_value, 1.0)
            fill_price = float(getattr(order_event, "fill_price", getattr(order_event, "FillPrice", 0)) or 0)
            history = self.tp_history[ticker_value]
            self.tp_positions[ticker_value] = {
                "entryDate": self.time.date().isoformat(),
                "entryAdj": fill_price * factor,
                "highestAdj": history[-1]["closeAdj"] if history else fill_price * factor,
                "entryAtr": self._tp_atr(history) or 0.0,
            }
        elif not self.portfolio[self.tp_symbols[ticker_value]].invested:
            self.tp_positions.pop(ticker_value, None)
