import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { BacktestConfigPage } from "../pages/backtest-config.page";
import { BacktestResultPage } from "../pages/backtest-result.page";
import { HistoryPage } from "../pages/history.page";
import { ensureE2EProject } from "../utils/api";
import { waitForBacktestTerminal } from "../utils/backtest-waiter";
import { appendCaseResult } from "../utils/report-writer";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("07 invalid symbol error handling @backtest", () => {
  test("keeps failed invalid-symbol run visible and recoverable", async ({ page, request }, testInfo) => {
    test.setTimeout(10 * 60_000);
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await ensureE2EProject(request);

    const config = new BacktestConfigPage(page);
    await config.open();
    await config.fill({
      ...BACKTEST_CASES.invalidSymbol,
      projectName: E2E_PROJECT.name,
      assetClass: "Equity",
      marketLabel: "US",
      feeModel: "Default",
      slippageModel: "Default"
    });
    const runId = await config.runAndCaptureId();
    const waitResult = await waitForBacktestTerminal(request, runId, { timeoutMs: 2 * 60_000 });
    expect(waitResult.final.status).toBe("failed");
    expect(waitResult.final.error_message || waitResult.final.error).toMatch(/missing|data|symbol|INVALID_SYMBOL_E2E/i);

    const resultPage = new BacktestResultPage(page);
    await resultPage.open(runId);
    await resultPage.expectFailed();
    await expect(page.locator(".app-content")).not.toBeEmpty();
    await expect(page.getByText(/missing|data|symbol|INVALID_SYMBOL_E2E/i).first()).toBeVisible();
    await resultPage.expectLogs(/preflight failed|missing|INVALID_SYMBOL_E2E/i);
    await page.screenshot({ path: `../../tests/e2e/reports/artifacts/${BACKTEST_CASES.invalidSymbol.name}.png`, fullPage: true });

    const history = new HistoryPage(page);
    await history.open();
    await history.filterByName(BACKTEST_CASES.invalidSymbol.name);
    await history.expectRun(BACKTEST_CASES.invalidSymbol.name);
    await history.filterByStatus("failed");
    await history.expectRun(BACKTEST_CASES.invalidSymbol.name);
    await assertNoFrontendErrors();

    appendCaseResult({
      id: "Case C",
      name: "Invalid symbol error handling",
      status: "Pass",
      details: {
        runId,
        status: waitResult.final.status,
        error: waitResult.final.error_message || waitResult.final.error,
        enteredHistory: true,
        blankScreen: false
      }
    });
  });
});
