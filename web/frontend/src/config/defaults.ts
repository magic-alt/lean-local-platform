import type { AppSettings } from "../api";

export const defaultSettings: AppSettings = {
  defaultAssetClass: "equity",
  defaultMarket: "china",
  defaultVenue: "china",
  defaultResolution: "daily",
  defaultDataType: "trade",
  defaultProvider: "tushare",
  defaultAdjust: "",
  defaultStrategyTemplate: "ema_cross",
  defaultCash: 300000,
  defaultStart: "2024-01-01",
  defaultEnd: "2026-07-13",
  dockerImage: "quantconnect/lean:latest",
  researchImage: "quantconnect/research:latest",
  chartPointLimit: 1000000,
  maxConcurrentJobs: 1,
  jobTimeoutSeconds: 7200,
  logLevel: "INFO"
};

export const defaultBarPreviewValues = {
  source: "database",
  assetClass: "equity",
  symbol: "000001",
  market: "china",
  venue: "china",
  resolution: "daily",
  dataType: "trade",
  providerSource: "tushare",
  providerMode: "strict",
  adjust: "raw",
  startDate: "2024-01-01",
  endDate: "2026-07-13",
  limit: 200
};
