import { expect, Page, TestInfo } from "@playwright/test";

const IGNORED_CONSOLE_PATTERNS = [
  /ResizeObserver loop completed/i,
  /favicon/i,
  /Failed to load resource: the server responded with a status of 404 \(Not Found\)/i,
  /\[antd: Alert\].*deprecated/i,
  /\[antd: Upload\].*value.*fileList/i
];

export function attachFrontendGuards(page: Page, testInfo: TestInfo, expectedConsoleErrors: RegExp[] = []) {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (IGNORED_CONSOLE_PATTERNS.some((pattern) => pattern.test(text))) return;
    if (expectedConsoleErrors.some((pattern) => pattern.test(text))) return;
    consoleErrors.push(text);
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(error.message);
  });
  page.on("response", (response) => {
    if (response.status() >= 500 && !response.url().includes("/api/health/dependencies")) {
      failedRequests.push(`${response.status()} ${response.url()}`);
    }
  });

  testInfo.attach("guarded-front-end", {
    body: "Console/page/network guards enabled.",
    contentType: "text/plain"
  });

  return async () => {
    expect(consoleErrors, `Unexpected console/page errors:\n${consoleErrors.join("\n")}`).toEqual([]);
    expect(failedRequests, `Unexpected HTTP 5xx responses:\n${failedRequests.join("\n")}`).toEqual([]);
  };
}
