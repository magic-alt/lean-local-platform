import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { BacktestConfigPage } from "../pages/backtest-config.page";
import { ensureE2EProject } from "../utils/api";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("09 frontend resilience @smoke @responsive", () => {
  test("shows friendly error when backtests API returns 500", async ({ page }) => {
    await page.route("**/api/backtests**", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "E2E simulated backend failure" }) });
      } else {
        await route.continue();
      }
    });
    await page.goto("/#/backtests");
    await expect(page.getByRole("heading", { name: "Backtests" })).toBeVisible();
    await expect(page.getByText("E2E simulated backend failure").first()).toBeVisible();
    await expect(page.locator(".app-content")).not.toBeEmpty();
  });

  test("renders long running logs without white screen", async ({ page }) => {
    const run = {
      id: "e2e-resilience-run",
      name: "E2E_Resilience_Long_Log",
      symbol: "SPY",
      status: "running",
      parameters: { ticker: "SPY", market: "usa", start: "2020-01-01", end: "2020-12-31", cash: 100000 },
      docker_image: "quantconnect/lean:latest",
      results_dir: "/tmp/e2e-resilience-run",
      created_at: new Date().toISOString(),
      artifacts: []
    };
    await page.route("**/api/backtests/e2e-resilience-run", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(run) }));
    await page.route("**/api/backtests/e2e-resilience-run/logs", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ logs: Array.from({ length: 2000 }, (_, index) => `E2E log line ${index}`).join("\n") }) }));
    await page.route("**/api/backtests/e2e-resilience-run/validation", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ job_id: run.id, validation: null, experiment: null, fingerprint: null }) }));
    await page.goto("/#/runs/e2e-resilience-run");
    await expect(page.getByTestId("run-status")).toContainText("running");
    await page.getByRole("tab", { name: "Logs" }).click();
    await expect(page.getByTestId("backtest-logs")).toContainText("E2E log line 1999");
    await expect(page.locator(".app-content")).not.toBeEmpty();
  });

  test("keeps every backtest detail tab usable with malformed historical collections", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    const runId = "e2e-malformed-backtest-report";
    const run = {
      id: runId,
      name: "Malformed historical report",
      symbol: "600519",
      status: "success",
      parameters: { ticker: "600519", market: "china", start: "2026-06-01", end: "2026-07-22", cash: 100000 },
      docker_image: "quantconnect/lean:latest",
      results_dir: `/tmp/${runId}`,
      result_json_path: `/tmp/${runId}/result.json`,
      created_at: new Date().toISOString(),
      artifacts: [null, { name: "legacy-report.html" }, "report.html"],
      validation: { passed: true, severity: "ok", gates: { name: "legacy-gate", passed: true } }
    };
    const result = {
      id: "result-malformed",
      job_id: runId,
      summary_metrics: { "Net Profit": "1.00%" },
      orders: { legacy: true },
      trades: [null, "legacy", { id: 1, symbol: "600519", payload: { source: "old-parser" } }],
      holdings: "legacy",
      performance: {
        strategy_return: 0.01,
        monthly_returns: [null, "legacy", { period: "2026-07", return: 0.01 }],
        yearly_returns: [{ period: "2026", return: 0.01 }, 7],
        trade_pnl: [null, { symbol: "600519", net_pnl: 100, return: 0.01 }],
        industry_exposure: [{ industry: "Consumer", market_value: 100000, weight: 1 }, false]
      },
      created_at: new Date().toISOString()
    };
    const chart = {
      statistics: {},
      candles: null,
      indicators: [{ chart: "Price", name: "SMA", points: [null, { time: "2026-07-01", value: "10" }] }],
      series: {
        equity: [null, { time: "2026-07-01", value: 100000 }, "legacy"],
        cumulativeReturn: null,
        benchmark: null,
        price: { time: "2026-07-01", value: 10 }
      },
      orders: {}
    };

    await page.route(`**/api/backtests/${runId}`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(run) }));
    await page.route(`**/api/backtests/${runId}/logs`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ logs: "legacy run" }) }));
    await page.route(`**/api/backtests/${runId}/validation`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ job_id: runId, validation: run.validation }) }));
    await page.route(`**/api/backtests/${runId}/admission**`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ runId, registrationStatus: "not_applicable", parametersSha256: "" }) }));
    await page.route(`**/api/backtests/${runId}/chart-data`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(chart) }));
    await page.route(`**/api/backtests/${runId}/result`, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ job: run, result }) }));

    await page.goto(`/#/runs/${runId}`);
    await expect(page.getByTestId("run-status-panel")).toBeVisible();

    for (const tab of ["Trades (1)", "Research Quality", "Run Details", "Performance"]) {
      await page.getByRole("tab", { name: tab, exact: true }).click();
      await expect(page.locator(".app-content")).not.toBeEmpty();
      await expect(page.getByText("could not be displayed.")).toHaveCount(0);
    }

    await assertNoFrontendErrors();
  });

  test("prevents duplicate submit while create backtest is pending", async ({ page, request }) => {
    await ensureE2EProject(request);
    const config = new BacktestConfigPage(page);
    await config.open();
    await config.fill({
      ...BACKTEST_CASES.spy,
      name: "E2E_Duplicate_Click_Guard",
      projectName: E2E_PROJECT.name,
      assetClass: "Equity",
      marketLabel: "US",
      feeModel: "Default",
      slippageModel: "Default"
    });

    let createCount = 0;
    await page.route("**/api/backtests", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      createCount += 1;
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "e2e-duplicate-click-run",
          name: "E2E_Duplicate_Click_Guard",
          symbol: "SPY",
          status: "queued",
          parameters: { ticker: "SPY", market: "usa", start: "2020-01-01", end: "2020-12-31", cash: 100000 },
          docker_image: "quantconnect/lean:latest",
          results_dir: "/tmp/e2e-duplicate-click-run",
          created_at: new Date().toISOString()
        })
      });
    });
    await page.getByTestId("run-backtest-button").dblclick();
    await expect(page).toHaveURL(/#\/runs\/e2e-duplicate-click-run/);
    expect(createCount).toBe(1);
  });
});
