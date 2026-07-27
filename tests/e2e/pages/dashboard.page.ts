import { expect, Page } from "@playwright/test";

import { BasePage } from "./base.page";

export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async open() {
    await this.gotoHash("/");
    await this.expectHeading("Dashboard");
  }

  async expectShellNavigation() {
    for (const item of [
      "概览",
      "项目",
      "数据",
      "研究",
      "回测",
      "优化",
      "报告",
      "模拟交易",
      "洞察",
      "任务",
      "监控",
      "文档",
      "设置"
    ]) {
      await expect(this.page.getByRole("link", { name: item, exact: true })).toBeVisible();
    }
  }

  async navigateTo(label: string, heading: string | RegExp) {
    await this.page.getByRole("link", { name: label, exact: true }).click();
    await this.expectHeading(heading);
  }
}
