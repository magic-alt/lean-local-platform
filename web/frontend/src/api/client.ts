export function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export class ApiError extends Error {
  status: number;
  path: string;
  errorCode?: string;
  traceId?: string;
  workflowId?: string;
  details?: unknown;

  constructor(message: string, status: number, path: string, metadata?: {
    errorCode?: string;
    traceId?: string;
    workflowId?: string;
    details?: unknown;
  }) {
    const traceSuffix = metadata?.traceId ? ` (Trace: ${metadata.traceId})` : "";
    super(`${message}${traceSuffix}`);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.errorCode = metadata?.errorCode;
    this.traceId = metadata?.traceId;
    this.workflowId = metadata?.workflowId;
    this.details = metadata?.details;
  }
}

function validationDetailSummary(details: unknown): string | undefined {
  if (!Array.isArray(details)) return undefined;
  const issues = details
    .slice(0, 3)
    .map((item) => {
      if (!item || typeof item !== "object") return undefined;
      const issue = item as Record<string, unknown>;
      const message = typeof issue.msg === "string" ? issue.msg : undefined;
      if (!message) return undefined;
      const location = Array.isArray(issue.loc)
        ? issue.loc
            .filter((part) => part !== "body")
            .map(String)
            .join(".")
        : "";
      return location ? `${location}: ${message}` : message;
    })
    .filter((item): item is string => Boolean(item));
  return issues.length ? issues.join("; ") : undefined;
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = String(options?.method || "GET").toUpperCase();
  const headers = new Headers(options?.headers);
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers.has("Idempotency-Key")) {
    headers.set(
      "Idempotency-Key",
      globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
    );
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let message = response.statusText;
    let errorCode: string | undefined;
    let traceId = response.headers.get("X-Trace-ID") ?? undefined;
    let workflowId = response.headers.get("X-Workflow-ID") ?? undefined;
    let details: unknown;
    try {
      const body = await response.json();
      const detail = body.detail;
      message = typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : message;
      errorCode = typeof body.error_code === "string" ? body.error_code : undefined;
      traceId = typeof body.trace_id === "string" ? body.trace_id : traceId;
      workflowId = typeof body.workflow_id === "string" ? body.workflow_id : workflowId;
      details = body.details;
      const validationSummary = errorCode === "VALIDATION_ERROR"
        ? validationDetailSummary(details)
        : undefined;
      if (validationSummary) message = `${message} ${validationSummary}`;
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new ApiError(message, response.status, path, { errorCode, traceId, workflowId, details });
  }
  return response.json() as Promise<T>;
}
