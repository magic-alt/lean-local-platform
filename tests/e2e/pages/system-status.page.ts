import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class SystemStatusPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/monitoring");
    await this.expectHeading("Monitoring");
  }

  async check() {
    await this.page.getByTestId("check-system-status-button").click();
    await expect(this.page.getByTestId("dependency-health-table")).toBeVisible();
  }

  async expectDependency(service: string, shouldBeUp = true) {
    const row = this.page.getByRole("row").filter({ hasText: service }).first();
    await expect(row).toBeVisible();
    await expect(row).toContainText(shouldBeUp ? "up" : "down");
  }
}
