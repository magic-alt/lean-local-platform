import { expect, test } from "@playwright/test";

test.describe("18 错误恢复用户旅程 @smoke @responsive", () => {
  test("API 503 后刷新恢复，路由切换和浏览器返回保留历史筛选", async ({ page }) => {
    let unavailable = true;
    const failedRun = {
      id: "recovery-run", name: "异常历史数据", symbol: "510300", status: "failed",
      parameters: { market: "china", start: "2026-07-01", end: "2026-07-20", cash: 300000 },
      docker_image: "quantconnect/lean:test", results_dir: "/tmp/recovery-run",
      error_message: "worker unavailable: Redis connection refused", created_at: "2026-07-27T08:00:00+08:00"
    };
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/backtests" && unavailable) {
        return route.fulfill({ status: 503, json: { detail: "服务暂不可用，请刷新重试" } });
      }
      if (url.pathname === "/api/backtests") return route.fulfill({ json: [failedRun] });
      if (url.pathname === `/api/backtests/${failedRun.id}`) return route.fulfill({ json: failedRun });
      if (url.pathname === `/api/backtests/${failedRun.id}/logs`) return route.fulfill({ json: { logs: "Redis connection refused" } });
      if (url.pathname === `/api/backtests/${failedRun.id}/validation`) return route.fulfill({ json: { job_id: failedRun.id, validation: null, experiment: null, fingerprint: null } });
      if (url.pathname === `/api/backtests/${failedRun.id}/admission`) return route.fulfill({ json: { runId: failedRun.id, registrationStatus: "not_applicable" } });
      if (url.pathname === "/api/projects" || url.pathname === "/api/strategies/templates" || url.pathname === "/api/asset-classes") return route.fulfill({ json: [] });
      if (url.pathname === "/api/examples") return route.fulfill({ json: { items: [], count: 0 } });
      if (url.pathname === "/api/settings") {
        return route.fulfill({
          json: {
            defaultAssetClass: "equity", defaultMarket: "china", defaultVenue: "china",
            defaultResolution: "daily", defaultDataType: "trade", defaultProvider: "tushare",
            defaultAdjust: "", defaultStrategyTemplate: "sma_cross", defaultCash: 300000,
            defaultStart: "2025-01-01", defaultEnd: "2025-12-31", dockerImage: "quantconnect/lean:test",
            researchImage: "quantconnect/research:test", chartPointLimit: 100000,
            maxConcurrentJobs: 1, maxBatchRuns: 100, jobTimeoutSeconds: 7200, logLevel: "INFO"
          }
        });
      }
      if (url.pathname === "/api/symbols") return route.fulfill({ json: { symbols: ["510300"], count: 1 } });
      if (url.pathname === "/api/securities/search") {
        return route.fulfill({ json: { items: [], count: 0, query: "", markets: ["china"] } });
      }
      return route.fulfill({ json: {} });
    });

    await page.goto("/#/backtests?view=history&status=failed&symbol=510300");
    await expect(page.getByText("服务暂不可用，请刷新重试").first()).toBeVisible();
    unavailable = false;
    await page.reload();
    await expect(page.getByText("异常历史数据")).toBeVisible();
    await page.getByTestId(`open-run-${failedRun.id}`).click();
    await expect(page.getByText("worker unavailable: Redis connection refused")).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/status=failed/);
    await expect(page.getByText("异常历史数据")).toBeVisible();
  });

  test("数据、benchmark、QA 和 worker 故障原因不会被吞掉", async ({ page }) => {
    const account = {
      id: "recovery-paper", shadow_session_id: "retired", name: "恢复检查账户", status: "error",
      market_scope: "china", base_currency: "CNY", initial_cash: "1000000", benchmark_symbol: "000300",
      current_generation: 1, total_equity: "1000000", health_status: "degraded",
      automation_status: "error", last_run_status: "failed", last_failure_code: "data_missing",
      last_failure_detail: "data missing · benchmark missing · QA critical · Redis unavailable",
      created_at: "", updated_at: ""
    };
    await page.route(/^https?:\/\/[^/]+\/api\/.*$/, async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/paper/accounts") return route.fulfill({ json: { items: [account], count: 1, limit: 50, offset: 0, dataTrust: { valuationTrusted: true, reason: null } } });
      if (url.pathname === "/api/paper/accounts/recovery-paper/overview") {
        return route.fulfill({
          json: {
            account,
            deployment: null,
            latestCycle: {
              id: "failed-cycle", paper_account_id: account.id, deployment_id: "missing", trading_date: "2026-07-27",
              status: "failed", signal_count: 0, intent_count: 0, order_count: 0, fill_count: 0, rejected_count: 0,
              failure_code: "data_missing", failure_detail: account.last_failure_detail
            },
            dataReadiness: { watermark: null, qa: { severity: "critical" } },
            dataTrust: { valuationTrusted: true, reason: null }
          }
        });
      }
      if (url.pathname.endsWith("/positions")) return route.fulfill({ json: { items: [], count: 0, limit: 50, offset: 0 } });
      if (url.pathname.endsWith("/performance")) return route.fulfill({ json: { points: [] } });
      return route.fulfill({ json: {} });
    });

    await page.goto("/#/paper");
    await expect(page.getByText(account.last_failure_detail).first()).toBeVisible();
    await page.getByRole("link", { name: account.name }).click();
    await expect(page.getByText(account.last_failure_detail).first()).toBeVisible();
    await expect(page.locator(".app-content")).not.toBeEmpty();
  });
});
