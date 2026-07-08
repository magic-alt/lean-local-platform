import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class StrategyPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async openProjects() {
    await this.gotoHash("/projects");
    await this.expectHeading("Projects");
  }

  async createProject(values: {
    name: string;
    assetClass?: string;
    market?: string;
    resolution?: string;
    strategy?: string;
    className?: string;
  }) {
    await this.openProjects();
    await this.fillByLabel("Name", values.name);
    if (values.assetClass) await this.selectByTestId("project-asset-select", values.assetClass);
    if (values.market) await this.selectByTestId("project-market-select", values.market);
    if (values.resolution) await this.selectByTestId("project-resolution-select", values.resolution);
    if (values.strategy) await this.selectByTestId("project-template-select", values.strategy);
    if (values.className) await this.fillByLabel("Class", values.className);
    await this.page.getByRole("button", { name: "Create" }).click();
    await this.expectHeading("Project Workspace");
  }

  async openWorkspaceFor(projectName: string) {
    await this.openProjects();
    const row = this.page.getByRole("row").filter({ hasText: projectName }).first();
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Workspace" }).click();
    await this.expectHeading("Project Workspace");
  }

  async expectCodeEditorLoaded() {
    await this.page.getByRole("tab", { name: "Code" }).click();
    await expect(this.page.locator(".monaco-editor")).toBeVisible();
  }

  async saveCodeIfDirty() {
    const save = this.page.getByRole("button", { name: "Save" });
    if (await save.isEnabled()) {
      await save.click();
      await expect(this.page.getByText("Saved")).toBeVisible();
    }
  }
}
