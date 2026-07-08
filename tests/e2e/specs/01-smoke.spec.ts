import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";
import { DashboardPage } from "../pages/dashboard.page";

test.describe("01 smoke and navigation @smoke @responsive", () => {
  test("core pages render without white screen or severe browser errors", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    const dashboard = new DashboardPage(page);
    await dashboard.open();
    await dashboard.expectShellNavigation();
    await dashboard.screenshot(`smoke-dashboard-${testInfo.project.name}`);

    const routes: Array<[string, string | RegExp]> = [
      ["Projects", "Projects"],
      ["Data", "Data Library"],
      ["Backtests", "Backtests"],
      ["Compare", "Strategy Compare"],
      ["Optimization", "Optimization"],
      ["Paper", "Paper Replay"],
      ["Research", "Research"],
      ["A-Share Research", "A-Share Research"],
      ["Reports", "Reports"],
      ["Object Store", "Object Store"],
      ["Tasks", "Tasks"],
      ["Monitoring", "Monitoring"],
      ["Settings", "Settings"]
    ];

    for (const [label, heading] of routes) {
      await dashboard.navigateTo(label, heading);
      await expect(page.locator(".app-content")).not.toBeEmpty();
      await page.screenshot({ path: `../../tests/e2e/reports/artifacts/smoke-${label.replace(/\s+/g, "-").toLowerCase()}-${testInfo.project.name}.png`, fullPage: true });
      await page.reload();
      await dashboard.expectHeading(heading);
    }

    await page.goto("/#/missing-e2e-route");
    await expect(page.getByText("Page Not Found")).toBeVisible();
    await assertNoFrontendErrors();
  });
});
