import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { BacktestConfigPage } from "../pages/backtest-config.page";
import { BacktestResultPage } from "../pages/backtest-result.page";
import { HistoryPage } from "../pages/history.page";
import { apiGet, BacktestResultPayload, ensureE2EProject } from "../utils/api";
import { isSuccessfulStatus, waitForBacktestTerminal } from "../utils/backtest-waiter";
import { appendCaseResult } from "../utils/report-writer";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("05 real SPY SMA cross backtest @backtest", () => {
  test("runs E2E_Backtest_MA_Cross_SPY_2020 through the Web and displays results", async ({ page, request }, testInfo) => {
    test.setTimeout(20 * 60_000);
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await ensureE2EProject(request);

    const config = new BacktestConfigPage(page);
    await config.open();
    const createRequest = page.waitForRequest((item) => new URL(item.url()).pathname === "/api/backtests" && item.method() === "POST");
    await config.fill({
      ...BACKTEST_CASES.spy,
      projectName: E2E_PROJECT.name,
      assetClass: "Equity",
      marketLabel: "US",
      feeModel: "Default",
      slippageModel: "Default"
    });
    const runId = await config.runAndCaptureId();
    const payload = createRequest.then((item) => item.postDataJSON() as Record<string, unknown>);
    expect(await payload).toMatchObject({
      name: BACKTEST_CASES.spy.name,
      symbol: BACKTEST_CASES.spy.symbol,
      market: BACKTEST_CASES.spy.market,
      resolution: BACKTEST_CASES.spy.resolution,
      cash: BACKTEST_CASES.spy.cash
    });

    const waitResult = await waitForBacktestTerminal(request, runId, { requireRunningState: true });
    expect(isSuccessfulStatus(waitResult.final.status), waitResult.statuses.join(" -> ")).toBeTruthy();

    const result = await apiGet<BacktestResultPayload>(request, `/api/backtests/${runId}/result`);
    expect(result.result.equity_curve.length).toBeGreaterThan(0);
    expect(result.result.drawdown_curve.length).toBeGreaterThan(0);
    expect(result.job.result_json_path).toBeTruthy();
    expect(result.job.parameters).toMatchObject({
      ticker: BACKTEST_CASES.spy.symbol,
      market: BACKTEST_CASES.spy.market,
      start: BACKTEST_CASES.spy.start,
      end: BACKTEST_CASES.spy.end,
      cash: BACKTEST_CASES.spy.cash
    });

    const resultPage = new BacktestResultPage(page);
    await resultPage.open(runId);
    await resultPage.expectCompleted();
    await resultPage.expectCoreMetrics();
    await resultPage.expectCharts();
    await resultPage.expectRecordsPanel();
    await resultPage.expectLogs(/LEAN|Docker|Backtest|Engine/i);
    await expect(page.getByTestId("backtest-logs")).not.toContainText(/Traceback|Unhandled exception/i);
    await page.screenshot({ path: `../../tests/e2e/reports/artifacts/${BACKTEST_CASES.spy.name}.png`, fullPage: true });

    const history = new HistoryPage(page);
    await history.open();
    await history.filterByName(BACKTEST_CASES.spy.name);
    await history.expectRun(BACKTEST_CASES.spy.name);
    await history.openRunByText(BACKTEST_CASES.spy.name);
    await expect(page.getByTestId("run-status")).toContainText(/success|succeeded/i);
    await assertNoFrontendErrors();

    appendCaseResult({
      id: "Case A",
      name: "SPY SMA cross",
      status: "Pass",
      details: {
        runId,
        status: waitResult.final.status,
        initialCash: BACKTEST_CASES.spy.cash,
        finalEquity: waitResult.final.statistics?.["End Equity"],
        totalReturn: waitResult.final.statistics?.["Net Profit"],
        sharpe: waitResult.final.statistics?.["Sharpe Ratio"],
        totalTrades: waitResult.final.statistics?.["Total Trades"] ?? waitResult.final.statistics?.["Total Orders"]
      }
    });
  });
});
