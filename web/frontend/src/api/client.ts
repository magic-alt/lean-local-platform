export function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export class ApiError extends Error {
  status: number;
  path: string;

  constructor(message: string, status: number, path: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.path = path;
  }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      const detail = body.detail;
      message = typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : message;
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new ApiError(message, response.status, path);
  }
  return response.json() as Promise<T>;
}
