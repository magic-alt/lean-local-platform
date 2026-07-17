import { encodePath, request } from "./client";
import type {
  RunStatus,
  DataAsset,
  DataProvider,
  DataSyncCatalog,
  DataSyncRun,
  MarketInfo,
  AssetClassInfo,
  LocalDataFile,
  StrategyParameter,
  StrategyTemplate,
  AppSettings,
  DependencyStatus,
  DependencyHealth,
  UniverseComponent,
  Universe,
  DatabaseHealth,
  IndexMember,
  IndexMembersResult,
  Project,
  ProjectFile,
  Task,
  BacktestRun,
  BacktestPreflight,
  BacktestStatus,
  BacktestValidationGate,
  BacktestValidation,
  BacktestExperiment,
  BacktestValidationResponse,
  BacktestAdmissionResponse,
  BacktestResult,
  PortfolioOptimizationResult,
  BacktestCompareResult,
  OptimizationRun,
  ResearchSession,
  ReportRecord,
  ObjectStoreItem,
  PaperSession,
  PaperDailyReport,
  PaperBacktestCandidate,
  PaperWalkforwardRun,
  ChartPoint,
  ChartData,
  DataQueryRow,
  DataQueryResult,
  FactorEvaluationResult,
  CBondPoolItem,
  CBondRiskItem,
  FuturesMainItem,
  MaintenanceHistoryClearResult,
  InsightCapabilities,
  InsightListResponse,
  InsightReport,
  AshareTechCapabilities,
  AshareTechReport,
  AshareTechReportList,
  AshareTechRuleTag,
  AshareTechWatchlist,
  AshareTechWatchlistItem
} from "./types";

export * from "./types";

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
  indexMembersFromTushareAsOf: (universeCode: string, asOfDate: string) =>
    request<IndexMembersResult & { source?: string; fetchedDate?: string; imported?: Record<string, unknown> }>(
      `/api/pit/index-members/${encodeURIComponent(universeCode)}/as-of/${encodeURIComponent(asOfDate)}/tushare`
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
  updateProject: (id: string, payload: { name?: string; config?: Record<string, unknown> }) =>
    request<Project>(`/api/projects/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  cloneProject: (id: string, payload: { name?: string; config?: Record<string, unknown> }) =>
    request<Project>(`/api/projects/${encodeURIComponent(id)}/clone`, {
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
  searchSecurities: (market: string, keyword: string, limit = 50) =>
    request<{
      items: Array<{
        symbol: string;
        market: string;
        marketLabel: string;
        name: string;
        exchange?: string;
        status?: string;
        hasLocalData: boolean;
        matchType: "exact" | "prefix" | "contains" | "browse";
        matchField: "code" | "name" | "pinyin" | "alias" | "none";
        score: number;
      }>;
      count: number;
      query: string;
      markets: string[];
    }>(
      `/api/securities/search?market=${encodeURIComponent(market)}&keyword=${encodeURIComponent(keyword)}&limit=${encodeURIComponent(limit)}`
    ),
  dataIdentifiers: (symbol: string) =>
    request<{ symbol: string; items: Array<Record<string, unknown>>; count: number }>(
      `/api/data/identifiers/${encodeURIComponent(symbol)}`
    ),
  dataAssets: () => request<DataAsset[]>("/api/data-assets"),
  dataFiles: (assetClass?: string, venue?: string) =>
    request<{ items: LocalDataFile[]; count: number }>(
      `/api/data/files?assetClass=${encodeURIComponent(assetClass ?? "")}&venue=${encodeURIComponent(venue ?? "")}`
    ),
  queryData: (params: {
    symbol?: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    source?: string;
    providerSource?: string;
    providerMode?: string;
    allowResearchSource?: boolean;
    adjust?: string;
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
  dataCatalog: () => request<DataSyncCatalog>("/api/data/catalog"),
  dataSyncRuns: () => request<{ items: DataSyncRun[]; limit: number }>("/api/data/sync-runs"),
  dataSyncRun: (id: string) => request<DataSyncRun>(`/api/data/sync-runs/${encodeURIComponent(id)}`),
  createDataSyncRun: (datasets?: string[]) =>
    request<DataSyncRun>("/api/data/sync-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ datasets: datasets?.length ? datasets : null })
    }),
  cancelDataSyncRun: (id: string) =>
    request<DataSyncRun>(`/api/data/sync-runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  resumeDataSyncRun: (id: string) =>
    request<DataSyncRun>(`/api/data/sync-runs/${encodeURIComponent(id)}/resume`, { method: "POST" }),
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
  preflightBacktest: (payload: {
    symbol: string;
    name?: string;
    assetClass?: string;
    market?: string;
    venue?: string;
    resolution?: string;
    dataType?: string;
    start: string;
    end: string;
    cash: number;
    dockerImage: string;
    projectId?: string;
    benchmarkSymbol?: string;
    feeModel?: string;
    slippageModel?: string;
    source?: string;
    provider?: string;
    allowResearchSource?: boolean;
    parameters?: Record<string, unknown>;
  }) =>
    request<BacktestPreflight>("/api/backtests/preflight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  createBacktest: (payload: {
    symbol: string;
    name?: string;
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
    benchmarkSymbol?: string;
    feeModel?: string;
    slippageModel?: string;
    source?: string;
    provider?: string;
    allowResearchSource?: boolean;
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
  backtestValidation: (id: string) =>
    request<BacktestValidationResponse>(`/api/backtests/${encodeURIComponent(id)}/validation`),
  backtestAdmission: (id: string, profile = "institutional") =>
    request<BacktestAdmissionResponse>(`/api/backtests/${encodeURIComponent(id)}/admission?profile=${encodeURIComponent(profile)}`),
  cancelBacktest: (id: string) =>
    request<BacktestRun>(`/api/backtests/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  logs: (id: string) =>
    request<{ logs: string }>(`/api/backtests/${encodeURIComponent(id)}/logs`),
  chartData: (id: string) =>
    request<ChartData>(`/api/backtests/${encodeURIComponent(id)}/chart-data`),
  tasks: () => request<Task[]>("/api/tasks"),
  taskLogs: (id: string) => request<{ logs: string }>(`/api/tasks/${encodeURIComponent(id)}/logs`),
  cancelTask: (id: string) => request<Task>(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  deleteTask: (id: string) => request<{ deleted: boolean; id: string }>(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
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
    parameters?: Record<string, unknown>;
    parameterGrid: Record<string, unknown[]>;
    maxCandidates?: number;
    dockerImage: string;
  }) =>
    request<OptimizationRun>("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  compareBacktests: (payload: { runIds: string[]; includeCurves?: boolean }) =>
    request<BacktestCompareResult>("/api/compare/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  optimizePortfolio: (payload: {
    runIds: string[];
    objective?: "sharpe" | "return" | "drawdown";
    step?: number;
    maxWeight?: number;
    allowShort?: boolean;
  }) =>
    request<PortfolioOptimizationResult>("/api/portfolios/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  researchSessions: () => request<ResearchSession[]>("/api/research"),
  startResearch: (payload: { projectId: string; port?: number }) =>
    request<ResearchSession>("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  stopResearch: (id: string) =>
    request<ResearchSession>(`/api/research/${encodeURIComponent(id)}/stop`, { method: "POST" }),
  restartResearch: (id: string) =>
    request<ResearchSession>(`/api/research/${encodeURIComponent(id)}/restart`, { method: "POST" }),
  researchLogs: (id: string) =>
    request<{ logs: string; sessionId: string }>(`/api/research/${encodeURIComponent(id)}/logs`),
  deleteResearch: (id: string, purgeWorkspace = false) =>
    request<{ deleted: boolean; id: string; workspacePurged: boolean }>(
      `/api/research/${encodeURIComponent(id)}?purgeWorkspace=${purgeWorkspace ? "true" : "false"}`,
      { method: "DELETE" }
    ),
  reports: () => request<ReportRecord[]>("/api/reports"),
  createReport: (payload: { runId: string }) =>
    request<ReportRecord>("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  reportExportUrl: (id: string, format: "html" | "pdf" | "markdown" | "csv" | "json") =>
    `/api/reports/${encodeURIComponent(id)}/export?format=${encodeURIComponent(format)}`,
  objectStoreItems: () => request<ObjectStoreItem[]>("/api/object-store"),
  uploadObjectStoreItem: (key: string, formData: FormData) =>
    request<ObjectStoreItem>(`/api/object-store/${encodePath(key)}`, {
      method: "POST",
      body: formData
    }),
  deleteObjectStoreItem: (key: string) =>
    request<{ deleted: boolean }>(`/api/object-store/${encodePath(key)}`, { method: "DELETE" }),
  paperSessions: () => request<PaperSession[]>("/api/paper"),
  paperSession: (id: string) => request<PaperSession>(`/api/paper/${encodeURIComponent(id)}`),
  paperCandidates: (projectId: string) =>
    request<PaperBacktestCandidate[]>(`/api/paper/candidates?projectId=${encodeURIComponent(projectId)}`),
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
    sourceBacktestId: string;
    startDate?: string;
    autoAdvance?: boolean;
  }) =>
    request<PaperSession>("/api/paper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  paperReports: (id: string) => request<PaperDailyReport[]>(`/api/paper/${encodeURIComponent(id)}/reports`),
  paperRuns: (id: string) => request<PaperWalkforwardRun[]>(`/api/paper/${encodeURIComponent(id)}/runs`),
  runPaperDay: (id: string, tradeDate: string) =>
    request<PaperWalkforwardRun>(`/api/paper/${encodeURIComponent(id)}/run-day`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tradeDate, autoSignal: false })
    }),
  insightCapabilities: () => request<InsightCapabilities>("/api/insights/capabilities"),
  insights: (filters?: { assetClass?: string; symbol?: string; status?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<InsightListResponse>(`/api/insights${suffix}`);
  },
  createInsight: (payload: {
    symbol: string;
    assetClass: "equity" | "crypto" | "crypto_future" | "future";
    market?: string;
    venue?: string;
    resolution?: "daily";
    dataType?: string;
    asOfDate?: string;
    lookbackBars?: number;
    backtestRunId?: string;
  }) => request<{ id: string; taskId: string; status: string }>("/api/insights", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  insight: (id: string) => request<InsightReport>(`/api/insights/${encodeURIComponent(id)}`),
  deleteInsight: (id: string) =>
    request<{ deleted: boolean; id: string; deletedTasks: number; deletedDecisionSignal: boolean; paperAuditPreserved: boolean }>(
      `/api/insights/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  handoffInsightToPaper: (id: string, payload: { sessionId: string; targetPercent?: number }) =>
    request<{ created: boolean; paperSignal?: Record<string, unknown>; report: InsightReport }>(
      `/api/insights/${encodeURIComponent(id)}/paper-signals`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }
    ),
  ashareTechCapabilities: () => request<AshareTechCapabilities>("/api/ashare-tech-insights/capabilities"),
  ashareTechReports: () => request<AshareTechReportList>("/api/ashare-tech-insights/reports"),
  ashareTechReport: (id: string) => request<AshareTechReport>(`/api/ashare-tech-insights/reports/${encodeURIComponent(id)}`),
  deleteAshareTechReport: (id: string) =>
    request<{ deleted: boolean; id: string; deletedTasks: number }>(
      `/api/ashare-tech-insights/reports/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
  createAshareTechReport: (payload: { requestedDate?: string; force?: boolean }) =>
    request<{ id: string; taskId?: string | null; status: string; reused: boolean }>("/api/ashare-tech-insights/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  ashareTechWatchlist: () => request<AshareTechWatchlist>("/api/ashare-tech-insights/watchlist"),
  addAshareTechWatchlistItem: (payload: { code: string; groupKey: AshareTechWatchlistItem["groupKey"]; ruleTags: AshareTechRuleTag[] }) =>
    request<AshareTechWatchlistItem>("/api/ashare-tech-insights/watchlist/items", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  updateAshareTechWatchlistItem: (code: string, payload: { enabled?: boolean; ruleTags?: AshareTechRuleTag[] }) =>
    request<AshareTechWatchlistItem>(`/api/ashare-tech-insights/watchlist/items/${encodeURIComponent(code)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  deleteAshareTechWatchlistItem: (code: string) =>
    request<{ deleted: boolean; code: string; watchlist: AshareTechWatchlist }>(`/api/ashare-tech-insights/watchlist/items/${encodeURIComponent(code)}`, { method: "DELETE" }),
  resetAshareTechWatchlist: () => request<AshareTechWatchlist>("/api/ashare-tech-insights/watchlist/reset", { method: "POST" }),
  updatePaperSessionStatus: (id: string, status: string) =>
    request<PaperSession>(`/api/paper/${encodeURIComponent(id)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    }),
  clearLocalHistory: (payload?: { dryRun?: boolean; force?: boolean }) =>
    request<MaintenanceHistoryClearResult>("/api/maintenance/clear-history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dryRun: payload?.dryRun ?? false,
        force: payload?.force ?? false
      })
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
