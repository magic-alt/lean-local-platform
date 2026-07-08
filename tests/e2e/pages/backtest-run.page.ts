import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class BacktestRunPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open(runId: string) {
    await this.gotoHash(`/runs/${runId}`);
    await expect(this.page.getByTestId("run-status")).toBeVisible();
  }

  async refresh() {
    await this.page.getByRole("button", { name: "Refresh" }).click();
  }

  async openLogs() {
    await this.page.getByRole("tab", { name: "Logs" }).click();
    await expect(this.page.getByTestId("backtest-logs")).toBeVisible();
  }
}
