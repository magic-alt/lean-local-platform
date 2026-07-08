import { expect, test } from "@playwright/test";

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
