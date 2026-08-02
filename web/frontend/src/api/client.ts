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

export interface ApiRequestOptions extends RequestInit {
  /** Stable for every HTTP attempt that belongs to one user command. */
  operationId?: string;
  /** Network failures only; HTTP responses are never retried here. */
  networkRetries?: number;
}

export function createOperationId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const pendingOperations = new Map<string, { id: string; createdAt: number }>();
const OPERATION_TTL_MS = 15 * 60 * 1000;

function bodyFingerprint(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `${value.length}:${(hash >>> 0).toString(16)}`;
}

function commandIdentity(method: string, path: string, body: BodyInit | null | undefined): string | undefined {
  if (body == null) return `${method}:${path}`;
  return typeof body === "string" ? `${method}:${path}:${bodyFingerprint(body)}` : undefined;
}

function operationForCommand(identity: string | undefined): string {
  const now = Date.now();
  for (const [key, pending] of pendingOperations) {
    if (now - pending.createdAt > OPERATION_TTL_MS) pendingOperations.delete(key);
  }
  const existing = identity ? pendingOperations.get(identity) : undefined;
  if (existing) return existing.id;
  const id = createOperationId();
  if (identity) pendingOperations.set(identity, { id, createdAt: now });
  return id;
}

function isNetworkFailure(error: unknown): boolean {
  if (error instanceof TypeError) return true;
  return typeof DOMException !== "undefined"
    && error instanceof DOMException
    && ["NetworkError", "TimeoutError"].includes(error.name);
}

export async function request<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  const method = String(options?.method || "GET").toUpperCase();
  const headers = new Headers(options?.headers);
  const mutating = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  const identity = mutating ? commandIdentity(method, path, options?.body) : undefined;
  const operationId = options?.operationId ?? (mutating ? operationForCommand(identity) : "");
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", operationId);
  }
  const networkRetries = options?.networkRetries;
  const fetchOptions = { ...(options ?? {}) };
  delete fetchOptions.operationId;
  delete fetchOptions.networkRetries;
  const attempts = 1 + (mutating ? Math.max(0, networkRetries ?? 1) : 0);
  let response: Response | undefined;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      response = await fetch(path, { ...fetchOptions, headers });
      if (identity) pendingOperations.delete(identity);
      break;
    } catch (error) {
      if (!isNetworkFailure(error) || attempt + 1 >= attempts) throw error;
    }
  }
  if (!response) throw new TypeError(`Network request failed for ${path}`);
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
