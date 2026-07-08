import fs from "node:fs";
import { spawnSync } from "node:child_process";

import { reportPath, repoRoot } from "./utils/env";

function stopLocalProcesses() {
  const processFile = reportPath("processes.json");
  if (!fs.existsSync(processFile)) return;
  const processes = JSON.parse(fs.readFileSync(processFile, "utf-8")) as Array<{ name: string; pid?: number }>;
  for (const item of processes) {
    if (!item.pid) continue;
    try {
      process.kill(-item.pid, "SIGTERM");
    } catch {
      try {
        process.kill(item.pid, "SIGTERM");
      } catch {
        // Process already exited.
      }
    }
  }
}

async function globalTeardown() {
  if (process.env.E2E_STOP_LOCAL_SERVICES !== "0") {
    stopLocalProcesses();
  }
  fs.writeFileSync(reportPath("teardown.json"), JSON.stringify({
    completedAt: new Date().toISOString(),
    stoppedStack: process.env.E2E_STOP_STACK === "1"
  }, null, 2), "utf-8");
  if (process.env.E2E_STOP_STACK === "1") {
    spawnSync("docker", ["compose", "--profile", "app", "down"], {
      cwd: repoRoot,
      env: {
        ...process.env,
        COMPOSE_PROJECT_NAME: process.env.COMPOSE_PROJECT_NAME || "lean-e2e"
      },
      stdio: "inherit"
    });
  }
}

export default globalTeardown;
