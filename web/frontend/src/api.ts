export type RunStatus = "created" | "queued" | "running" | "success" | "failed" | "cancelled" | "succeeded" | "interrupted";

export interface DataAsset {
  id: number;
  symbol: string;
  asset_class?: string;
  venue?: string;
  resolution?: string;
  data_type?: string;
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
  markets: string[];
  assetClasses?: string[];
  venues?: string[];
  notes: string;
}

export interface MarketInfo {
  key: string;
  name: string;
  currency: string;
  defaultProvider: string;
  providers: string[];
}

export interface AssetClassInfo {
  key: "equity" | "crypto" | "crypto_future" | "future";
  name: string;
  defaultVenue: string;
  defaultResolution: string;
  venues: string[];
  dataTypes: string[];
  notes: string;
}

export interface LocalDataFile {
  assetClass: string;
  symbol: string;
  venue: string;
  market?: string | null;
  resolution: string;
  dataType: string;
  file: string;
  rows?: number | null;
  size: number;
}

export interface StrategyParameter {
  key: string;
  label: string;
  type: "number" | "string";
  default?: string | number;
  min?: number;
}

export interface StrategyTemplate {
  key: string;
  name: string;
  description: string;
  parameters: StrategyParameter[];
}

export interface AppSettings {
  defaultAssetClass: string;
  defaultMarket: string;
  defaultVenue: string;
  defaultResolution: string;
  defaultDataType: string;
  defaultProvider: string;
  defaultAdjust: string;
  defaultStrategyTemplate: string;
  defaultCash: number;
  defaultStart: string;
  defaultEnd: string;
  dockerImage: string;
  researchImage: string;
  chartPointLimit: number;
  maxConcurrentJobs: number;
  jobTimeoutSeconds: number;
  logLevel: string;
}

export interface DependencyStatus {
  service: string;
  ok: boolean;
  detail: string | Record<string, unknown>;
  latency_ms?: number;
}

export interface DependencyHealth {
  status: "ok" | "degraded";
  dependencies: DependencyStatus[];
  urls: {
    prometheus: string;
    grafana: string;
  };
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

export interface DatabaseHealth {
  service: string;
  ok: boolean;
  detail: {
    engine?: string;
    host?: string;
    port?: number;
    database?: string;
    user?: string;
    path?: string;
    exists?: boolean;
    missingTables: string[];
    counts: Record<string, number>;
    csi300MembershipRows: number;
  };
  latency_ms?: number;
}

export interface IndexMember {
  universe_code: string;
  symbol: string;
  start_date: string;
  end_date?: string | null;
  weight?: number | null;
  name?: string | null;
  exchange?: string | null;
  listed_date?: string | null;
  delisted_date?: string | null;
  status?: string | null;
  is_st?: boolean | number | null;
  industry?: string | null;
}

export interface IndexMembersResult {
  universe: string;
  asOfDate: string;
  items: IndexMember[];
  count: number;
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
  job_id?: string;
  name?: string | null;
  symbol: string;
  asset_class?: string;
  venue?: string;
  resolution?: string;
  data_type?: string;
  parameters: {
    ticker: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    start: string;
    end: string;
    fast?: number;
    slow?: number;
    cash: number;
    [key: string]: unknown;
  };
  project_id?: string | null;
  task_id?: string | null;
  status: RunStatus;
  docker_image: string;
  container_name?: string | null;
  work_dir?: string | null;
  results_dir: string;
  result_json_path?: string | null;
  summary_json_path?: string | null;
  report_html_path?: string | null;
  log_path?: string | null;
  statistics?: Record<string, string> | null;
  exit_code?: number | null;
  error?: string | null;
  error_message?: string | null;
  created_at: string;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  artifacts?: string[];
}

export interface BacktestStatus {
  job_id: string;
  status: RunStatus;
  created_at?: string | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  error?: string | null;
}

export interface BacktestResult {
  id: string;
  job_id: string;
  summary_metrics: Record<string, string>;
  equity_curve: ChartPoint[];
  drawdown_curve: ChartPoint[];
  orders: Array<Record<string, unknown>>;
  trades: Array<Record<string, unknown>>;
  holdings: Array<Record<string, unknown>>;
  statistics: Record<string, string>;
  raw_result_path?: string | null;
  created_at: string;
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
  source?: string;
  task_id?: string | null;
  run_id: string;
  status: string;
  report_path?: string | null;
  result_json_path?: string | null;
  raw_result_object_id?: string | null;
  summary_object_id?: string | null;
  storedObjects?: Array<{ id: string; object_key: string; sha256: string; size: number }>;
  error?: string | null;
  created_at: string;
}

export interface ObjectStoreItem {
  key: string;
  file_path: string;
  size: number;
  updated_at: string;
}

export interface PaperSession {
  id: string;
  project_id?: string | null;
  name: string;
  status: string;
  symbol: string;
  asset_class: string;
  venue: string;
  resolution: string;
  cash: number;
  equity: number;
  parameters?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
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

export interface DataQueryRow {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
}

export interface DataQueryResult {
  enabled: boolean;
  items: DataQueryRow[];
  count: number;
  source?: string;
  message?: string;
  error?: string;
}

export interface FactorEvaluationResult {
  id?: string;
  factor: string;
  universe: string;
  start_date: string;
  end_date: string;
  forward_days: number;
  quantiles: number;
  engine: string;
  observations: number;
  date_count: number;
  mean_ic?: number | null;
  mean_rank_ic?: number | null;
  ic_series: Array<{ trade_date: string; ic: number; count: number }>;
  rank_ic_series: Array<{ trade_date: string; rank_ic: number; count: number }>;
  quantile_returns: Array<{ quantile: number; mean_return?: number | null; count: number }>;
}

export interface CBondPoolItem {
  bond_code: string;
  bond_name?: string | null;
  stock_symbol?: string | null;
  trade_date: string;
  close: number;
  conversion_value?: number | null;
  premium_rate?: number | null;
  double_low?: number | null;
  current_remaining_size?: number | null;
  rating?: string | null;
}

export interface CBondRiskItem {
  id: string;
  bond_code: string;
  bond_name?: string | null;
  announce_date: string;
  trigger_date?: string | null;
  status: string;
  call_price?: number | null;
  last_trade_date?: string | null;
}

export interface FuturesMainItem {
  contract_code: string;
  product: string;
  exchange: string;
  bar_date: string;
  close?: number | null;
  volume?: number | null;
  open_interest?: number | null;
  last_trade_date?: string | null;
  daysToExpiry?: number | null;
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
  dependencyHealth: () => request<DependencyHealth>("/api/health/dependencies"),
  databaseHealth: () => request<DatabaseHealth>("/api/health/database"),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  strategyTemplates: () => request<StrategyTemplate[]>("/api/strategies/templates"),
  assetClasses: () => request<AssetClassInfo[]>("/api/asset-classes"),
  markets: () => request<MarketInfo[]>("/api/markets"),
  djiaUniverse: () => request<Universe>("/api/universes/djia"),
  indexMembersAsOf: (universeCode: string, asOfDate: string) =>
    request<IndexMembersResult>(
      `/api/pit/index-members/${encodeURIComponent(universeCode)}/as-of/${encodeURIComponent(asOfDate)}`
    ),
  projects: () => request<Project[]>("/api/projects"),
  createProject: (payload: {
    name: string;
    language: "Python" | "CSharp";
    algorithmClass?: string;
    templateKey?: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    parameters?: Record<string, unknown>;
  }) =>
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
  symbols: (market = "usa", assetClass = "equity", venue?: string, resolution = "daily", dataType = "trade") =>
    request<{ symbols: string[]; count: number }>(
      `/api/symbols?market=${encodeURIComponent(market)}&assetClass=${encodeURIComponent(assetClass)}&venue=${encodeURIComponent(venue ?? "")}&resolution=${encodeURIComponent(resolution)}&dataType=${encodeURIComponent(dataType)}`
    ),
  searchSecurities: (market: string, keyword: string) =>
    request<{ items: Array<{ symbol: string; market: string; name: string; hasLocalData: boolean }>; count: number }>(
      `/api/securities/search?market=${encodeURIComponent(market)}&keyword=${encodeURIComponent(keyword)}`
    ),
  dataAssets: () => request<DataAsset[]>("/api/data-assets"),
  dataFiles: (assetClass?: string, venue?: string) =>
    request<{ items: LocalDataFile[]; count: number }>(
      `/api/data/files?assetClass=${encodeURIComponent(assetClass ?? "")}&venue=${encodeURIComponent(venue ?? "")}`
    ),
  queryData: (params: {
    symbol: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    source?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<DataQueryResult>(`/api/data/query?${query.toString()}`);
  },
  dataProviders: () => request<DataProvider[]>("/api/data/providers"),
  fetchData: (payload: {
    symbol: string;
    assetClass?: string;
    market: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    provider: string;
    apiKey?: string;
    outputsize: "compact" | "full";
    startDate?: string;
    endDate?: string;
    adjust?: string;
    overwrite: boolean;
  }) =>
    request<DataAsset>("/api/data/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  fetchBatchData: (payload: {
    symbols: string[];
    assetClass?: string;
    market: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    provider: string;
    apiKey?: string;
    outputsize: "compact" | "full";
    startDate?: string;
    endDate?: string;
    adjust?: string;
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
  backtests: (filters?: { status?: string; projectId?: string; symbol?: string; fromDate?: string; toDate?: string }) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value) query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<BacktestRun[]>(`/api/backtests${suffix}`);
  },
  createBacktest: (payload: {
    symbol: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    start: string;
    end: string;
    fast?: number;
    slow?: number;
    cash: number;
    dockerImage: string;
    projectId?: string;
    parameters?: Record<string, unknown>;
  }) =>
    request<BacktestRun>("/api/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  backtest: (id: string) => request<BacktestRun>(`/api/backtests/${encodeURIComponent(id)}`),
  backtestStatus: (id: string) => request<BacktestStatus>(`/api/backtests/${encodeURIComponent(id)}/status`),
  backtestResult: (id: string) =>
    request<{ job: BacktestRun; result: BacktestResult }>(`/api/backtests/${encodeURIComponent(id)}/result`),
  cancelBacktest: (id: string) =>
    request<BacktestRun>(`/api/backtests/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
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
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
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
    request<{ deleted: boolean }>(`/api/object-store/${encodePath(key)}`, { method: "DELETE" }),
  paperSessions: () => request<PaperSession[]>("/api/paper"),
  createPaperSession: (payload: {
    name?: string;
    projectId?: string;
    symbol: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    cash?: number;
    executionPolicy?: string;
    allowSameDayClose?: boolean;
    benchmarkSymbol?: string;
    maxPositions?: number;
    maxPositionWeight?: number;
    minCash?: number;
    blacklist?: string;
    watchlist?: string;
    observeOnlySymbols?: string;
    allowStBuy?: boolean;
    parameters?: Record<string, unknown>;
  }) =>
    request<PaperSession>("/api/paper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  paperReports: (id: string) => request<unknown[]>(`/api/paper/${encodeURIComponent(id)}/reports`),
  updatePaperSessionStatus: (id: string, status: string) =>
    request<PaperSession>(`/api/paper/${encodeURIComponent(id)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    }),
  factorEngines: () => request<{ available: Record<string, boolean>; selected: string }>("/api/factors/engines"),
  evaluateFactor: (payload: {
    factorName: string;
    universeCode: string;
    startDate: string;
    endDate: string;
    forwardDays: number;
    quantiles: number;
    engine?: string;
    persist?: boolean;
  }) =>
    request<FactorEvaluationResult>("/api/factors/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  factorEvaluations: (limit = 50) =>
    request<{ items: Array<{ id: string; factor_name: string; universe_code: string; created_at: string; result?: FactorEvaluationResult }>; count: number }>(
      `/api/factors/evaluations?limit=${encodeURIComponent(limit)}`
    ),
  cbondDoubleLow: (params: { date: string; maxDoubleLow: number; excludeCallRisk: boolean; limit?: number }) => {
    const query = new URLSearchParams({
      date: params.date,
      maxDoubleLow: String(params.maxDoubleLow),
      excludeCallRisk: String(params.excludeCallRisk),
      limit: String(params.limit ?? 100)
    });
    return request<{ asOfDate: string; count: number; items: CBondPoolItem[] }>(`/api/cbond/double-low?${query.toString()}`);
  },
  cbondCallRisk: (date: string) =>
    request<{ asOfDate: string; count: number; items: CBondRiskItem[] }>(`/api/cbond/call-risk?date=${encodeURIComponent(date)}`),
  futuresAgriMain: (params: { date: string; products?: string }) => {
    const query = new URLSearchParams({ date: params.date });
    if (params.products) query.set("products", params.products);
    return request<{ asOfDate: string; count: number; missing: string[]; items: FuturesMainItem[] }>(`/api/futures/agri-main?${query.toString()}`);
  }
};
