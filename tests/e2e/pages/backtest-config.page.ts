import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export interface BacktestFormValues {
  projectName: string;
  name: string;
  symbol: string;
  market: "usa" | "china" | "hongkong";
  marketLabel: string;
  assetClass: string;
  resolution: string;
  dataType: string;
  start: string;
  end: string;
  cash: number;
  benchmarkSymbol: string;
  feeModel?: string;
  slippageModel?: string;
  source?: string;
  sourceLabel?: string;
  fast?: number;
  slow?: number;
}

export class BacktestConfigPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/backtests");
    await this.expectHeading("Backtests");
    await expect(this.page.getByText("New Backtest")).toBeVisible();
  }

  async fill(values: BacktestFormValues) {
    await this.fillByLabel("Backtest Name", values.name);
    await this.selectByTestId("backtest-project-select", values.projectName);
    await this.selectByTestId("backtest-asset-select", values.assetClass);
    await this.selectByTestId("backtest-market-select", values.marketLabel);
    await this.selectByTestId("backtest-resolution-select", values.resolution);
    await this.selectByTestId("backtest-data-type-select", values.dataType);
    await this.page.getByTestId("backtest-symbol-input").locator("input").fill(values.symbol);
    await this.page.getByTestId("backtest-start-input").fill(values.start);
    await this.page.getByTestId("backtest-end-input").fill(values.end);
    await this.page.getByTestId("backtest-cash-input").fill(String(values.cash));
    await this.page.getByTestId("backtest-benchmark-input").fill(values.benchmarkSymbol);
    if (values.feeModel) await this.selectByTestId("backtest-fee-model-select", values.feeModel);
    if (values.slippageModel) await this.selectByTestId("backtest-slippage-model-select", values.slippageModel);
    if (values.source) {
      if (values.market === "china") {
        await this.selectByTestId("backtest-source-select", values.sourceLabel ?? values.source);
      } else {
        await this.fillByLabel("Data Source", values.source);
      }
    }
    if (values.fast !== undefined) {
      const fast = this.page.getByLabel(/fast/i);
      if (await fast.count()) await fast.fill(String(values.fast));
    }
    if (values.slow !== undefined) {
      const slow = this.page.getByLabel(/slow/i);
      if (await slow.count()) await slow.fill(String(values.slow));
    }
  }

  async runAndCaptureId(): Promise<string> {
    const responsePromise = this.page.waitForResponse((response) =>
      response.url().includes("/api/backtests") &&
      response.request().method() === "POST"
    );
    await this.page.getByTestId("run-backtest-button").click();
    const response = await responsePromise;
    expect(response.ok(), `create backtest returned ${response.status()}: ${await response.text()}`).toBeTruthy();
    const payload = await response.json();
    await expect(this.page).toHaveURL(/#\/runs\//);
    return payload.id as string;
  }

  async expectValidationMessage(message: string | RegExp) {
    await expect(this.page.getByText(message)).toBeVisible();
  }
}
