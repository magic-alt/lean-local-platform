import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

import { apiPort, apiURL, backendDir, e2eLeanDataDir, ensureE2EDirs, repoRoot, reportPath } from "./utils/env";

function run(command: string, args: string[], options: { cwd?: string; env?: NodeJS.ProcessEnv; allowFailure?: boolean } = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? repoRoot,
    env: options.env ?? process.env,
    encoding: "utf-8",
    stdio: "pipe"
  });
  if (result.status !== 0 && !options.allowFailure) {
    throw new Error([
      `Command failed: ${command} ${args.join(" ")}`,
      result.stdout,
      result.stderr
    ].filter(Boolean).join("\n"));
  }
  return result;
}

function startProcess(name: string, command: string, args: string[], env: NodeJS.ProcessEnv) {
  const stdout = fs.openSync(reportPath(`${name}.log`), "a");
  const stderr = fs.openSync(reportPath(`${name}.err.log`), "a");
  const child = spawn(command, args, {
    cwd: backendDir,
    env,
    detached: true,
    stdio: ["ignore", stdout, stderr]
  });
  child.unref();
  return { name, pid: child.pid, command: [command, ...args].join(" ") };
}

function stopPreviousLocalProcesses() {
  const processFile = reportPath("processes.json");
  if (!fs.existsSync(processFile)) return;
  const processes = JSON.parse(fs.readFileSync(processFile, "utf-8")) as Array<{ pid?: number }>;
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
  fs.rmSync(processFile, { force: true });
}

async function waitForHealth(timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiURL}/api/health`);
      if (response.ok) return;
      lastError = `${response.status} ${await response.text()}`;
    } catch (error) {
      lastError = (error as Error).message;
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(`API health did not become ready at ${apiURL}/api/health: ${lastError}`);
}

async function writeEnvironmentReport(stackStarted: boolean) {
  const node = run("node", ["--version"], { allowFailure: true });
  const npm = run("npm", ["--version"], { cwd: path.join(repoRoot, "web/frontend"), allowFailure: true });
  const docker = run("docker", ["version", "--format", "{{.Server.Version}}"], { allowFailure: true });
  let dependencyHealth: unknown = null;
  try {
    const response = await fetch(`${apiURL}/api/health/dependencies`);
    dependencyHealth = await response.json();
  } catch (error) {
    dependencyHealth = { error: (error as Error).message };
  }
  fs.writeFileSync(reportPath("environment.json"), JSON.stringify({
    apiURL,
    e2eLeanDataDir,
    stackStarted,
    node: node.stdout.trim() || node.stderr.trim(),
    npm: npm.stdout.trim() || npm.stderr.trim(),
    docker: docker.stdout.trim() || docker.stderr.trim(),
    dependencyHealth
  }, null, 2), "utf-8");
}

async function globalSetup() {
  ensureE2EDirs();
  stopPreviousLocalProcesses();
  const composeEnv = {
    ...process.env,
    COMPOSE_PROJECT_NAME: process.env.COMPOSE_PROJECT_NAME || "lean-e2e",
    LEAN_API_PORT: process.env.E2E_API_PORT || "18080",
    LEAN_MYSQL_PORT: process.env.E2E_MYSQL_PORT || "13306",
    LEAN_REDIS_PORT: process.env.E2E_REDIS_PORT || "16379",
    LEAN_CLICKHOUSE_HTTP_PORT: process.env.E2E_CLICKHOUSE_HTTP_PORT || "18123",
    LEAN_CLICKHOUSE_NATIVE_PORT: process.env.E2E_CLICKHOUSE_NATIVE_PORT || "19000",
    LEAN_DATA_DIR: e2eLeanDataDir,
    LEAN_HOST_DATA_DIR: e2eLeanDataDir,
    LEAN_HOST_PLATFORM_DIR: repoRoot,
    LEAN_HOST_PARQUET_DIR: path.join(e2eLeanDataDir, "parquet")
  };
  const shouldStartStack = process.env.E2E_START_STACK !== "0";
  const backendMode = process.env.E2E_BACKEND_MODE || "local";
  const startedProcesses: Array<{ name: string; pid: number | undefined; command: string }> = [];
  const serviceEnv = {
    ...composeEnv,
    REDIS_URL: `redis://127.0.0.1:${composeEnv.LEAN_REDIS_PORT}/0`,
    LEAN_DATABASE_URL: process.env.LEAN_DATABASE_URL ||
      `mysql+pymysql://lean:lean@127.0.0.1:${composeEnv.LEAN_MYSQL_PORT}/lean_market`,
    CLICKHOUSE_HOST: "127.0.0.1",
    CLICKHOUSE_PORT: composeEnv.LEAN_CLICKHOUSE_HTTP_PORT,
    CLICKHOUSE_USERNAME: "lean",
    CLICKHOUSE_PASSWORD: "lean",
    CLICKHOUSE_DATABASE: "lean_market",
    LEAN_DATA_DIR: e2eLeanDataDir,
    LEAN_HOST_DATA_DIR: e2eLeanDataDir,
    LEAN_HOST_PLATFORM_DIR: repoRoot,
    LEAN_HOST_PARQUET_DIR: path.join(e2eLeanDataDir, "parquet")
  };
  if (shouldStartStack && backendMode === "compose") {
    const composeArgs = ["compose", "--profile", "app", "up", "-d"];
    if (process.env.E2E_COMPOSE_BUILD !== "0") composeArgs.push("--build");
    composeArgs.push("mysql", "redis", "clickhouse", "api", "worker");
    run("docker", composeArgs, { cwd: repoRoot, env: composeEnv });
  } else if (shouldStartStack) {
    run("docker", ["compose", "up", "-d", "--wait", "mysql", "redis", "clickhouse"], { cwd: repoRoot, env: composeEnv });
    const python = process.env.E2E_PYTHON || path.join(backendDir, ".venv/bin/python");
    startedProcesses.push(startProcess("api", python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", apiPort], serviceEnv));
    startedProcesses.push(startProcess("worker", python, ["-m", "celery", "-A", "app.tasks.celery_app", "worker", "--loglevel=info", "--pool=solo"], serviceEnv));
    fs.writeFileSync(reportPath("processes.json"), JSON.stringify(startedProcesses, null, 2), "utf-8");
  }
  await waitForHealth();
  if (process.env.E2E_SKIP_SEED !== "1") {
    const python = process.env.E2E_PYTHON || path.join(repoRoot, "web/backend/.venv/bin/python");
    run(python, [path.join(repoRoot, "tests/e2e/fixtures/seed_e2e_data.py")], {
      cwd: repoRoot,
      env: {
        ...serviceEnv,
        PYTHONPATH: path.join(repoRoot, "web/backend"),
      }
    });
  }
  await writeEnvironmentReport(shouldStartStack);
}

export default globalSetup;
