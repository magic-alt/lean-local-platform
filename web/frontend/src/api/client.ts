export function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export class ApiError extends Error {
  status: number;
  path: string;
  errorCode?: string;
  traceId?: string;
  workflowId?: string;

  constructor(message: string, status: number, path: string, metadata?: {
    errorCode?: string;
    traceId?: string;
    workflowId?: string;
  }) {
    const traceSuffix = metadata?.traceId ? ` (Trace: ${metadata.traceId})` : "";
    super(`${message}${traceSuffix}`);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
    this.errorCode = metadata?.errorCode;
    this.traceId = metadata?.traceId;
    this.workflowId = metadata?.workflowId;
  }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = response.statusText;
    let errorCode: string | undefined;
    let traceId = response.headers.get("X-Trace-ID") ?? undefined;
    let workflowId = response.headers.get("X-Workflow-ID") ?? undefined;
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
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new ApiError(message, response.status, path, { errorCode, traceId, workflowId });
  }
  return response.json() as Promise<T>;
}
