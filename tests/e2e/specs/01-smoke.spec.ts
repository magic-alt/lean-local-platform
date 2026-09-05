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
      ["项目", "Projects"],
      ["数据", "Data Library"],
      ["回测", "Backtests"],
      ["优化", "Optimization Center"],
      ["模拟交易", "模拟账户"],
      ["研究", "研究交付"],
      ["报告", "Reports"],
      ["洞察", "洞察 · A股科技日报"],
      ["任务", "Tasks"],
      ["监控", "Monitoring"],
      ["设置", "Settings"]
    ];

    for (const [label, heading] of routes) {
      await dashboard.navigateTo(label, heading);
      await expect(page.locator(".app-content")).not.toBeEmpty();
      await page.screenshot({ path: `../../tests/e2e/reports/artifacts/smoke-${label.replace(/\s+/g, "-").toLowerCase()}-${testInfo.project.name}.png`, fullPage: true });
      await page.reload();
      await dashboard.expectHeading(heading);
    }

    await page.goto("/#/ashare-research");
    await dashboard.expectHeading("研究交付");

    await page.goto("/#/compare");
    await dashboard.expectHeading("Optimization Center");
    await expect(page.getByRole("tab", { name: "Compare Results" })).toBeVisible();

    await page.goto("/#/object-store");
    await expect(page.getByText("Page Not Found")).toBeVisible();

    await page.goto("/#/missing-e2e-route");
    await expect(page.getByText("Page Not Found")).toBeVisible();
    await assertNoFrontendErrors();
  });
});
