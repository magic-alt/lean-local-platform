import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class BacktestResultPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open(runId: string) {
    await this.gotoHash(`/runs/${runId}`);
    await expect(this.page.getByTestId("run-status-panel")).toBeVisible();
  }

  async expectCompleted() {
    await expect(this.page.getByTestId("run-status")).toContainText(/success|succeeded/i);
  }

  async expectFailed() {
    await expect(this.page.getByTestId("run-status")).toContainText(/failed|interrupted|cancelled/i);
  }

  async expectCoreMetrics() {
    for (const testId of [
      "metric-initial-cash",
      "metric-end-equity",
      "metric-total-return",
      "metric-sharpe",
      "metric-drawdown",
      "metric-total-trades"
    ]) {
      await expect(this.page.getByTestId(testId)).toBeVisible();
    }
  }

  async expectCharts() {
    await this.page.getByRole("tab", { name: "Charts" }).click();
    const equity = this.page.getByTestId("equity-chart");
    const price = this.page.getByTestId("price-chart");
    await expect(equity).toBeVisible();
    await expect(price).toBeVisible();
    await expect.poll(async () => Number(await equity.getAttribute("data-point-count"))).toBeGreaterThan(0);
    await expect.poll(async () => Number(await price.getAttribute("data-point-count"))).toBeGreaterThan(0);
  }

  async expectLogs(pattern: RegExp) {
    await this.page.getByRole("tab", { name: "Logs" }).click();
    await expect(this.page.getByTestId("backtest-logs")).toContainText(pattern);
  }

  async expectRecordsPanel() {
    await this.page.getByRole("tab", { name: "Records" }).click();
    await expect(this.page.getByTestId("records-panel")).toBeVisible();
  }
}
