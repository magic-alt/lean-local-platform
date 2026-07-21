import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";


test.describe("10 documentation center @smoke @responsive", () => {
  test("renders GFM, navigates deep links, searches and stays responsive", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);
    await page.goto("/#/docs/index");
    await expect(page.getByRole("heading", { name: "LEAN Local 文档中心" })).toBeVisible();
    await expect(page.locator(".docs-sidebar")).toHaveCount(1);
    await expect(page.getByText("中文操作教程 + 完整技术参考")).toHaveCount(0);

    const appSidebar = page.locator(".app-sidebar");
    const sidebarTop = await appSidebar.evaluate((element) => element.getBoundingClientRect().top);
    await page.evaluate(() => window.scrollTo(0, 900));
    await expect.poll(() => appSidebar.evaluate((element) => Math.round(element.getBoundingClientRect().top))).toBe(Math.round(sidebarTop));
    await page.evaluate(() => window.scrollTo(0, 0));

    const sidebar = page.locator(".docs-sidebar");
    const guideToggle = sidebar.getByRole("button", { name: "操作教程" });
    await guideToggle.click();
    await expect(sidebar.getByRole("button", { name: "快速开始", exact: true })).toHaveCount(0);
    await guideToggle.click();
    await expect(sidebar.getByRole("button", { name: "快速开始", exact: true })).toBeVisible();

    await page.getByRole("link", { name: "快速开始" }).first().click();
    await expect(page).toHaveURL(/#\/docs\/quick-start/);
    await expect(page.getByRole("heading", { name: "1. 环境要求" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("heading", { name: "快速开始" })).toBeVisible();

    await page.goto("/#/docs/data?section=数据集类型");
    await expect(page.locator(".docs-markdown table").first()).toBeVisible();
    await expect(page.getByText("| Dataset |", { exact: false })).toHaveCount(0);

    const search = page.getByPlaceholder("搜索配置、API、操作或错误");
    await search.fill("maxBatchRuns");
    await expect(page.locator(".docs-search-results")).toContainText("批量");

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await assertNoFrontendErrors();
  });
});
