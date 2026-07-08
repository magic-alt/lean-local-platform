import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class SettingsPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/settings");
    await this.expectHeading("Settings");
  }

  async expectDefaultsVisible() {
    await expect(this.page.getByText("Defaults")).toBeVisible();
    await expect(this.page.getByLabel("Docker Image", { exact: true })).toBeVisible();
    await expect(this.page.getByRole("button", { name: "Save Settings" })).toBeVisible();
  }
}
