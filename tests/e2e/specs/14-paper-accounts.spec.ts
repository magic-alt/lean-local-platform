import { expect, test } from "@playwright/test";

import { attachFrontendGuards } from "../fixtures/console";


type Account = {
  id: string;
  shadow_session_id: string;
  name: string;
  status: string;
  market_scope: "china";
  base_currency: "CNY";
  initial_cash: string;
  benchmark_symbol: string;
  current_generation: number;
  cash: string;
  available_cash: string;
  market_value: string;
  total_equity: string;
  daily_pnl: string;
  cumulative_return: string;
  benchmark_return: string;
  excess_return: string;
  position_count: number;
  health_status: string;
  created_at: string;
  updated_at: string;
};


test.describe("14 Paper multi-account brokerage workspace @paper @responsive", () => {
  test("creates, switches, inspects, automates and compares isolated accounts", async ({ page }, testInfo) => {
    const assertNoFrontendErrors = attachFrontendGuards(
      page,
      testInfo,
      [/Failed to load resource: the server responded with a status of 422/]
    );
    const accounts: Account[] = [];
    const deployments = new Map<string, Array<Record<string, unknown>>>();
    let nextAccount = 1;

    await page.route("**/api/paper/accounts?*", async (route) => {
      await route.fulfill({ json: { items: accounts, count: accounts.length, limit: 50, offset: 0 } });
    });
    await page.route("**/api/projects", async (route) => {
      await route.fulfill({ json: [{ id: "project-1", name: "E2E Paper Strategy", display_name: "E2E Paper Strategy" }] });
    });
    await page.route("**/api/health/dependencies", async (route) => {
      await route.fulfill({
        json: {
          status: "ok",
          dependencies: [{ service: "backtest_worker", ok: true, detail: "e2e" }],
          urls: { prometheus: "", grafana: "" }
        }
      });
    });
    await page.route("**/api/paper/candidates?*", async (route) => {
      await route.fulfill({
        json: [{
          id: "backtest-1",
          name: "Certified Frozen Candidate",
          symbol: "510300",
          start: "2024-01-01",
          end: "2024-06-30",
          cash: 1000000,
          strategyVersionId: "strategy-v1",
          parameterHash: "parameter-fingerprint",
          admissionStage: "paper",
          validation: { passed: true }
        }]
      });
    });
    await page.route("**/api/paper/accounts", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      const payload = route.request().postDataJSON();
      const id = `account-${nextAccount++}`;
      const fallbackName = id === "account-1" ? "E2E Account A" : "E2E Account B";
      const fallbackCash = id === "account-1" ? "1000000" : "2500000";
      const account: Account = {
        id,
        shadow_session_id: `session-${id}`,
        name: payload.name || fallbackName,
        status: "draft",
        market_scope: "china",
        base_currency: "CNY",
        initial_cash: String(payload.initialCash || fallbackCash),
        benchmark_symbol: payload.benchmarkSymbol,
        current_generation: 1,
        cash: String(payload.initialCash || fallbackCash),
        available_cash: String(payload.initialCash || fallbackCash),
        market_value: "0",
        total_equity: String(payload.initialCash || fallbackCash),
        daily_pnl: "0",
        cumulative_return: "0",
        benchmark_return: "0",
        excess_return: "0",
        position_count: 0,
        health_status: "healthy",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      accounts.push(account);
      await route.fulfill({ status: 201, json: account });
    });
    await page.route(/\/api\/paper\/accounts\/account-\d+\/deployments$/, async (route) => {
      const accountId = route.request().url().match(/accounts\/(account-\d+)/)?.[1] || "";
      if (route.request().method() === "POST") {
        const payload = route.request().postDataJSON();
        const deployment = {
          id: `deployment-${accountId}`,
          paper_account_id: accountId,
          version: 1,
          name: payload.name,
          status: "active",
          is_primary: 1,
          project_id: payload.projectId,
          source_backtest_id: payload.sourceBacktestId,
          project_snapshot_id: "snapshot-v1",
          dataset_version_id: "dataset-v1",
          schedule_type: "market_daily",
          schedule_expression: "after_close+00:45",
          market_timezone: "Asia/Shanghai",
          execution_timing: "next_open",
          signal_mode: "paper_execute",
          strategy_fingerprint: "strategy-fingerprint",
          dataset_fingerprint: "dataset-fingerprint",
          deployment_fingerprint: "deployment-fingerprint",
          consecutive_failures: 0
        };
        deployments.set(accountId, [deployment]);
        await route.fulfill({ status: 201, json: deployment });
      } else {
        await route.fulfill({ json: deployments.get(accountId) || [] });
      }
    });
    await page.route(/\/api\/paper\/accounts\/account-\d+\/activate$/, async (route) => {
      const accountId = route.request().url().match(/accounts\/(account-\d+)/)?.[1];
      const account = accounts.find((item) => item.id === accountId)!;
      account.status = "active";
      await route.fulfill({ json: account });
    });

    await page.goto("/#/paper");
    await expect(page.getByRole("heading", { name: "Paper Accounts" })).toBeVisible();

    for (const [name, cash] of [["E2E Account A", "1000000"], ["E2E Account B", "2500000"]] as const) {
      await page.getByRole("button", { name: "新建模拟账户" }).click();
      await page.getByLabel("账户名称").fill(name);
      await page.getByLabel("初始资金").fill(cash);
      await page.getByRole("button", { name: "下一步" }).click();
      await page.getByLabel("Project").click();
      await page.getByText("E2E Paper Strategy", { exact: true }).click();
      await page.getByLabel("可信 Backtest Candidate").click();
      await page.getByText(/Certified Frozen Candidate/).click();
      await page.getByRole("button", { name: "下一步" }).click();
      await page.getByRole("button", { name: "下一步" }).click();
      await page.getByRole("button", { name: "下一步" }).click();
      await page.getByRole("button", { name: "创建并冻结" }).click();
      await expect(page.getByText(name)).toBeVisible();
    }

    await page.getByRole("checkbox").nth(0).check();
    await page.getByRole("checkbox").nth(1).check();
    await page.route("**/api/paper/accounts/compare?*", async (route) => {
      await route.fulfill({
        json: {
          comparable: true,
          currencies: ["CNY"],
          comparisonStart: "2024-07-01",
          valuationDate: "2024-07-05",
          missingData: [],
          accounts: accounts.map((account) => ({
            accountId: account.id,
            name: account.name,
            currency: "CNY",
            benchmarkSymbol: "000300",
            cumulativeReturn: account.id === "account-1" ? "0.02" : "0",
            benchmarkReturn: "0.01",
            excessReturn: account.id === "account-1" ? "0.01" : "-0.01",
            turnover: "0.1",
            tradeCount: account.id === "account-1" ? 2 : 0,
            positionCount: account.id === "account-1" ? 1 : 0,
            riskRejectCount: 1,
            cashRatio: account.id === "account-1" ? "0.7" : "1",
            lastRunDate: "2024-07-05"
          }))
        }
      });
    });
    await page.getByRole("button", { name: /比较 2/ }).click();
    await expect(page.getByRole("dialog").getByText("2.00%")).toBeVisible();
    await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();

    const account = accounts[0];
    account.market_value = "300000";
    account.total_equity = "1020000";
    account.cumulative_return = "0.02";
    account.position_count = 1;
    await page.route("**/api/paper/accounts/account-1/overview", async (route) => {
      await route.fulfill({
        json: {
          account,
          deployment: deployments.get("account-1")?.[0],
          latestCycle: {
            id: "cycle-1",
            paper_account_id: "account-1",
            deployment_id: "deployment-account-1",
            trading_date: "2024-07-05",
            status: "succeeded",
            signal_count: 1,
            intent_count: 1,
            order_count: 1,
            fill_count: 1,
            rejected_count: 0
          }
        }
      });
    });
    await page.route("**/api/paper/accounts/account-1/positions", async (route) => {
      await route.fulfill({
        json: {
          items: [{
            paper_account_id: "account-1",
            symbol: "510300",
            security_name: "沪深300ETF",
            market: "china",
            quantity: "10000",
            sellable_quantity: "10000",
            frozen_quantity: "0",
            average_cost: "3.8",
            certified_price: "4.0",
            market_value: "40000",
            account_weight: "0.039",
            daily_pnl: "500",
            unrealized_pnl: "2000",
            realized_pnl: "0",
            quote_data_timestamp: "2024-07-05",
            data_status: "certified_close"
          }],
          count: 1,
          limit: 50,
          offset: 0
        }
      });
    });
    await page.route("**/api/paper/accounts/account-1/orders", async (route) => {
      await route.fulfill({ json: { items: [{ id: "order-1", symbol: "510300", side: "buy", status: "FILLED" }], count: 1, limit: 50, offset: 0 } });
    });
    await page.route("**/api/paper/accounts/account-1/trades", async (route) => {
      await route.fulfill({ json: { items: [{ id: "fill-1", symbol: "510300", side: "buy", precise_quantity: "10000", precise_price: "4.0" }], count: 1, limit: 50, offset: 0 } });
    });
    await page.route("**/api/paper/accounts/account-1/signals", async (route) => {
      await route.fulfill({
        json: {
          items: [
            { id: "signal-1", paper_account_id: "account-1", deployment_id: "deployment-account-1", cycle_id: "cycle-1", signal_type: "buy", symbol: "510300", signal_timestamp: "2024-07-05T15:01:00+08:00", intended_execution_date: "2024-07-08", disposition: "filled", data_timestamp: "2024-07-05T15:00:00+08:00" },
            { id: "signal-2", paper_account_id: "account-1", deployment_id: "deployment-account-1", cycle_id: "cycle-2", signal_type: "no_signal", signal_timestamp: "2024-07-08T15:01:00+08:00", disposition: "observed", no_trade_reason: "no_signal", data_timestamp: "2024-07-08T15:00:00+08:00" }
          ],
          count: 2,
          limit: 50,
          offset: 0
        }
      });
    });
    await page.route("**/api/paper/accounts/account-1/cycles", async (route) => {
      await route.fulfill({ json: { items: [], count: 0, limit: 50, offset: 0 } });
    });
    await page.route("**/api/paper/accounts/account-1/audit", async (route) => {
      await route.fulfill({ status: 422, json: { detail: "audit projection temporarily unavailable" } });
    });
    await page.route("**/api/paper/accounts/account-1/performance", async (route) => {
      await route.fulfill({ json: { benchmarkSymbol: "000300", currency: "CNY", points: [] } });
    });

    await page.goto("/#/paper/accounts/account-1?tab=positions");
    await expect(page.getByRole("heading", { name: "E2E Account A" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "最新认证价格" })).toBeVisible();
    await page.getByRole("tab", { name: "Signals" }).click();
    await expect(page.getByRole("cell", { name: "no_signal", exact: true }).first()).toBeVisible();
    await page.getByRole("tab", { name: "Audit" }).click();
    await expect(page.getByText("审计 局部加载失败")).toBeVisible();
    await expect(page.locator(".app-content")).not.toBeEmpty();

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/#/paper");
    await expect(page.getByRole("heading", { name: "Paper Accounts" })).toBeVisible();
    await expect(page.locator(".paper-account-card").first()).toBeVisible();
    await assertNoFrontendErrors();
  });
});
