import fs from "node:fs";
import path from "node:path";

export const repoRoot = path.resolve(process.cwd(), "../..");
export const frontendDir = path.join(repoRoot, "web/frontend");
export const backendDir = path.join(repoRoot, "web/backend");
export const e2eRoot = path.join(repoRoot, "tests/e2e");
export const reportsDir = path.join(e2eRoot, "reports");
export const artifactsDir = path.join(reportsDir, "artifacts");
export const e2eLeanDataDir = process.env.E2E_LEAN_DATA_DIR || path.join(repoRoot, "web/runtime/e2e-lean-data");
export const e2eRuntimeDir = process.env.E2E_RUNTIME_DIR || path.join(repoRoot, "web/runtime/e2e-runtime");

export const apiPort = process.env.E2E_API_PORT || "18080";
export const frontendPort = process.env.E2E_FRONTEND_PORT || process.env.PW_BASE_PORT || "15173";
export const postgresPort = process.env.E2E_POSTGRES_PORT || "15432";
export const rabbitmqPort = process.env.E2E_RABBITMQ_PORT || "15673";
export const rabbitmqManagementPort = process.env.E2E_RABBITMQ_MANAGEMENT_PORT || "15674";
export const apiURL = process.env.E2E_API_URL || `http://127.0.0.1:${apiPort}`;
export const frontendURL = process.env.E2E_FRONTEND_URL || `http://127.0.0.1:${frontendPort}`;

const postgresAdminPassword = process.env.E2E_POSTGRES_ADMIN_PASSWORD || "lean_e2e_admin";
const postgresAppPassword = process.env.E2E_POSTGRES_APP_PASSWORD || "lean_e2e_app";
const postgresCeleryPassword = process.env.E2E_POSTGRES_CELERY_PASSWORD || "lean_e2e_celery";
const postgresMlflowPassword = process.env.E2E_POSTGRES_MLFLOW_PASSWORD || "lean_e2e_mlflow";
const rabbitmqPassword = process.env.E2E_RABBITMQ_PASSWORD || "lean_e2e_rabbitmq";

function encoded(value: string) {
  return encodeURIComponent(value);
}

export function e2eComposeEnvironment(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    COMPOSE_PROJECT_NAME: process.env.COMPOSE_PROJECT_NAME || "lean-e2e",
    LEAN_POSTGRES_PORT: postgresPort,
    LEAN_RABBITMQ_PORT: rabbitmqPort,
    LEAN_RABBITMQ_MANAGEMENT_PORT: rabbitmqManagementPort,
    LEAN_POSTGRES_ADMIN_PASSWORD: postgresAdminPassword,
    LEAN_POSTGRES_APP_PASSWORD: postgresAppPassword,
    LEAN_POSTGRES_CELERY_PASSWORD: postgresCeleryPassword,
    LEAN_POSTGRES_MLFLOW_PASSWORD: postgresMlflowPassword,
    LEAN_RABBITMQ_PASSWORD: rabbitmqPassword,
    LEAN_DEPLOYMENT_PROFILE: "dev",
    LEAN_API_PORT: apiPort,
    LEAN_API_AUTH_REQUIRED: "0",
    CLICKHOUSE_ENABLED: "0",
    LEAN_HOST_DATA_DIR: e2eLeanDataDir,
    LEAN_HOST_PARQUET_DIR: path.join(e2eLeanDataDir, "output/parquet")
  };
}

export function e2eServiceEnvironment(): NodeJS.ProcessEnv {
  return {
    ...e2eComposeEnvironment(),
    LEAN_DEPLOYMENT_MODE: "native",
    LEAN_EXECUTION_BACKEND: "docker",
    LEAN_BACKTEST_EXECUTION_DELEGATED: "0",
    LEAN_POSTGRES_ADMIN_URL: process.env.E2E_POSTGRES_ADMIN_URL
      || `postgresql://postgres:${encoded(postgresAdminPassword)}@127.0.0.1:${postgresPort}/postgres`,
    LEAN_DATABASE_URL: process.env.E2E_DATABASE_URL
      || `postgresql+psycopg://lean_app:${encoded(postgresAppPassword)}@127.0.0.1:${postgresPort}/lean_platform`,
    CELERY_BROKER_URL: process.env.E2E_CELERY_BROKER_URL
      || `amqp://lean_worker:${encoded(rabbitmqPassword)}@127.0.0.1:${rabbitmqPort}/lean`,
    CELERY_RESULT_BACKEND: process.env.E2E_CELERY_RESULT_BACKEND
      || `db+postgresql+psycopg://lean_celery:${encoded(postgresCeleryPassword)}@127.0.0.1:${postgresPort}/lean_celery`,
    LEAN_MLFLOW_DATABASE_URL: process.env.E2E_MLFLOW_DATABASE_URL
      || `postgresql+psycopg://lean_mlflow:${encoded(postgresMlflowPassword)}@127.0.0.1:${postgresPort}/lean_mlflow`,
    LEAN_DATA_DIR: e2eLeanDataDir,
    LEAN_MARKET_DATA_DIR: e2eLeanDataDir,
    LEAN_PARQUET_DIR: path.join(e2eLeanDataDir, "output/parquet"),
    LEAN_RUNTIME_DIR: e2eRuntimeDir,
    LEAN_FILE_OBJECT_STORE_DIR: path.join(e2eRuntimeDir, "object-store"),
    LEAN_SCHEDULED_AUTOMATION_ENABLED: "0",
    LEAN_API_AUTH_REQUIRED: "0",
    CLICKHOUSE_ENABLED: "0"
  };
}

export function ensureE2EDirs() {
  for (const dir of [reportsDir, artifactsDir, e2eLeanDataDir, e2eRuntimeDir]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

export function reportPath(name: string) {
  ensureE2EDirs();
  return path.join(reportsDir, name);
}
