import { expect, Locator, Page } from "@playwright/test";

export class BasePage {
  constructor(protected readonly page: Page) {}

  async gotoHash(path: string) {
    await this.page.goto(`/#${path}`);
  }

  async expectHeading(name: string | RegExp) {
    await expect(this.page.getByRole("heading", { name })).toBeVisible();
  }

  async selectByLabel(label: string, value: string | RegExp) {
    const field = this.page.getByLabel(label, { exact: true });
    await field.click();
    await this.selectOpenOption(value);
  }

  async selectByTestId(testId: string, value: string) {
    const control = this.page.getByTestId(testId);
    const selected = control.locator(".ant-select-selection-item").first();
    if (await selected.count()) {
      const selectedText = (await selected.textContent() || "").trim();
      if (selectedText.localeCompare(value, undefined, { sensitivity: "accent" }) === 0) return;
    }
    await control.click();
    await this.selectOpenOption(value);
  }

  async fillByLabel(label: string, value: string) {
    await this.page.getByLabel(label, { exact: true }).fill(value);
  }

  async screenshot(name: string) {
    await this.page.screenshot({ path: `../../tests/e2e/reports/artifacts/${name}.png`, fullPage: true });
  }

  protected async expectVisible(locator: Locator) {
    await expect(locator).toBeVisible();
  }

  private async selectOpenOption(value: string | RegExp) {
    const dropdown = this.page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)").last();
    await expect(dropdown).toBeVisible();

    if (typeof value === "string") {
      let searched = false;
      const deadline = Date.now() + 10_000;
      while (Date.now() < deadline) {
        const option = await this.findStringOption(dropdown, value);
        if (option) {
          await this.clickOpenOption(option, dropdown);
          return;
        }
        if (!searched) {
          await this.page.keyboard.type(value);
          searched = true;
        }
        await this.page.waitForTimeout(250);
      }
      throw new Error(`Select option "${value}" was not found`);
    }

    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
      const option = dropdown.locator("[role='option']").filter({ hasText: value });
      if (await option.count()) {
        await this.clickOpenOption(option.first(), dropdown);
        return;
      }
      await this.page.waitForTimeout(250);
    }
    throw new Error(`Select option matching ${value} was not found`);
  }

  private async findStringOption(dropdown: Locator, value: string): Promise<Locator | undefined> {
    const safeValue = value.replace(/"/g, '\\"');
    const ariaExact = dropdown.locator(`[role='option'][aria-label="${safeValue}"]`);
    if (await ariaExact.count()) return ariaExact.first();

    const ariaContains = dropdown.locator(`[role='option'][aria-label*="${safeValue}"]`);
    if (await ariaContains.count()) return ariaContains.first();

    const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const options = dropdown.locator("[role='option']");
    const exactText = options.filter({ hasText: new RegExp(`^\\s*${escaped}\\s*$`, "i") });
    if (await exactText.count()) return exactText.first();

    const partialText = options.filter({ hasText: value });
    if (await partialText.count()) return partialText.first();

    return undefined;
  }

  private async clickOpenOption(option: Locator, dropdown: Locator) {
    await option.scrollIntoViewIfNeeded().catch(() => undefined);
    try {
      await option.click({ force: true, timeout: 2000 });
    } catch {
      await option.dispatchEvent("mousedown", { bubbles: true, cancelable: true, button: 0 });
      await option.dispatchEvent("mouseup", { bubbles: true, cancelable: true, button: 0 });
      await option.dispatchEvent("click", { bubbles: true, cancelable: true, button: 0 });
    }
    await this.closeDropdown(dropdown);
  }

  private async closeDropdown(dropdown: Locator) {
    try {
      await expect(dropdown).toBeHidden({ timeout: 1000 });
    } catch {
      await this.page.keyboard.press("Escape");
      await expect(dropdown).toBeHidden({ timeout: 3000 }).catch(() => undefined);
    }
    await this.page.waitForTimeout(100);
  }
}
