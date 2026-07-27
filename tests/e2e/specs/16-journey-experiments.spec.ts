import { expect, test } from "@playwright/test";

import { BasePage } from "../pages/base.page";

test.describe("16 实验与 Walk-Forward 用户旅程 @smoke @responsive", () => {
  test("预览并排队带冻结版本的 Walk-Forward 实验", async ({ page }) => {
    const batches: Array<Record<string, unknown>> = [];
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      if (url.pathname === "/api/projects") {
        return route.fulfill({ json: [{ id: "wf-project", name: "WF Strategy", display_name: "WF Strategy", language: "Python", algorithm_class: "Main", project_path: "/tmp/wf", main_file: "main.py", config: {}, created_at: "", updated_at: "" }] });
      }
      if (url.pathname === "/api/strategies/templates" || url.pathname === "/api/asset-classes" || url.pathname === "/api/optimize") {
        return route.fulfill({ json: [] });
      }
      if (url.pathname === "/api/examples") return route.fulfill({ json: { items: [], count: 0 } });
      if (url.pathname === "/api/securities/search") {
        return route.fulfill({ json: { items: [], count: 0, query: "", markets: ["china"] } });
      }
      if (url.pathname === "/api/experiment-batches/preview") {
        return route.fulfill({ json: { expandedCount: 6, limit: 200, effectiveConcurrency: 2, withinLimit: true, warnings: [] } });
      }
      if (url.pathname === "/api/experiment-batches" && method === "POST") {
        const batch = {
          id: "wf-batch", name: "E2E Walk Forward", kind: "optimization", mode: "walk_forward",
          status: "queued", total: 6, succeeded: 0, failed: 0, skipped: 0, cancelled: 0,
          cancel_requested: false, created_at: "2026-07-27T09:00:00+08:00"
        };
        batches.push(batch);
        return route.fulfill({ status: 201, json: batch });
      }
      if (url.pathname === "/api/experiment-batches") return route.fulfill({ json: batches });
      return route.fulfill({ json: {} });
    });

    await page.goto("/#/optimization");
    await expect(page.getByRole("heading", { name: "Optimization" })).toBeVisible();
    const controls = new BasePage(page);
    await page.getByLabel("批次名称").fill("E2E Walk Forward");
    await controls.selectByLabel("运行模式", "Walk-forward");
    await controls.selectByLabel("项目", "WF Strategy");
    await page.getByText("高级优化设置", { exact: true }).click();
    await page.getByLabel("冻结 Dataset Version").fill("dataset:certified:20260727");
    await page.getByLabel("冻结 Universe Version").fill("universe:CSI300:20260727");
    await page.getByRole("button", { name: "预览展开" }).click();
    await expect(page.getByText(/将展开 6 个工作单元/)).toBeVisible();
    await page.getByRole("button", { name: "确认并排队" }).click();
    await expect(page.getByText("E2E Walk Forward").last()).toBeVisible();
    await expect(page.getByText("walk_forward").last()).toBeVisible();
  });
});
