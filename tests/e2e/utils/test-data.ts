export const E2E_PREFIX = "E2E_";

export const E2E_PROJECT = {
  name: "E2E_MA_Cross_Test",
  description: "E2E test strategy for moving average crossover",
  templateKey: "sma_cross",
  fast: 20,
  slow: 50
};

export const BACKTEST_CASES = {
  spy: {
    name: "E2E_Backtest_MA_Cross_SPY_2020",
    symbol: "SPY",
    market: "usa",
    venue: "usa",
    assetClass: "equity",
    resolution: "daily",
    dataType: "trade",
    start: "2020-01-01",
    end: "2020-12-31",
    cash: 100000,
    benchmarkSymbol: "SPY",
    source: "",
    fast: 20,
    slow: 50
  },
  ashare: {
    name: "E2E_Backtest_A_SHARE_ETF_510300_2024",
    symbol: "510300",
    market: "china",
    venue: "china",
    assetClass: "equity",
    resolution: "daily",
    dataType: "trade",
    start: "2024-01-01",
    end: "2024-12-31",
    cash: 100000,
    benchmarkSymbol: "000300",
    source: "tushare",
    sourceLabel: "TuShare Pro",
    allowResearchSource: true,
    fast: 20,
    slow: 50
  },
  invalidSymbol: {
    name: "E2E_Backtest_Invalid_Symbol_Error",
    symbol: "INVALID_SYMBOL_E2E",
    market: "usa",
    venue: "usa",
    assetClass: "equity",
    resolution: "daily",
    dataType: "trade",
    start: "2020-01-01",
    end: "2020-03-01",
    cash: 100000,
    benchmarkSymbol: "SPY",
    source: "",
    fast: 20,
    slow: 50
  }
} as const;
