import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

import { HistoryPage } from "../pages/history.page";
import { apiURL, artifactsDir } from "../utils/env";
import { listBacktests } from "../utils/api";
import { BACKTEST_CASES } from "../utils/test-data";

test.describe("08 history and report export", () => {
  test("finds successful and failed E2E runs in history and exports successful report", async ({ page, request }) => {
    const runs = await listBacktests(request);
    const spyRun = runs.find((run) => run.name === BACKTEST_CASES.spy.name && (run.status === "success" || run.status === "succeeded"));
    const failedRun = runs.find((run) => run.name === BACKTEST_CASES.invalidSymbol.name && run.status === "failed");
    test.skip(!spyRun || !failedRun, "Run the @backtest suite first so history/export has success and failed E2E runs.");

    const history = new HistoryPage(page);
    await history.open();
    await history.filterByName(BACKTEST_CASES.spy.name);
    await history.expectRun(BACKTEST_CASES.spy.name);
    await history.filterByStatus("success");
    await history.expectRun(BACKTEST_CASES.spy.name);

    await history.open();
    await history.filterByName(BACKTEST_CASES.invalidSymbol.name);
    await history.expectRun(BACKTEST_CASES.invalidSymbol.name);
    await history.filterByStatus("failed");
    await history.expectRun(BACKTEST_CASES.invalidSymbol.name);

    await page.goto("/#/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.locator(".app-content")).toContainText(spyRun!.id);

    const encodedReportId = encodeURIComponent(`backtest:${spyRun!.id}`);
    for (const format of ["json", "csv", "html", "pdf"] as const) {
      const response = await request.get(`${apiURL}/api/reports/${encodedReportId}/export?format=${format}`);
      if (!response.ok()) {
        throw new Error(`${format} export failed: ${response.status()} ${await response.text()}`);
      }
      const body = await response.body();
      expect(body.length, `${format} export is empty`).toBeGreaterThan(0);
      const disposition = response.headers()["content-disposition"] || "";
      expect(disposition).toContain(spyRun!.id);
      fs.writeFileSync(path.join(artifactsDir, `${BACKTEST_CASES.spy.name}.${format}`), body);
    }
  });
});
