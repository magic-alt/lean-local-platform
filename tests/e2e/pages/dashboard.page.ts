import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/");
    await this.expectHeading("Dashboard");
  }

  async expectShellNavigation() {
    for (const item of [
      "Dashboard",
      "Projects",
      "Data",
      "Backtests",
      "Optimization",
      "Paper",
      "Research",
      "Reports",
      "Insights",
      "Tasks",
      "Monitoring",
      "Settings"
    ]) {
      await expect(this.page.getByRole("link", { name: item, exact: true })).toBeVisible();
    }
  }

  async navigateTo(label: string, heading: string | RegExp) {
    await this.page.getByRole("link", { name: label, exact: true }).click();
    await this.expectHeading(heading);
  }
}
