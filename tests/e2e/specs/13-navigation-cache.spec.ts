import { expect, test } from "@playwright/test";

import { DashboardPage } from "../pages/dashboard.page";

test.describe("13 navigation data continuity @smoke", () => {
  test("keeps dashboard data visible after navigating away and back", async ({ page }) => {
    let backtestsRequests = 0;
    let tasksRequests = 0;

    await page.route("**/api/backtests**", async (route) => {
      if (route.request().method() !== "GET" || !/\/api\/backtests(?:\?|$)/.test(route.request().url())) {
        await route.continue();
        return;
      }
      backtestsRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: "navigation-cache-run",
          name: "Navigation cache run",
          symbol: "SPY",
          status: "success",
          duration_seconds: 12,
          statistics: {
            "Net Profit": "42.00%",
            "Sharpe Ratio": "1.50"
          },
          parameters: {},
          docker_image: "quantconnect/lean:latest",
          results_dir: "/tmp/navigation-cache-run",
          created_at: new Date().toISOString()
        }])
      });
    });
    await page.route("**/api/tasks**", async (route) => {
      if (route.request().method() !== "GET" || !/\/api\/tasks(?:\?|$)/.test(route.request().url())) {
        await route.continue();
        return;
      }
      tasksRequests += 1;
      await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    });

    const dashboard = new DashboardPage(page);
    await dashboard.open();
    await expect(page.getByText("42.00%", { exact: true })).toBeVisible();

    await dashboard.navigateTo("Projects", "Projects");
    await dashboard.navigateTo("Dashboard", "Dashboard");

    await expect(page.getByText("42.00%", { exact: true })).toBeVisible();
    await expect(page.getByText("N/A", { exact: true })).toHaveCount(0);
    expect(backtestsRequests).toBe(1);
    expect(tasksRequests).toBe(1);
  });
});
