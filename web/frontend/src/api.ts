export type RunStatus = "queued" | "running" | "succeeded" | "failed" | "interrupted" | "cancelled";

export interface Capability {
  key: string;
  name: string;
  group: string;
  status: "enabled" | "experimental" | "disabled";
  surface: string;
  notes: string;
}

export interface DataAsset {
  id: number;
  symbol: string;
  source: string;
  rows: number;
  first_date: string;
  last_date: string;
  lean_file: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface DataProvider {
  key: string;
  name: string;
  requiresApiKey: boolean;
  supportsBatch: boolean;
  notes: string;
}

export interface UniverseComponent {
  symbol: string;
  name: string;
  sector: string;
  exchange: string;
  hasLocalData: boolean;
}

export interface Universe {
  key: string;
  name: string;
  asOf: string;
  source: string;
  components: UniverseComponent[];
}

export interface Project {
  id: string;
  name: string;
  language: "Python" | "CSharp";
  algorithm_class: string;
  project_path: string;
  main_file: string;
  config?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProjectFile {
  path: string;
  name: string;
  type: "file" | "directory";
}

export interface Task {
  id: string;
  celery_task_id?: string | null;
  kind: string;
  status: RunStatus | "cancelled";
  title: string;
  project_id?: string | null;
  related_id?: string | null;
  parameters: Record<string, unknown>;
  log_path: string;
  artifacts?: string[] | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface BacktestRun {
  id: string;
  symbol: string;
  parameters: {
    ticker: string;
    start: string;
    end: string;
    fast: number;
    slow: number;
    cash: number;
  };
  project_id?: string | null;
  task_id?: string | null;
  status: RunStatus;
  docker_image: string;
  results_dir: string;
  result_json_path?: string | null;
  summary_json_path?: string | null;
  report_html_path?: string | null;
  log_path?: string | null;
  statistics?: Record<string, string> | null;
  exit_code?: number | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  artifacts?: string[];
}

export interface OptimizationRun {
  id: string;
  task_id?: string | null;
  project_id: string;
  status: string;
  parameters: Record<string, unknown>;
  result?: { candidates?: Array<Record<string, unknown>> } | null;
  results_dir: string;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ResearchSession {
  id: string;
  task_id?: string | null;
  project_id: string;
  status: string;
  port: number;
  container_id?: string | null;
  url?: string | null;
  error?: string | null;
  created_at: string;
}

export interface ReportRecord {
  id: string;
  task_id?: string | null;
  run_id: string;
  status: string;
  report_path?: string | null;
  error?: string | null;
  created_at: string;
}

export interface ObjectStoreItem {
  key: string;
  file_path: string;
  size: number;
  updated_at: string;
}

export interface ChartPoint {
  time: string;
  value: number;
}

export interface ChartData {
  statistics: Record<string, string>;
  series: {
    equity: ChartPoint[];
    return: ChartPoint[];
    drawdown: ChartPoint[];
    emaFast: ChartPoint[];
    emaSlow: ChartPoint[];
    benchmark: ChartPoint[];
    price: ChartPoint[];
  };
  orders: Array<{
    time: string;
    side: "BUY" | "SELL";
    symbol: string;
    quantity: number;
    price: number;
    tag?: string;
  }>;
  orderMarkers: Array<{
    time: string;
    side: "BUY" | "SELL";
    symbol: string;
    quantity: number;
    price: number;
    fillPrice: number;
    priceValue?: number | null;
    equityValue?: number | null;
    tag?: string;
  }>;
}

function encodePath(value: string): string {
  return value.split("/").map((part) => encodeURIComponent(part)).join("/");
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch {
      // Keep status text when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; redis: boolean }>("/api/health"),
  capabilities: () => request<Capability[]>("/api/capabilities"),
  djiaUniverse: () => request<Universe>("/api/universes/djia"),
  projects: () => request<Project[]>("/api/projects"),
  createProject: (payload: { name: string; language: "Python" | "CSharp"; algorithmClass?: string }) =>
    request<Project>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  deleteProject: (id: string) =>
    request<{ deleted: boolean }>(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
  projectFiles: (id: string) => request<ProjectFile[]>(`/api/projects/${encodeURIComponent(id)}/files`),
  readProjectFile: (id: string, path: string) =>
    request<{ path: string; content: string }>(
      `/api/projects/${encodeURIComponent(id)}/file?path=${encodeURIComponent(path)}`
    ),
  writeProjectFile: (id: string, path: string, content: string) =>
    request<{ path: string; size: number; updated_at: string }>(`/api/projects/${encodeURIComponent(id)}/file`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content })
    }),
  symbols: () => request<{ symbols: string[]; count: number }>("/api/symbols"),
  dataAssets: () => request<DataAsset[]>("/api/data-assets"),
  dataProviders: () => request<DataProvider[]>("/api/data/providers"),
  fetchData: (payload: {
    symbol: string;
    provider: string;
    apiKey?: string;
    outputsize: "compact" | "full";
    overwrite: boolean;
  }) =>
    request<DataAsset>("/api/data/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  fetchBatchData: (payload: {
    symbols: string[];
    provider: string;
    apiKey?: string;
    outputsize: "compact" | "full";
    overwrite: boolean;
  }) =>
    request<Task>("/api/data/fetch-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  importCsv: (formData: FormData) =>
    request<DataAsset>("/api/data/import-csv", {
      method: "POST",
      body: formData
    }),
  fetchAlphaVantage: (payload: {
    symbol: string;
    apiKey?: string;
    outputsize: "compact" | "full";
    overwrite: boolean;
  }) =>
    request<DataAsset>("/api/data/fetch-alpha-vantage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  backtests: () => request<BacktestRun[]>("/api/backtests"),
  createBacktest: (payload: {
    symbol: string;
    start: string;
    end: string;
    fast: number;
    slow: number;
    cash: number;
    dockerImage: string;
    projectId?: string;
  }) =>
    request<BacktestRun>("/api/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  backtest: (id: string) => request<BacktestRun>(`/api/backtests/${encodeURIComponent(id)}`),
  logs: (id: string) =>
    request<{ logs: string }>(`/api/backtests/${encodeURIComponent(id)}/logs`),
  chartData: (id: string) =>
    request<ChartData>(`/api/backtests/${encodeURIComponent(id)}/chart-data`),
  tasks: () => request<Task[]>("/api/tasks"),
  taskLogs: (id: string) => request<{ logs: string }>(`/api/tasks/${encodeURIComponent(id)}/logs`),
  cancelTask: (id: string) => request<Task>(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  optimizations: () => request<OptimizationRun[]>("/api/optimize"),
  createOptimization: (payload: {
    projectId: string;
    symbol: string;
    start: string;
    end: string;
    cash: number;
    fastValues: number[];
    slowValues: number[];
    dockerImage: string;
  }) =>
    request<OptimizationRun>("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  researchSessions: () => request<ResearchSession[]>("/api/research"),
  startResearch: (payload: { projectId: string; port: number }) =>
    request<ResearchSession>("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  stopResearch: (id: string) =>
    request<ResearchSession>(`/api/research/${encodeURIComponent(id)}/stop`, { method: "POST" }),
  reports: () => request<ReportRecord[]>("/api/reports"),
  createReport: (payload: { runId: string }) =>
    request<ReportRecord>("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  objectStoreItems: () => request<ObjectStoreItem[]>("/api/object-store"),
  uploadObjectStoreItem: (key: string, formData: FormData) =>
    request<ObjectStoreItem>(`/api/object-store/${encodePath(key)}`, {
      method: "POST",
      body: formData
    }),
  deleteObjectStoreItem: (key: string) =>
    request<{ deleted: boolean }>(`/api/object-store/${encodePath(key)}`, { method: "DELETE" })
};
