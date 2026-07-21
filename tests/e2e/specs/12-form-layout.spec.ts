import { expect, test, type Locator } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";


async function itemPositions(items: Locator) {
  const boxes = await items.evaluateAll((elements) => elements.map((element) => {
    const box = element.getBoundingClientRect();
    return { left: Math.round(box.left), top: Math.round(box.top), width: Math.round(box.width) };
  }));
  return boxes;
}

async function selectAdjacentAntOption(control: Locator, key: "ArrowDown" | "ArrowUp") {
  await control.click();
  const page = control.page();
  const dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last();
  await expect(dropdown).toBeVisible();
  await page.keyboard.press(key);
  await page.keyboard.press("Enter");
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

  test("paper mode only exposes fields required by the active workflow", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await page.goto("/#/paper");
    await expect(page.getByRole("heading", { name: "LEAN Paper" })).toBeVisible();

    const createCard = page.locator(".ant-card").filter({ hasText: "Create Paper Session" }).first();
    const mode = createCard.getByLabel("Mode", { exact: true });
    await selectAdjacentAntOption(mode, "ArrowDown");
    await expect(createCard.getByLabel("Market", { exact: true })).toBeVisible();
    await expect(createCard.getByLabel("Symbol", { exact: true })).toBeVisible();
    await expect(createCard.getByLabel("Initial Cash", { exact: true })).toBeVisible();
    await expect(createCard.getByLabel("Project", { exact: true })).toHaveCount(0);

    await selectAdjacentAntOption(mode, "ArrowUp");
    await expect(createCard.getByLabel("Project", { exact: true })).toBeVisible();
    await expect(createCard.getByLabel("Trusted Backtest", { exact: true })).toBeVisible();
    await expect(createCard.getByLabel("Initial Cash", { exact: true })).toHaveCount(0);
    await assertNoFrontendErrors();
  });
});
