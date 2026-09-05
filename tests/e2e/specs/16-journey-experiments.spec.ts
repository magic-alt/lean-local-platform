import { expect, test } from "@playwright/test";

import { BasePage } from "../pages/base.page";

test.describe("16 实验与 Walk-Forward 用户旅程 @smoke @responsive", () => {
  test("预览并排队带冻结数据口径的 Walk-Forward 优化", async ({ page }) => {
    const optimizations: Array<Record<string, unknown>> = [];
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      if (url.pathname === "/api/projects") {
        return route.fulfill({ json: [{ id: "wf-project", name: "WF Strategy", display_name: "WF Strategy", language: "Python", algorithm_class: "Main", project_path: "/tmp/wf", main_file: "main.py", config: {}, created_at: "", updated_at: "" }] });
      }
      if (url.pathname === "/api/strategies/templates" || url.pathname === "/api/asset-classes") {
        return route.fulfill({ json: [] });
      }
      if (url.pathname === "/api/examples") return route.fulfill({ json: { items: [], count: 0 } });
      if (url.pathname === "/api/optimizations/preview") {
        return route.fulfill({
          json: {
            kind: "optimization",
            mode: "walk_forward",
            expandedCount: 6,
            parameterCandidates: 1,
            workUnits: 6,
            limit: 200,
            effectiveConcurrency: 2,
            withinLimit: true,
            selection: { type: "symbols", values: ["000001"] },
            warnings: [],
            sample: [],
            scopeHash: "scope-e2e-walk-forward",
            dataFingerprint: "data-e2e-walk-forward"
          }
        });
      }
      if (url.pathname === "/api/optimizations" && method === "POST") {
        const optimization = {
          id: "wf-optimization",
          name: "E2E Walk Forward",
          mode: "walk_forward",
          status: "queued",
          created_at: "2026-09-05T09:00:00+08:00",
          summary: null
        };
        optimizations.push(optimization);
        return route.fulfill({ status: 201, json: optimization });
      }
      if (url.pathname === "/api/optimizations") return route.fulfill({ json: optimizations });
      return route.continue();
    });

    await page.goto("/#/optimization");
    await expect(page.getByRole("heading", { name: "Optimization Center" })).toBeVisible();
    const controls = new BasePage(page);
    await page.getByLabel("名称").fill("E2E Walk Forward");

    // Ant Design's virtualized Select does not consistently expose its options
    // through role=option in headless Chromium. Target the open dropdown item
    // directly so this test validates the product mode rather than the helper.
    await page.getByLabel("模式", { exact: true }).click();
    const modeDropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last();
    await expect(modeDropdown).toBeVisible();
    await modeDropdown.locator(".ant-select-item-option").filter({ hasText: /^Walk-forward$/ }).click();

    await controls.selectByLabel("策略项目", "WF Strategy");
    await page.getByRole("button", { name: "预览展开" }).click();
    await expect(page.getByText(/1 个参数候选 → 6 个标准回测工作单元/)).toBeVisible();
    await page.getByRole("button", { name: "创建优化" }).click();
    await expect(page.getByText(/优化已排队/)).toBeVisible();
  });
});
