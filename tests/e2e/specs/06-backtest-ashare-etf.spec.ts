import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { BacktestConfigPage } from "../pages/backtest-config.page";
import { BacktestResultPage } from "../pages/backtest-result.page";
import { HistoryPage } from "../pages/history.page";
import { apiGet, BacktestResultPayload, ensureE2EProject } from "../utils/api";
import { isSuccessfulStatus, waitForBacktestTerminal } from "../utils/backtest-waiter";
import { appendCaseResult } from "../utils/report-writer";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("06 real A-share ETF 510300 backtest @backtest", () => {
  test("runs E2E_Backtest_A_SHARE_ETF_510300_2024 through the Web", async ({ page, request }, testInfo) => {
    test.setTimeout(20 * 60_000);
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await ensureE2EProject(request);

    const config = new BacktestConfigPage(page);
    await config.open();
    await config.fill({
      ...BACKTEST_CASES.ashare,
      projectName: E2E_PROJECT.name,
      assetClass: "Equity",
      marketLabel: "A Share",
      feeModel: "Default",
      slippageModel: "Default"
    });
    const runId = await config.runAndCaptureId();
    const waitResult = await waitForBacktestTerminal(request, runId, { requireRunningState: true });
    expect(isSuccessfulStatus(waitResult.final.status), waitResult.final.error_message || waitResult.statuses.join(" -> ")).toBeTruthy();

    const result = await apiGet<BacktestResultPayload>(request, `/api/backtests/${runId}/result`);
    expect(result.job.symbol).toBe(BACKTEST_CASES.ashare.symbol);
    expect(result.job.parameters).toMatchObject({
      ticker: BACKTEST_CASES.ashare.symbol,
      market: BACKTEST_CASES.ashare.market,
      source: BACKTEST_CASES.ashare.source,
      benchmarkSymbol: BACKTEST_CASES.ashare.benchmarkSymbol,
      start: BACKTEST_CASES.ashare.start,
      end: BACKTEST_CASES.ashare.end
    });
    expect(result.result.equity_curve.length).toBeGreaterThan(0);

    const resultPage = new BacktestResultPage(page);
    await resultPage.open(runId);
    await resultPage.expectCompleted();
    await resultPage.expectCoreMetrics();
    await resultPage.expectCharts();
    await resultPage.expectRecordsPanel();
    await page.screenshot({ path: `../../tests/e2e/reports/artifacts/${BACKTEST_CASES.ashare.name}.png`, fullPage: true });

    const history = new HistoryPage(page);
    await history.open();
    await history.filterByMarket("A Share");
    await history.filterByName(BACKTEST_CASES.ashare.name);
    await history.expectRun(BACKTEST_CASES.ashare.name);
    await assertNoFrontendErrors();

    appendCaseResult({
      id: "Case B",
      name: "A-share ETF 510300",
      status: "Pass",
      details: {
        runId,
        status: waitResult.final.status,
        dataSource: BACKTEST_CASES.ashare.source,
        dataExists: true,
        finalEquity: waitResult.final.statistics?.["End Equity"],
        totalReturn: waitResult.final.statistics?.["Net Profit"],
        maxDrawdown: waitResult.final.statistics?.["Drawdown"] ?? waitResult.final.statistics?.["Max Drawdown"],
        sharpe: waitResult.final.statistics?.["Sharpe Ratio"]
      }
    });
  });
});
