import { test } from "@playwright/test";

import { BacktestConfigPage } from "../pages/backtest-config.page";
import { ensureE2EProject } from "../utils/api";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("04 backtest configuration validation", () => {
  test.beforeEach(async ({ request }) => {
    await ensureE2EProject(request);
  });

  test("requires project strategy, symbol, valid dates, and positive initial cash", async ({ page }) => {
    const config = new BacktestConfigPage(page);
    await config.open();

    await page.getByTestId("run-backtest-button").click();
    await config.expectValidationMessage("Project strategy is required");

    await config.fill({
      ...BACKTEST_CASES.spy,
      projectName: E2E_PROJECT.name,
      marketLabel: "US",
      feeModel: "Default",
      slippageModel: "Default"
    });

    await page.getByTestId("backtest-symbol-input").locator("input").fill("");
    await page.getByTestId("run-backtest-button").click();
    await config.expectValidationMessage("Symbol is required");

    await page.getByTestId("backtest-symbol-input").locator("input").fill(BACKTEST_CASES.spy.symbol);
    await page.getByTestId("backtest-start-input").fill("2020-12-31");
    await page.getByTestId("backtest-end-input").fill("2020-01-01");
    await page.getByTestId("run-backtest-button").click();
    await config.expectValidationMessage("End date must be on or after start date");

    await page.getByTestId("backtest-start-input").fill(BACKTEST_CASES.spy.start);
    await page.getByTestId("backtest-end-input").fill(BACKTEST_CASES.spy.end);
    await page.getByTestId("backtest-cash-input").fill("0");
    await page.getByTestId("run-backtest-button").click();
    await config.expectValidationMessage("Initial cash must be greater than 0");
  });
});
