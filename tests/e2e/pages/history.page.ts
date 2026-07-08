import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class HistoryPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/backtests");
    await this.expectHeading("Backtests");
    await expect(this.page.getByText("History")).toBeVisible();
    const clear = this.page.getByRole("button", { name: "Clear" });
    if (await clear.count()) {
      await clear.click();
    }
  }

  async filterByName(name: string) {
    await this.page.getByPlaceholder("Name").fill(name);
    await this.page.getByRole("button", { name: "Filter" }).click();
  }

  async filterByStatus(status: string) {
    await this.selectByTestId("history-status-select", status);
    await this.page.getByRole("button", { name: "Filter" }).click();
  }

  async filterByMarket(marketLabel: string) {
    await this.selectByTestId("history-market-select", marketLabel);
    await this.page.getByRole("button", { name: "Filter" }).click();
  }

  async expectRun(nameOrId: string) {
    await expect(this.page.getByTestId("runs-table")).toContainText(nameOrId);
  }

  async openRunByText(text: string) {
    const row = this.page.getByRole("row").filter({ hasText: text }).first();
    await expect(row).toBeVisible();
    await row.getByText("Open").click();
    await expect(this.page).toHaveURL(/#\/runs\//);
  }
}
