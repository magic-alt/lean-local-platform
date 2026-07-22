import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

import { HistoryPage } from "../pages/history.page";
import { apiURL, artifactsDir } from "../utils/env";
import { listBacktests } from "../utils/api";
import { BACKTEST_CASES } from "../utils/test-data";

test.describe("08 history and report export", () => {
  test("only offers HTML and Markdown as browser previews", async ({ page, context }) => {
    const reportId = "backtest:preview-run";
    await page.route("**/api/reports", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{
        id: reportId,
        source: "backtest_run",
        run_id: "preview-run",
        type: "backtest",
        benchmark: "000300",
        status: "success",
        created_at: "2026-07-18T00:00:00+00:00"
      }])
    }));
    await context.route((url) =>
      decodeURIComponent(url.pathname) === "/api/reports/backtest:preview-run/export" && url.searchParams.get("format") === "html",
    (route) => route.fulfill({
      status: 200,
      contentType: "text/html",
      headers: { "Content-Disposition": 'inline; filename="backtest-report-preview-run.html"' },
      body: "<html><body><h1>Inline HTML preview</h1></body></html>"
    }));
    await context.route((url) =>
      decodeURIComponent(url.pathname) === "/api/reports/backtest:preview-run/export" && url.searchParams.get("format") === "markdown",
    (route) => route.fulfill({
      status: 200,
      contentType: "text/plain",
      headers: { "Content-Disposition": 'inline; filename="backtest-report-preview-run.md"' },
      body: "# Inline Markdown preview"
    }));

    await page.goto("/#/reports");
    const reportRow = page.locator("tr").filter({ hasText: "preview-run" }).first();
    const htmlLink = reportRow.getByRole("link", { name: "HTML" });
    const markdownLink = reportRow.getByRole("link", { name: "MD" });
    await expect(reportRow).toContainText("Backtest");
    await expect(reportRow).toContainText("000300");
    await expect(page.getByRole("columnheader", { name: "Result" })).toHaveCount(0);
    await expect(page.getByRole("columnheader", { name: "Objects" })).toHaveCount(0);
    await expect(htmlLink).toBeVisible();
    await expect(markdownLink).toBeVisible();
    await expect(reportRow.getByRole("link", { name: "PDF" })).toHaveCount(0);
    await expect(reportRow.getByRole("link", { name: "CSV" })).toHaveCount(0);
    await expect(reportRow.getByRole("link", { name: "JSON" })).toHaveCount(0);
    await expect(htmlLink).not.toHaveAttribute("download", /.+/);
    await expect(markdownLink).not.toHaveAttribute("download", /.+/);

    const htmlPopupPromise = page.waitForEvent("popup");
    await htmlLink.click();
    const htmlPopup = await htmlPopupPromise;
    await expect(htmlPopup.getByRole("heading", { name: "Inline HTML preview" })).toBeVisible();
    await htmlPopup.close();

    const markdownPopupPromise = page.waitForEvent("popup");
    await markdownLink.click();
    const markdownPopup = await markdownPopupPromise;
    await expect(markdownPopup.locator("body")).toContainText("Inline Markdown preview");
    await markdownPopup.close();
  });

  test("finds the successful E2E run in history and exports its report", async ({ page, request }) => {
    const runs = await listBacktests(request);
    const spyRun = runs.find((run) => run.name === BACKTEST_CASES.spy.name && (run.status === "success" || run.status === "succeeded"));
    test.skip(!spyRun, "Run the @backtest suite first so history/export has a successful E2E run.");

    const history = new HistoryPage(page);
    await history.open();
    await history.filterByName(BACKTEST_CASES.spy.name);
    await history.expectRun(BACKTEST_CASES.spy.name);
    await history.filterByStatus("success");
    await history.expectRun(BACKTEST_CASES.spy.name);

    await page.goto("/#/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await expect(page.locator(".app-content")).toContainText(spyRun!.id);
    const reportRow = page.locator("tr").filter({ hasText: spyRun!.id }).first();
    await expect(reportRow.getByRole("link", { name: "HTML" })).toBeVisible();
    await expect(reportRow.getByRole("link", { name: "MD" })).toBeVisible();
    await expect(reportRow.getByRole("link", { name: "PDF" })).toHaveCount(0);
    await expect(reportRow.getByRole("link", { name: "CSV" })).toHaveCount(0);
    await expect(reportRow.getByRole("link", { name: "JSON" })).toHaveCount(0);
    await expect(reportRow.getByRole("link", { name: "HTML" })).not.toHaveAttribute("download", /.+/);

    const encodedReportId = encodeURIComponent(`backtest:${spyRun!.id}`);
    for (const format of ["html", "markdown"] as const) {
      const response = await request.get(`${apiURL}/api/reports/${encodedReportId}/export?format=${format}`);
      if (!response.ok()) {
        throw new Error(`${format} export failed: ${response.status()} ${await response.text()}`);
      }
      const body = await response.body();
      expect(body.length, `${format} export is empty`).toBeGreaterThan(0);
      const disposition = response.headers()["content-disposition"] || "";
      expect(disposition).toMatch(/^inline;/);
      expect(disposition).toContain(spyRun!.id);
      fs.writeFileSync(path.join(artifactsDir, `${BACKTEST_CASES.spy.name}.${format}`), body);
    }
    for (const format of ["pdf", "csv", "json"] as const) {
      const response = await request.get(`${apiURL}/api/reports/${encodedReportId}/export?format=${format}`);
      expect(response.status()).toBe(400);
    }
  });
});
