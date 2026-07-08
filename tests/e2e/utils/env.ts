import fs from "node:fs";
import path from "node:path";

export const repoRoot = path.resolve(process.cwd(), "../..");
export const frontendDir = path.join(repoRoot, "web/frontend");
export const backendDir = path.join(repoRoot, "web/backend");
export const e2eRoot = path.join(repoRoot, "tests/e2e");
export const reportsDir = path.join(e2eRoot, "reports");
export const artifactsDir = path.join(reportsDir, "artifacts");
export const e2eLeanDataDir = process.env.E2E_LEAN_DATA_DIR || path.join(repoRoot, "web/runtime/e2e-lean-data");

export const apiPort = process.env.E2E_API_PORT || "18080";
export const frontendPort = process.env.E2E_FRONTEND_PORT || process.env.PW_BASE_PORT || "15173";
export const apiURL = process.env.E2E_API_URL || `http://127.0.0.1:${apiPort}`;
export const frontendURL = process.env.E2E_FRONTEND_URL || `http://127.0.0.1:${frontendPort}`;

export function ensureE2EDirs() {
  for (const dir of [reportsDir, artifactsDir, e2eLeanDataDir]) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

export function reportPath(name: string) {
  ensureE2EDirs();
  return path.join(reportsDir, name);
}
