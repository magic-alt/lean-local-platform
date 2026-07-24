import fs from "node:fs";
import path from "node:path";

import { APIRequestContext, expect } from "@playwright/test";

import { apiURL, repoRoot } from "./env";

export type RunStatus = "created" | "queued" | "running" | "success" | "succeeded" | "failed" | "cancelled" | "interrupted";

export interface ProjectRecord {
  id: string;
  name: string;
  main_file: string;
  config?: Record<string, unknown>;
}

export interface BacktestRecord {
  id: string;
  name?: string | null;
  symbol: string;
  status: RunStatus;
  parameters: Record<string, unknown>;
  statistics?: Record<string, unknown> | null;
  result_json_path?: string | null;
  report_html_path?: string | null;
  error?: string | null;
  error_message?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  artifacts?: string[];
}

export interface BacktestResultPayload {
  job: BacktestRecord;
  result: {
    summary_metrics: Record<string, unknown>;
    equity_curve: Array<{ time: string; value: number }>;
    drawdown_curve: Array<{ time: string; value: number }>;
    orders: Array<Record<string, unknown>>;
    trades: Array<Record<string, unknown>>;
    holdings: Array<Record<string, unknown>>;
    statistics: Record<string, unknown>;
  };
}

function apiHeaders(): Record<string, string> {
  const configured = process.env.E2E_API_TOKEN?.trim();
  const tokenFile = process.env.E2E_API_TOKEN_FILE ||
    path.join(repoRoot, "web/runtime/secrets/api_token");
  let token = configured || "";
  if (!token) {
    try {
      token = fs.readFileSync(tokenFile, "utf-8").trim();
    } catch {
      // Authentication may intentionally be disabled in the isolated E2E lane.
    }
  }
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`${apiURL}${path}`, { headers: apiHeaders() });
  expect(response.ok(), `${path} returned ${response.status()}: ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}

export async function apiPost<T>(request: APIRequestContext, path: string, body: unknown): Promise<T> {
  const response = await request.post(`${apiURL}${path}`, { data: body, headers: apiHeaders() });
  expect(response.ok(), `${path} returned ${response.status()}: ${await response.text()}`).toBeTruthy();
  return response.json() as Promise<T>;
}

export async function ensureE2EProject(request: APIRequestContext, overrides?: Partial<{
  name: string;
  templateKey: string;
  market: string;
  assetClass: string;
  venue: string;
  resolution: string;
  dataType: string;
}>): Promise<ProjectRecord> {
  const name = overrides?.name || "E2E_MA_Cross_Test";
  const existing = await apiGet<ProjectRecord[]>(request, "/api/projects");
  const found = existing.find((project) => project.name === name);
  if (found) return found;
  return apiPost<ProjectRecord>(request, "/api/projects", {
    name,
    language: "Python",
    templateKey: overrides?.templateKey || "sma_cross",
    assetClass: overrides?.assetClass || "equity",
    market: overrides?.market || "usa",
    venue: overrides?.venue || overrides?.market || "usa",
    resolution: overrides?.resolution || "daily",
    dataType: overrides?.dataType || "trade",
    parameters: {
      fast: 20,
      slow: 50
    }
  });
}

export async function listBacktests(request: APIRequestContext): Promise<BacktestRecord[]> {
  return apiGet<BacktestRecord[]>(request, "/api/backtests");
}

export async function getBacktest(request: APIRequestContext, id: string): Promise<BacktestRecord> {
  return apiGet<BacktestRecord>(request, `/api/backtests/${encodeURIComponent(id)}`);
}
