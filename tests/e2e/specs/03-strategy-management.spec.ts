import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { StrategyPage } from "../pages/strategy.page";
import { E2E_PROJECT } from "../utils/test-data";

test.describe("03 strategy/project management", () => {
  test("create E2E SMA strategy project and verify code persists", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    const strategies = new StrategyPage(page);
    await strategies.createProject({
      name: E2E_PROJECT.name,
      assetClass: "Equity",
      market: "US Equity",
      resolution: "daily",
      strategy: "SMA Cross",
      className: "E2EMACrossTest"
    });
    await expect(page.getByText(E2E_PROJECT.name).first()).toBeVisible();
    await strategies.expectCodeEditorLoaded();
    await page.reload();
    await strategies.expectHeading("Project Workspace");
    await expect(page.getByText(E2E_PROJECT.name).first()).toBeVisible();
    await assertNoFrontendErrors();
  });
});
