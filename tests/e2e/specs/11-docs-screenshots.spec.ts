import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";


const enabled = process.env.UPDATE_DOC_SCREENSHOTS === "1";
const assetDir = path.resolve(process.cwd(), "../../docs/help/assets");

test.describe("11 documentation screenshots", () => {
  test.skip(!enabled, "Set UPDATE_DOC_SCREENSHOTS=1 to update tracked documentation images.");

  test("capture stable workflow pages with isolated E2E data", async ({ page }) => {
    fs.mkdirSync(assetDir, { recursive: true });
    const pages: Array<[string, string, string]> = [
      ["/#/data", "Data Library", "data-library.png"],
      ["/#/projects", "Projects", "project-editor.png"],
      ["/#/backtests", "Backtests", "backtest-workbench.png"],
      ["/#/optimization", "Optimization", "optimization-workbench.png"],
      ["/#/research", "Research", "research-workspace.png"],
      ["/#/paper", "LEAN Paper", "paper-sessions.png"],
      ["/#/reports", "Reports", "reports-library.png"]
    ];
    for (const [route, heading, filename] of pages) {
      await page.goto(route);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      await page.locator(".app-content").screenshot({ path: path.join(assetDir, filename), animations: "disabled" });
    }
  });
});
