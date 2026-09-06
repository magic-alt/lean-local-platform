import fs from "node:fs";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";

import {
  apiPort,
  apiURL,
  backendDir,
  e2eComposeEnvironment,
  e2eLeanDataDir,
  e2eServiceEnvironment,
  ensureE2EDirs,
  postgresPort,
  rabbitmqPort,
  repoRoot,
  reportPath
} from "./utils/env";

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

function pythonExecutable() {
  if (process.env.E2E_PYTHON) return process.env.E2E_PYTHON;
  return path.join(
    backendDir,
    process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"
  );
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
    postgresPort,
    rabbitmqPort,
    stackStarted,
    node: node.stdout.trim() || node.stderr.trim(),
    npm: npm.stdout.trim() || npm.stderr.trim(),
    docker: docker.stdout.trim() || docker.stderr.trim(),
    dependencyHealth
  }, null, 2), "utf-8");
}

async function globalSetup() {
  ensureE2EDirs();
  if (process.env.E2E_UI_ONLY === "1") {
    fs.writeFileSync(reportPath("environment.json"), JSON.stringify({
      uiOnly: true,
      stackStarted: false,
      baseURL: process.env.PW_BASE_URL || "http://127.0.0.1:15173"
    }, null, 2), "utf-8");
    return;
  }
  if (process.env.E2E_REAL_LOCAL_DATA === "1" && process.env.E2E_SKIP_SEED !== "1") {
    throw new Error("Real local data E2E is read-only: set E2E_SKIP_SEED=1 when E2E_REAL_LOCAL_DATA=1.");
  }

  stopPreviousLocalProcesses();
  const composeEnv = e2eComposeEnvironment();
  const serviceEnv = e2eServiceEnvironment();
  const shouldStartStack = process.env.E2E_START_STACK !== "0";
  const backendMode = process.env.E2E_BACKEND_MODE || "local";
  const startedProcesses: Array<{ name: string; pid: number | undefined; command: string }> = [];
  const python = pythonExecutable();

  if (shouldStartStack && backendMode === "compose") {
    const composeArgs = ["compose", "--profile", "app", "up", "-d", "--wait"];
    if (process.env.E2E_COMPOSE_BUILD !== "0") composeArgs.push("--build");
    composeArgs.push(
      "postgres",
      "rabbitmq",
      "postgres-init",
      "migration",
      "api",
      "worker",
      "data-worker",
      "data-lineage-worker",
      "data-demand-worker",
      "backtest-worker"
    );
    run("docker", composeArgs, { cwd: repoRoot, env: composeEnv });
  } else if (shouldStartStack) {
    run("docker", ["compose", "up", "-d", "--wait", "postgres", "rabbitmq"], {
      cwd: repoRoot,
      env: composeEnv
    });
    run(python, [path.join(repoRoot, "scripts/init_postgres_databases.py")], {
      cwd: repoRoot,
      env: serviceEnv
    });
    run(python, [path.join(repoRoot, "scripts/db_migrate.py"), "apply", "--json"], {
      cwd: repoRoot,
      env: serviceEnv
    });
    startedProcesses.push(startProcess(
      "api",
      python,
      ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", apiPort],
      serviceEnv
    ));
    startedProcesses.push(startProcess(
      "worker",
      python,
      [
        "-m", "celery", "-A", "app.tasks.celery_app:celery_app", "worker",
        "--loglevel=info", "--pool=solo",
        "--queues=default,data-bulk,data-lineage,data-demand,backtest",
        "--hostname=e2e@%h"
      ],
      serviceEnv
    ));
    fs.writeFileSync(reportPath("processes.json"), JSON.stringify(startedProcesses, null, 2), "utf-8");
  }

  await waitForHealth();
  if (process.env.E2E_SKIP_SEED !== "1") {
    run(python, [path.join(repoRoot, "tests/e2e/fixtures/seed_e2e_data.py")], {
      cwd: repoRoot,
      env: {
        ...serviceEnv,
        PYTHONPATH: path.join(repoRoot, "web/backend")
      }
    });
  }
  await writeEnvironmentReport(shouldStartStack);
}

export default globalSetup;
