import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";

test.describe("20 real local data preview", () => {
  test.skip(process.env.E2E_REAL_LOCAL_DATA !== "1", "requires the operator's mounted local Parquet lake");

  test("searches Parquet, renders an index chart, and survives route switches", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(page, testInfo);

    await page.goto("/#/data", { waitUntil: "networkidle" });
    await expect(page.getByRole("heading", { name: "Data Library" })).toBeVisible();

    const stockResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/data/query?")
        && response.url().includes("assetClass=equity")
        && response.status() === 200,
    );
    await page.getByRole("button", { name: /Preview$/ }).click();
    const stockPayload = await (await stockResponsePromise).json();
    expect(stockPayload.items.length).toBeGreaterThan(1_000);
    await expect(page.locator("canvas").last()).toBeVisible();

    await page.getByRole("tab", { name: "研究数据 Preview" }).click();
    const factorResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/data/dataset-preview/daily_basic") && response.status() === 200,
    );
    await page.getByPlaceholder(/股票代码或指标名/).fill("pe_ttm");
    await page.getByRole("button", { name: /查询本地 Parquet/ }).click();
    const factorPayload = await (await factorResponsePromise).json();
    expect(factorPayload.items.length).toBeGreaterThan(0);
    await expect(page.getByText("pe_ttm", { exact: true }).first()).toBeVisible();

    await page.getByRole("tab", { name: "指数 Preview" }).click();
    const indexCode = page.getByRole("button", { name: "000300.SH", exact: true });
    await expect(indexCode).toBeVisible();
    const chartResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/data/query?")
        && response.url().includes("assetClass=index")
        && response.status() === 200,
    );
    await indexCode.click();
    const chartPayload = await (await chartResponsePromise).json();
    expect(chartPayload.items.length).toBeGreaterThan(1_000);
    expect(chartPayload.truncated).toBe(false);
    await expect(page.locator("canvas").last()).toBeVisible();

    await page.getByRole("link", { name: "回测", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Backtests" })).toBeVisible();
    await page.getByRole("link", { name: "研究", exact: true }).click();
    await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
    await page.getByRole("link", { name: "数据", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Data Library" })).toBeVisible();

    await expect(page.getByText("Internal Server Error", { exact: false })).toHaveCount(0);
    await page.screenshot({ path: "../../tests/e2e/reports/artifacts/data-preview-fixed.png", fullPage: true });
    await assertNoFrontendErrors();
  });
});
