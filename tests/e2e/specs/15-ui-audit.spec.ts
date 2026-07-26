import { expect, test } from "@playwright/test";


test.describe("15 navigation and required viewports @viewport", () => {
  test("highlights the active grouped navigation without horizontal overflow", async ({ page }) => {
    await page.route("**/api/backtests*", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route("**/api/tasks", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route("**/api/paper/accounts?*", async (route) => {
      await route.fulfill({
        json: {
          items: [],
          count: 0,
          limit: 50,
          offset: 0,
          dataTrust: { valuationTrusted: true, reason: null }
        }
      });
    });
    await page.goto("/#/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    const viewport = page.viewportSize();
    expect(viewport).not.toBeNull();
    const isTablet = (viewport?.width || 0) <= 991;

    if (isTablet) {
      await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
      await page.getByRole("button", { name: "Open navigation" }).click();
      const mobileNavigation = page.getByRole("navigation", { name: "Mobile navigation" });
      await expect(mobileNavigation).toBeVisible();
      await expect(mobileNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "Dashboard" })).toBeVisible();
      await mobileNavigation.getByRole("link", { name: "Paper Accounts" }).click();
      await expect(page.getByRole("heading", { name: "Paper Accounts" })).toBeVisible();
    } else {
      const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
      await expect(primaryNavigation).toBeVisible();
      await expect(primaryNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "Dashboard" })).toBeVisible();
      await page.goto("/#/paper");
      await expect(page.getByRole("heading", { name: "Paper Accounts" })).toBeVisible();
      await expect(primaryNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "Paper Accounts" })).toBeVisible();
    }

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  });
});
