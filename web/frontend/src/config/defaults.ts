import type { AppSettings } from "../api";
import dayjs from "dayjs";

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
  defaultEnd: dayjs().format("YYYY-MM-DD"),
  dockerImage: "quantconnect/lean@sha256:19e3633d2da1e8b378dd6af4b999b0ca6cf0660a1bf557a0518a2e43fc270823",
  researchImage: "quantconnect/research@sha256:1548cafe8d696c1a30774413fc6f7c0d7f0205104f2f78110d9a84906ac65634",
  chartPointLimit: 1000000,
  maxConcurrentJobs: 1,
  maxBatchRuns: 5000,
  jobTimeoutSeconds: 7200,
  logLevel: "INFO",
  deploymentMode: "docker",
  deploymentProfile: "full",
  executionBackend: "docker"
};

export const defaultBarPreviewValues = {
  source: "parquet",
  assetClass: "equity",
  symbol: "000001",
  market: "china",
  venue: "china",
  resolution: "daily",
  dataType: "trade",
  providerSource: "tushare",
  providerMode: "strict",
  adjust: "raw",
  startDate: "1990-01-01",
  endDate: dayjs().format("YYYY-MM-DD"),
  limit: 0
};
