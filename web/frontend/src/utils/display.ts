export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function numericText(value: string) {
  const normalized = value.trim().replace(/,/g, "");
  const match = /^([+-]?)([$¥€£]?)(\d+(?:\.\d+)?)(%?)$/.exec(normalized);
  if (!match) return null;
  const number = Number(`${match[1]}${match[3]}`);
  return Number.isFinite(number)
    ? { number, currency: match[2], percent: match[4] === "%" }
    : null;
}

export function formatNumber(value: unknown, maximumFractionDigits = 4) {
  const number = typeof value === "number"
    ? value
    : typeof value === "string"
      ? numericText(value)?.number
      : Number.NaN;
  if (typeof number !== "number" || !Number.isFinite(number)) return "-";
  const threshold = 10 ** -maximumFractionDigits;
  if (maximumFractionDigits > 0 && number !== 0 && Math.abs(number) < threshold) {
    return `${number < 0 ? "-" : ""}<${threshold.toFixed(maximumFractionDigits)}`;
  }
  return number.toLocaleString(undefined, {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  });
}

export function formatInteger(value: unknown) {
  return formatNumber(value, 0);
}

export function formatCurrency(value: unknown, currency = "USD") {
  const parsed = typeof value === "string" ? numericText(value) : null;
  const number = typeof value === "number" ? value : parsed?.number;
  if (number == null || !Number.isFinite(number)) return "-";
  const symbol = parsed?.currency || (currency === "CNY" ? "¥" : "$");
  return `${symbol}${number.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPercent(value: unknown, maximumFractionDigits = 2) {
  const parsed = typeof value === "string" ? numericText(value) : null;
  const number = typeof value === "number" ? value : parsed?.number;
  if (number == null || !Number.isFinite(number)) return "-";
  const percentage = parsed?.percent ? number : number * 100;
  const threshold = 10 ** -maximumFractionDigits;
  if (percentage !== 0 && Math.abs(percentage) < threshold) {
    return `${percentage < 0 ? "-" : ""}<${threshold.toFixed(maximumFractionDigits)}%`;
  }
  return `${percentage.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits,
  })}%`;
}

export function formatDuration(seconds: unknown) {
  if (seconds == null || seconds === "") return "-";
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "-";
  if (value < 60) return `${formatNumber(value, value < 10 ? 1 : 0)}s`;
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const remainingSeconds = Math.round(value % 60);
  return [
    hours ? `${hours}h` : null,
    minutes ? `${minutes}m` : null,
    remainingSeconds && !hours ? `${remainingSeconds}s` : null,
  ].filter(Boolean).join(" ");
}

export function formatDateTime(value: unknown) {
  if (typeof value !== "string" || !value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function shortValue(value: unknown, max = 72) {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "string") {
    const parsed = numericText(value);
    if (parsed) {
      const formatted = formatNumber(parsed.number);
      return `${parsed.currency}${formatted}${parsed.percent ? "%" : ""}`;
    }
  }
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
