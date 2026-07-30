import { expect, test } from "@playwright/test";

test.describe("19 优化页加载稳定性", () => {
  test("组合候选接口失败时只请求一次并在对应页签内提示", async ({ page }) => {
    let candidateRequests = 0;

    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());

      if (url.pathname === "/api/portfolio-optimizations/candidates") {
        candidateRequests += 1;
        return route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Not Found" }),
        });
      }
      if (url.pathname === "/api/examples") {
        return route.fulfill({ json: { items: [], count: 0 } });
      }
      return route.fulfill({ json: [] });
    });

    await page.goto("/#/optimization");
    await expect(page.getByRole("heading", { name: "Optimization Center" })).toBeVisible();
    await expect.poll(() => candidateRequests).toBe(1);
    await page.waitForTimeout(500);
    expect(candidateRequests).toBe(1);
    await expect(page.locator(".ant-message-error")).toHaveCount(0);

    await page.getByRole("tab", { name: "Portfolio Builder" }).click();
    await expect(page.getByText("组合候选加载失败")).toBeVisible();
    await expect(page.getByText("Not Found", { exact: true })).toBeVisible();
  });
});
