import { expect, test } from "@playwright/test";

const accounts = [
  {
    id: "paper-a", shadow_session_id: "retired-a", name: "稳健账户", status: "active",
    market_scope: "china", base_currency: "CNY", initial_cash: "1000000", benchmark_symbol: "000300",
    current_generation: 1, total_equity: "1020000", available_cash: "700000", market_value: "320000",
    daily_pnl: "1200", cumulative_return: "0.02", benchmark_return: "0.01", excess_return: "0.01",
    position_count: 2, health_status: "healthy", primary_strategy: "CSI300 Rotation",
    automation_status: "active", next_scheduled_at: "2026-07-28T15:45:00+08:00",
    last_run_status: "succeeded", last_run_at: "2026-07-27T15:50:00+08:00",
    created_at: "", updated_at: ""
  },
  {
    id: "paper-b", shadow_session_id: "retired-b", name: "进取账户", status: "error",
    market_scope: "china", base_currency: "CNY", initial_cash: "3000000", benchmark_symbol: "000300",
    current_generation: 1, total_equity: "2940000", available_cash: "1800000", market_value: "1140000",
    daily_pnl: "-20000", cumulative_return: "-0.02", benchmark_return: "0.01", excess_return: "-0.03",
    position_count: 4, health_status: "degraded", primary_strategy: "Small Cap",
    automation_status: "error", next_scheduled_at: null, last_run_status: "failed",
    last_failure_code: "benchmark_missing", last_failure_detail: "benchmark missing after QA critical",
    created_at: "", updated_at: ""
  }
];

test.describe("17 多账户模拟盘用户旅程 @smoke @responsive", () => {
  test("比较隔离账户、查看每日运行并返回原筛选上下文", async ({ page }) => {
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/paper/accounts/compare") {
        return route.fulfill({
          json: {
            comparable: true, currencies: ["CNY"], comparisonStart: "2026-07-01", valuationDate: "2026-07-27", missingData: [],
            accounts: accounts.map((account) => ({
              accountId: account.id, name: account.name, currency: "CNY", benchmarkSymbol: "000300",
              cumulativeReturn: account.cumulative_return, benchmarkReturn: account.benchmark_return,
              excessReturn: account.excess_return, turnover: "0.1", tradeCount: 2, positionCount: account.position_count,
              riskRejectCount: account.id === "paper-b" ? 2 : 0, cashRatio: "0.5", lastRunDate: "2026-07-27"
            }))
          }
        });
      }
      if (url.pathname === "/api/paper/accounts") {
        return route.fulfill({ json: { items: accounts, count: 2, limit: 50, offset: 0, dataTrust: { valuationTrusted: true, reason: null } } });
      }
      if (url.pathname === "/api/paper/certification-cohorts") {
        return route.fulfill({ json: { items: [], count: 0 } });
      }
      if (url.pathname === "/api/paper/accounts/paper-b/overview") {
        return route.fulfill({
          json: {
            account: accounts[1],
            deployment: {
              id: "deployment-b", paper_account_id: "paper-b", version: 1, name: "Small Cap", status: "error", is_primary: 1,
              project_id: "project-b", source_backtest_id: "run-b", project_snapshot_id: "snapshot-b",
              dataset_version_id: "dataset-b", schedule_type: "market_daily", schedule_expression: "after_close+00:45",
              market_timezone: "Asia/Shanghai", execution_timing: "next_open", signal_mode: "paper_execute",
              strategy_fingerprint: "strategy-b", dataset_fingerprint: "dataset-b", deployment_fingerprint: "deployment-b",
              next_scheduled_at: null, consecutive_failures: 3
            },
            latestCycle: {
              id: "cycle-b", paper_account_id: "paper-b", deployment_id: "deployment-b", trading_date: "2026-07-27",
              status: "failed", signal_count: 0, intent_count: 0, order_count: 0, fill_count: 0, rejected_count: 0,
              failure_code: "benchmark_missing", failure_detail: "benchmark missing after QA critical"
            },
            dataTrust: { valuationTrusted: true, reason: null },
            dataReadiness: { watermark: { last_data_date: "2026-07-26" }, qa: { severity: "critical" } }
          }
        });
      }
      if (url.pathname === "/api/paper/accounts/paper-b/deployments") return route.fulfill({ json: [] });
      if (url.pathname === "/api/paper/accounts/paper-b/cycles") {
        return route.fulfill({ json: { items: [], count: 0, limit: 50, offset: 0 } });
      }
      if (url.pathname.endsWith("/positions") || url.pathname.endsWith("/orders") || url.pathname.endsWith("/signals")) {
        return route.fulfill({ json: { items: [], count: 0, limit: 50, offset: 0 } });
      }
      if (url.pathname.endsWith("/performance")) return route.fulfill({ json: { points: [] } });
      if (url.pathname === "/api/health/dependencies") {
        return route.fulfill({ json: { status: "degraded", dependencies: [{ service: "backtest_worker", ok: false, detail: "worker unavailable" }] } });
      }
      return route.continue();
    });

    await page.goto("/#/paper?view=cards&status=error");
    await expect(page.getByRole("heading", { name: "模拟账户" })).toBeVisible();
    await page.getByLabel("选择账户 稳健账户").check();
    await page.getByLabel("选择账户 进取账户").check();
    await page.getByRole("button", { name: /比较 2/ }).click();
    await expect(page.getByRole("dialog").getByText("-3.00%")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

    await page.getByRole("link", { name: "进取账户" }).click();
    await expect(page.getByText("benchmark missing after QA critical").first()).toBeVisible();
    const dailyRunTab = page.getByRole("tab", { name: "每日运行" });
    if ((page.viewportSize()?.width || 0) <= 390) {
      const target = new URL(page.url());
      target.hash = `${target.hash}${target.hash.includes("?") ? "&" : "?"}tab=daily-runs`;
      await page.goto(target.toString());
    } else {
      await dailyRunTab.click();
    }
    await expect(dailyRunTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Worker / 队列")).toBeVisible();
    await page.getByRole("button", { name: "返回账户" }).click();
    await expect(page).toHaveURL(/status=error/);
    await expect(page).toHaveURL(/view=cards/);
  });
});
