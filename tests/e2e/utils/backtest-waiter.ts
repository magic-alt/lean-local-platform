import { APIRequestContext, expect, Page } from "@playwright/test";

import { BacktestRecord, getBacktest, RunStatus } from "./api";

const TERMINAL_STATUSES = new Set<RunStatus>(["success", "succeeded", "failed", "cancelled", "interrupted"]);
const ACTIVE_STATUSES = new Set<RunStatus>(["created", "queued", "running"]);

export interface BacktestWaitResult {
  final: BacktestRecord;
  statuses: RunStatus[];
  sawRunning: boolean;
}

export async function waitForBacktestTerminal(
  request: APIRequestContext,
  runId: string,
  options: { timeoutMs?: number; pollMs?: number; requireRunningState?: boolean } = {}
): Promise<BacktestWaitResult> {
  const timeoutMs = options.timeoutMs ?? 15 * 60_000;
  const pollMs = options.pollMs ?? 2_000;
  const deadline = Date.now() + timeoutMs;
  const statuses: RunStatus[] = [];
  let final = await getBacktest(request, runId);
  while (Date.now() < deadline) {
    final = await getBacktest(request, runId);
    statuses.push(final.status);
    if (TERMINAL_STATUSES.has(final.status)) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  expect(TERMINAL_STATUSES.has(final.status), `run ${runId} statuses: ${statuses.join(" -> ")}`).toBeTruthy();
  const sawRunning = statuses.some((status) => ACTIVE_STATUSES.has(status));
  if (options.requireRunningState) {
    expect(sawRunning, `run ${runId} should expose created/queued/running before terminal status`).toBeTruthy();
  }
  return { final, statuses, sawRunning };
}

export async function waitForResultPageStatus(
  page: Page,
  expected: RegExp,
  options: { timeoutMs?: number } = {}
) {
  await expect(page.getByTestId("run-status")).toContainText(expected, { timeout: options.timeoutMs ?? 15 * 60_000 });
}

export function isSuccessfulStatus(status: RunStatus) {
  return status === "success" || status === "succeeded";
}
