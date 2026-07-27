import { expect, test, type Locator } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";


async function itemPositions(items: Locator) {
  const boxes = await items.evaluateAll((elements) => elements.map((element) => {
    const box = element.getBoundingClientRect();
    return { left: Math.round(box.left), top: Math.round(box.top), width: Math.round(box.width) };
  }));
  return boxes;
}

test.describe("12 responsive compact forms @responsive", () => {
  test("project form uses four, two, and one column layouts without losing advanced values", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await page.goto("/#/projects");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

    const createCard = page.locator(".ant-card").filter({ hasText: "Create Project" }).first();
    const marketItems = createCard.locator(".form-grid").nth(1).locator(":scope > .ant-form-item");
    await expect(marketItems).toHaveCount(4);

    let positions: Awaited<ReturnType<typeof itemPositions>> = [];
    for (const width of [1920, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      positions = await itemPositions(marketItems);
      expect(new Set(positions.map((item) => item.top)).size).toBe(1);
    }

    await page.setViewportSize({ width: 900, height: 900 });
    positions = await itemPositions(marketItems);
    expect(positions[0].top).toBe(positions[1].top);
    expect(positions[2].top).toBeGreaterThan(positions[0].top);
    expect(positions[2].top).toBe(positions[3].top);

    await page.setViewportSize({ width: 390, height: 844 });
    positions = await itemPositions(marketItems);
    expect(new Set(positions.map((item) => item.top)).size).toBe(4);
    const mobileLayout = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      offenders: [...document.querySelectorAll<HTMLElement>("body *")]
        .map((element) => ({
          className: element.className?.toString().slice(0, 100),
          right: Math.round(element.getBoundingClientRect().right),
          scrollWidth: element.scrollWidth,
          width: Math.round(element.getBoundingClientRect().width),
        }))
        .filter((item) => item.right > window.innerWidth + 1 || item.scrollWidth > item.width + 1)
        .sort((a, b) => b.right - a.right)
        .slice(0, 8),
    }));
    expect(mobileLayout.scrollWidth, JSON.stringify(mobileLayout.offenders)).toBeLessThanOrEqual(390);

    await createCard.getByText("Advanced settings", { exact: true }).click();
    const classInput = createCard.getByLabel("Algorithm Class", { exact: true });
    await classInput.fill("ResponsiveLayoutAlgorithm");
    await createCard.getByText("Advanced settings", { exact: true }).click();
    await createCard.getByText("Advanced settings", { exact: true }).click();
    await expect(classInput).toHaveValue("ResponsiveLayoutAlgorithm");

    await assertNoFrontendErrors();
  });

  test("paper account wizard exposes labeled controls in a stable focus order", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
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
    await page.route("**/api/projects?*", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.goto("/#/paper");
    await expect(page.getByRole("heading", { name: "模拟账户" })).toBeVisible();
    await page.getByRole("button", { name: "新建模拟账户" }).click();
    const dialog = page.getByRole("dialog", { name: "新建模拟账户" });
    await expect(dialog.getByRole("textbox", { name: /账户名称/ })).toBeVisible();
    await expect(dialog.getByRole("spinbutton", { name: /初始资金/ })).toBeVisible();
    await expect(dialog.getByRole("textbox", { name: /基准/ })).toBeVisible();
    const firstFocusableLabels = await dialog.locator("input:not([disabled]), button:not([disabled])").evaluateAll(
      (elements) => elements.slice(0, 4).map((element) => element.getAttribute("aria-label") || element.getAttribute("id") || element.textContent?.trim())
    );
    expect(firstFocusableLabels.some((label) => String(label).includes("name"))).toBeTruthy();
    await assertNoFrontendErrors();
  });
});
