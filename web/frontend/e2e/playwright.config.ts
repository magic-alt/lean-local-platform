import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const port = process.env.E2E_FRONTEND_PORT ?? "15174";
const baseURL = `http://127.0.0.1:${port}`;
const frontendDir = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
  expect: {
    timeout: 10_000
  },
  workers: 1,
  use: {
    baseURL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }
    }
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    cwd: frontendDir,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000
  }
});
