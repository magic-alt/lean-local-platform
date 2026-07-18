import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { BacktestConfigPage } from "../pages/backtest-config.page";
import { ensureE2EProject } from "../utils/api";
import { appendCaseResult } from "../utils/report-writer";
import { BACKTEST_CASES, E2E_PROJECT } from "../utils/test-data";

test.describe("07 invalid symbol error handling @backtest", () => {
  test("blocks invalid symbols at preflight and persists a traceable workflow error", async ({ page, request }, testInfo) => {
    test.setTimeout(10 * 60_000);
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo, [/Failed to load resource:.*400 \(Bad Request\)/i]);
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
    const beforeResponse = await request.get("/api/backtests");
    const beforeRuns = await beforeResponse.json() as Array<{ name?: string }>;
    const preflightPromise = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/backtests/preflight" && response.request().method() === "POST"
    );
    await page.getByTestId("run-backtest-button").click();
    const preflight = await preflightPromise;
    expect(preflight.status()).toBe(400);
    const traceId = preflight.headers()["x-trace-id"];
    const workflowId = preflight.headers()["x-workflow-id"];
    expect(traceId).toBeTruthy();
    expect(workflowId).toBeTruthy();
    expect(await preflight.text()).toMatch(/missing|data|symbol|INVALID_SYMBOL_E2E/i);
    await expect(page.getByText(new RegExp(`Trace: ${traceId}`)).first()).toBeVisible();
    const workflow = await request.get(`/api/workflows/${encodeURIComponent(workflowId)}`);
    expect(workflow.ok()).toBeTruthy();
    expect((await workflow.json()).status).toBe("failed");
    await page.screenshot({ path: `../../tests/e2e/reports/artifacts/${BACKTEST_CASES.invalidSymbol.name}.png`, fullPage: true });
    const afterRuns = await (await request.get("/api/backtests")).json() as Array<{ name?: string }>;
    expect(afterRuns.filter((item) => item.name === BACKTEST_CASES.invalidSymbol.name)).toHaveLength(
      beforeRuns.filter((item) => item.name === BACKTEST_CASES.invalidSymbol.name).length
    );
    await assertNoFrontendErrors();

    appendCaseResult({
      id: "Case C",
      name: "Invalid symbol error handling",
      status: "Pass",
      details: {
        status: "preflight_blocked",
        traceId,
        workflowId,
        enteredHistory: false,
        blankScreen: false
      }
    });
  });
});
