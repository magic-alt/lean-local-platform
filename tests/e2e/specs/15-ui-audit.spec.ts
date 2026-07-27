import { expect, test } from "@playwright/test";


test.describe("15 navigation and required viewports @smoke @responsive", () => {
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
      await expect(page.getByRole("button", { name: "打开导航" })).toBeVisible();
      await page.getByRole("button", { name: "打开导航" }).click();
      const mobileNavigation = page.getByRole("navigation", { name: "移动端导航" });
      await expect(mobileNavigation).toBeVisible();
      await expect(mobileNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "概览" })).toBeVisible();
      await mobileNavigation.getByRole("link", { name: "模拟交易" }).click();
      await expect(page.getByRole("heading", { name: "模拟账户" })).toBeVisible();
    } else {
      const primaryNavigation = page.getByRole("navigation", { name: "主导航" });
      await expect(primaryNavigation).toBeVisible();
      for (const group of ["研究", "回测", "交易", "系统"]) {
        await expect(primaryNavigation.getByText(group, { exact: true }).first()).toBeVisible();
      }
      await expect(primaryNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "概览" })).toBeVisible();
      await page.goto("/#/paper");
      await expect(page.getByRole("heading", { name: "模拟账户" })).toBeVisible();
      await expect(primaryNavigation.locator(".ant-menu-item-selected").getByRole("link", { name: "模拟交易" })).toBeVisible();
    }

    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  });
});
