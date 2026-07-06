export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function shortValue(value: unknown, max = 72) {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

export function shortHash(value: unknown) {
  const text = typeof value === "string" ? value : "";
  return text.length > 16 ? `${text.slice(0, 12)}...` : shortValue(text);
}

export function detailText(detail: string | Record<string, unknown>) {
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}
