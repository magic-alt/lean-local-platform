import { expect, test } from "@playwright/test";

import { BacktestConfigPage } from "../pages/backtest-config.page";

const project = {
  id: "journey-project",
  name: "首次回测策略",
  display_name: "首次回测策略",
  language: "Python",
  algorithm_class: "Main",
  project_path: "/tmp/journey-project",
  main_file: "main.py",
  config: { templateKey: "sma_cross", market: "china", assetClass: "equity", venue: "china", resolution: "daily", dataType: "trade" },
  created_at: "2026-07-27T09:00:00+08:00",
  updated_at: "2026-07-27T09:00:00+08:00"
};

const run = {
  id: "journey-first-run",
  project_id: project.id,
  name: "首次回测 510300",
  symbol: "510300",
  status: "queued",
  parameters: { market: "china", start: "2025-01-01", end: "2025-12-31", cash: 300000 },
  docker_image: "quantconnect/lean:test",
  results_dir: "/tmp/journey-first-run",
  created_at: "2026-07-27T09:05:00+08:00"
};

test.describe("15 首次回测用户旅程 @smoke @responsive", () => {
  test("配置、提交并从结果返回时保留回测上下文", async ({ page }) => {
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      if (url.pathname === "/api/projects") return route.fulfill({ json: [project] });
      if (url.pathname === "/api/strategies/templates") {
        return route.fulfill({ json: [{ key: "sma_cross", name: "SMA Cross", description: "", parameters: [] }] });
      }
      if (url.pathname === "/api/asset-classes") {
        return route.fulfill({ json: [{ key: "equity", name: "Equity", defaultVenue: "china", defaultResolution: "daily", venues: ["china"], dataTypes: ["trade"], notes: "" }] });
      }
      if (url.pathname === "/api/settings") {
        return route.fulfill({
          json: {
            defaultAssetClass: "equity", defaultMarket: "china", defaultVenue: "china",
            defaultResolution: "daily", defaultDataType: "trade", defaultProvider: "tushare",
            defaultAdjust: "", defaultStrategyTemplate: "sma_cross", defaultCash: 300000,
            defaultStart: "2025-01-01", defaultEnd: "2025-12-31", dockerImage: "quantconnect/lean:test",
            researchImage: "quantconnect/research:test", chartPointLimit: 100000,
            maxConcurrentJobs: 1, maxBatchRuns: 100, jobTimeoutSeconds: 7200, logLevel: "INFO"
          }
        });
      }
      if (url.pathname === "/api/symbols") return route.fulfill({ json: { symbols: ["510300"], count: 1 } });
      if (url.pathname === "/api/securities/search") return route.fulfill({ json: { items: [], count: 0, query: "", markets: ["china"] } });
      if (url.pathname === "/api/examples") return route.fulfill({ json: { items: [], count: 0 } });
      if (url.pathname === "/api/backtests/preflight" && method === "POST") {
        return route.fulfill({ json: { ready: true, repaired: [], warnings: [], effectiveSource: "tushare" } });
      }
      if (url.pathname === "/api/backtests" && method === "POST") return route.fulfill({ status: 201, json: run });
      if (url.pathname === "/api/backtests" && method === "GET") return route.fulfill({ json: [] });
      if (url.pathname === `/api/backtests/${run.id}`) return route.fulfill({ json: run });
      if (url.pathname === `/api/backtests/${run.id}/logs`) return route.fulfill({ json: { logs: "queued" } });
      if (url.pathname === `/api/backtests/${run.id}/validation`) return route.fulfill({ json: { job_id: run.id, validation: null, experiment: null, fingerprint: null } });
      if (url.pathname === `/api/backtests/${run.id}/admission`) return route.fulfill({ json: { runId: run.id, registrationStatus: "not_applicable" } });
      return route.fulfill({ json: {} });
    });

    const config = new BacktestConfigPage(page);
    await config.open();
    await config.fill({
      projectName: project.name,
      name: run.name,
      symbol: run.symbol,
      market: "china",
      marketLabel: "A Share",
      assetClass: "Equity",
      resolution: "daily",
      dataType: "trade",
      start: "2025-01-01",
      end: "2025-12-31",
      cash: 300000,
      benchmarkSymbol: "000300",
      feeModel: "Default A-share costs",
      slippageModel: "Default",
      source: "tushare",
      sourceLabel: "TuShare Pro"
    });
    await config.runAndCaptureId();

    await expect(page.getByRole("heading", { name: run.name })).toBeVisible();
    await expect(page).toHaveURL(/returnTo=%2Fbacktests/);
    await page.getByRole("button", { name: "Backtests" }).click();
    await expect(page.getByRole("heading", { name: "Backtests" })).toBeVisible();
  });
});
