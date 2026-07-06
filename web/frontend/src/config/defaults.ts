import type { AppSettings } from "../api";

export const defaultSettings: AppSettings = {
  defaultAssetClass: "equity",
  defaultMarket: "usa",
  defaultVenue: "usa",
  defaultResolution: "daily",
  defaultDataType: "trade",
  defaultProvider: "yahoo",
  defaultAdjust: "",
  defaultStrategyTemplate: "ema_cross",
  defaultCash: 100000,
  defaultStart: "2018-01-01",
  defaultEnd: "2024-12-31",
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
  limit: 200
};
