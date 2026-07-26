import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = fileURLToPath(new URL(".", import.meta.url));
const repoRoot = path.resolve(frontendDir, "../..");
const e2eRoot = path.join(repoRoot, "tests/e2e");
const basePort = process.env.PW_BASE_PORT ?? process.env.E2E_FRONTEND_PORT ?? "15173";
const apiPort = process.env.E2E_API_PORT ?? "18080";
const baseURL = `http://127.0.0.1:${basePort}`;
const shouldStartServer = process.env.PW_NO_SERVER !== "1";
const apiURL = process.env.E2E_API_URL ?? `http://127.0.0.1:${apiPort}`;

export default defineConfig({
  testDir: path.join(e2eRoot, "specs"),
  globalSetup: path.join(e2eRoot, "global-setup.ts"),
  globalTeardown: path.join(e2eRoot, "global-teardown.ts"),
  timeout: 180_000,
  expect: {
    timeout: 20_000
  },
  retries: process.env.CI ? 1 : 0,
  workers: process.env.E2E_WORKERS ? Number(process.env.E2E_WORKERS) : 1,
  outputDir: path.join(e2eRoot, "reports/artifacts"),
  reporter: [
    ["list"],
    ["html", { outputFolder: path.join(e2eRoot, "reports/html"), open: "never" }],
    ["json", { outputFile: path.join(e2eRoot, "reports/results.json") }]
  ],
  use: {
    baseURL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 60_000
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }
    },
    {
      name: "chromium-1920",
      grep: /@smoke|@responsive/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } }
    },
    {
      name: "chromium-1280",
      grep: /@viewport/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } }
    },
    {
      name: "chromium-tablet",
      grep: /@viewport/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 768, height: 1024 } }
    }
  ],
  webServer: shouldStartServer ? {
    command: `VITE_API_PROXY_TARGET=${apiURL} npm run dev -- --host 127.0.0.1 --port ${basePort} --strictPort`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000
  } : undefined
});
