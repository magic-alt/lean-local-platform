import { encodePath, request } from "./client";
import type {
  RunStatus,
  DataAsset,
  DataProvider,
  DataSyncCatalog,
  DataContractCatalog,
  DataSyncRun,
  DerivedLayerWatermarks,
  OnDemandStorageTarget,
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
  WorkflowDetail,
  WorkflowSummary,
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
  PortfolioOptimizationRun,
  PortfolioOptimizationCandidate,
  BacktestCompareResult,
  OptimizationRun,
  OptimizationRequest,
  BacktestOptimizationDraft,
  ResearchSession,
  ResearchRun,
  ResearchTemplate,
  ResearchWorkspace,
  DataScope,
  DataScopeResolution,
  ResearchCheckResult,
  ReportRecord,
  ObjectStoreItem,
  PaperBacktestCandidate,
  PaperAccount,
  PaperDataTrust,
  PaperCertificationCohort,
  PaperAccountOverview,
  PaperAccountComparison,
  PaperDeployment,
  PaperExecutionCycle,
  PaperPosition,
  PaperSignal,
  PagedResponse,
  LogWindow,
  ChartPoint,
  ChartData,
  ScreeningReport,
  DataQueryRow,
  DataQueryResult,
  FactorEvaluationResult,
  CBondPoolItem,
  CBondRiskItem,
  FuturesMainItem,
  FuturesContinuousResult,
  MaintenanceHistoryClearResult,
  AshareTechCapabilities,
  AshareTechPromptTemplate,
  AshareTechProductionProfile,
  AshareTechReport,
  AshareTechReportList,
  AshareTechRuleTag,
  AshareTechWatchlist,
  AshareTechWatchlistItem,
  AshareTechAgentRun,
  AshareTechModelDiagnostic,
  AshareTechEvaluationItem,
  AshareTechEvaluationSummary,
  SecurityProfile,
  DatasetPreviewResult,
  WorkflowExample,
  ExperimentBatch,
  ExperimentBatchComparison,
  ExperimentBatchPreview,
  HelpArticleSummary,
  HelpArticle
} from "./types";

export * from "./types";

export const api = {
  health: () => request<{ status: string; redis: boolean }>("/api/health"),
  dependencyHealth: () => request<DependencyHealth>("/api/health/dependencies"),
  databaseHealth: () => request<DatabaseHealth>("/api/health/database"),
  workflows: (status?: string, limit = 100) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set("status", status);
    return request<PagedResponse<WorkflowSummary>>(`/api/workflows?${query.toString()}`);
  },
  workflow: (id: string) => request<WorkflowDetail>(`/api/workflows/${encodeURIComponent(id)}`),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  strategyTemplates: () => request<StrategyTemplate[]>("/api/strategies/templates"),
  examples: (kind?: "backtest" | "optimization" | "research", q?: string) =>
    request<{ items: WorkflowExample[]; count: number }>(`/api/examples?${new URLSearchParams({ ...(kind ? { kind } : {}), ...(q ? { q } : {}) }).toString()}`),
  instantiateExample: (kind: WorkflowExample["kind"], key: string, payload: { name?: string; overrides?: Record<string, unknown> } = {}) =>
    request<{ example: WorkflowExample; project: Project; launch: { route: string; defaults: Record<string, unknown> } }>(`/api/examples/${encodeURIComponent(kind)}/${encodeURIComponent(key)}/instantiate`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  experimentBatches: () => request<ExperimentBatch[]>("/api/experiment-batches?paged=false&limit=1000"),
  compareExperimentBatches: (payload: { batchIds: string[]; metric?: string; xParameter?: string; yParameter?: string }) =>
    request<ExperimentBatchComparison>("/api/experiment-batches/compare", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  experimentBatchPreview: (payload: Record<string, unknown>) => request<ExperimentBatchPreview>("/api/experiment-batches/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  createExperimentBatch: (payload: Record<string, unknown>) => request<ExperimentBatch>("/api/experiment-batches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }),
  experimentBatch: (id: string) => request<ExperimentBatch>(`/api/experiment-batches/${encodeURIComponent(id)}`),
  deleteExperimentBatch: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/experiment-batches/${encodeURIComponent(id)}`, { method: "DELETE" }),
  cancelExperimentBatch: (id: string) => request<ExperimentBatch>(`/api/experiment-batches/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  retryExperimentBatch: (id: string) => request<ExperimentBatch>(`/api/experiment-batches/${encodeURIComponent(id)}/retry-failed`, { method: "POST" }),
  restartExperimentBatch: (id: string) => request<ExperimentBatch>(`/api/experiment-batches/${encodeURIComponent(id)}/restart`, { method: "POST" }),
  experimentBatchExportUrl: (id: string) => `/api/experiment-batches/${encodeURIComponent(id)}/export.csv`,
  helpArticles: (q?: string) => request<{ items: HelpArticleSummary[]; count: number }>(`/api/help/articles${q ? `?q=${encodeURIComponent(q)}` : ""}`),
  helpArticle: (slug: string) => request<HelpArticle>(`/api/help/articles/${encodeURIComponent(slug)}`),
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
  projects: () => request<Project[]>("/api/projects?paged=false&limit=1000"),
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
    request<{ deleted: boolean; details: { project: string; archived: boolean; historyPreserved: boolean; sourceRemoved: boolean } }>(
      `/api/projects/${encodeURIComponent(id)}`,
      { method: "DELETE" }
    ),
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
        listedDate?: string | null;
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
  securityProfile: (market: string, symbol: string) =>
    request<SecurityProfile>(
      `/api/securities/${encodeURIComponent(symbol)}/profile?market=${encodeURIComponent(market)}`
    ),
  dataIdentifiers: (symbol: string) =>
    request<{ symbol: string; items: Array<Record<string, unknown>>; count: number }>(
      `/api/data/identifiers/${encodeURIComponent(symbol)}`
    ),
  dataAssets: () => request<DataAsset[]>("/api/data-assets?paged=false&limit=1000"),
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
  dataContracts: (params?: { assetClass?: string; status?: string; includeFields?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.assetClass) query.set("assetClass", params.assetClass);
    if (params?.status) query.set("status", params.status);
    if (params?.includeFields) query.set("includeFields", "true");
    return request<DataContractCatalog>(`/api/data/contracts?${query.toString()}`);
  },
  datasetPreview: (dataset: string, params?: {
    keyword?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
    offset?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.keyword) query.set("keyword", params.keyword);
    if (params?.startDate) query.set("startDate", params.startDate);
    if (params?.endDate) query.set("endDate", params.endDate);
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    return request<DatasetPreviewResult>(
      `/api/data/dataset-preview/${encodeURIComponent(dataset)}?${query.toString()}`
    );
  },
  onDemandStorageTargets: () => request<{ items: OnDemandStorageTarget[] }>("/api/data/on-demand/storage-targets"),
  createOnDemandDownload: (payload: {
    dataset: string;
    storageTarget: string;
    relativePath?: string;
    format: "parquet" | "jsonl";
    startDate?: string;
    endDate?: string;
    symbol?: string;
    apiParameters?: Record<string, unknown>;
  }) => request<Task>("/api/data/on-demand/downloads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  dataSyncRuns: () => request<PagedResponse<DataSyncRun>>("/api/data/sync-runs"),
  dataSyncRun: (id: string) => request<DataSyncRun>(`/api/data/sync-runs/${encodeURIComponent(id)}`),
  derivedLayerWatermarks: () => request<DerivedLayerWatermarks>("/api/data/derived/watermarks"),
  startDerivedMaintenance: (layers: Array<"parquet" | "clickhouse"> = ["parquet", "clickhouse"]) =>
    request<{ id: string; status: string }>("/api/data/derived/maintenance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ layers })
    }),
  createDataSyncRun: (datasets?: string[], mode: "auto" | "incremental" | "full_rebuild" = "auto") =>
    request<DataSyncRun>("/api/data/sync-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ datasets: datasets?.length ? datasets : null, mode })
    }),
  prepareMlData: (payload: { mode: "auto" | "incremental" | "full_rebuild" | "universe_backfill" | "screen_backfill"; datasets: string[]; scope: Record<string, unknown> }) =>
    request<DataSyncRun>("/api/data/sync-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
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
  backtests: (filters?: { name?: string; status?: string; projectId?: string; symbol?: string; market?: string; fromDate?: string; toDate?: string }) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value) query.set(key, String(value));
    });
    query.set("paged", "false");
    query.set("limit", "100");
    const suffix = `?${query.toString()}`;
    return request<BacktestRun[]>(`/api/backtests${suffix}`);
  },
  backtestsPage: (
    filters?: { name?: string; status?: string; projectId?: string; symbol?: string; market?: string; fromDate?: string; toDate?: string },
    page: { limit: number; offset: number } = { limit: 20, offset: 0 }
  ) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value) query.set(key, String(value));
    });
    query.set("paged", "true");
    query.set("limit", String(page.limit));
    query.set("offset", String(page.offset));
    return request<PagedResponse<BacktestRun>>(`/api/backtests?${query.toString()}`);
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
    projectId: string;
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
    projectId: string;
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
  deleteBacktest: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/backtests/${encodeURIComponent(id)}`, { method: "DELETE" }),
  logs: (id: string, params?: { cursor?: string; offset?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.cursor !== undefined) query.set("cursor", params.cursor);
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<LogWindow>(`/api/backtests/${encodeURIComponent(id)}/logs${suffix}`);
  },
  chartData: (id: string, symbol?: string) =>
    request<ChartData>(`/api/backtests/${encodeURIComponent(id)}/chart-data${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  screening: (id: string) =>
    request<ScreeningReport>(`/api/backtests/${encodeURIComponent(id)}/screening`),
  tasks: () => request<Task[]>("/api/tasks?paged=false&limit=100"),
  task: (id: string) => request<Task>(`/api/tasks/${encodeURIComponent(id)}`),
  taskLogs: (id: string, params?: { cursor?: string; offset?: number; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.cursor !== undefined) query.set("cursor", params.cursor);
    if (params?.offset !== undefined) query.set("offset", String(params.offset));
    if (params?.limit !== undefined) query.set("limit", String(params.limit));
    const suffix = query.size ? `?${query.toString()}` : "";
    return request<LogWindow>(`/api/tasks/${encodeURIComponent(id)}/logs${suffix}`);
  },
  cancelTask: (id: string) => request<Task>(`/api/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  deleteTask: (id: string) => request<{ deleted: boolean; id: string }>(`/api/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  optimizations: () => request<OptimizationRun[]>("/api/optimizations?paged=false&limit=1000"),
  optimization: (id: string) => request<OptimizationRun>(`/api/optimizations/${encodeURIComponent(id)}`),
  optimizationPreview: (payload: OptimizationRequest) =>
    request<ExperimentBatchPreview & { scopeHash: string; dataFingerprint: string }>("/api/optimizations/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  deleteOptimization: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/optimizations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  archiveOptimization: (id: string) =>
    request<{ archived: boolean; id: string }>(`/api/optimizations/${encodeURIComponent(id)}/archive`, { method: "POST" }),
  cancelOptimization: (id: string) =>
    request<OptimizationRun>(`/api/optimizations/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  retryOptimization: (id: string) =>
    request<OptimizationRun>(`/api/optimizations/${encodeURIComponent(id)}/retry-failed`, { method: "POST" }),
  createOptimization: (payload: OptimizationRequest) =>
    request<OptimizationRun>("/api/optimizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  compareOptimizations: (payload: { optimizationIds: string[]; metric?: string; xParameter?: string; yParameter?: string }) =>
    request<ExperimentBatchComparison>("/api/optimizations/compare", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  optimizationExportUrl: (id: string) => `/api/optimizations/${encodeURIComponent(id)}/export.csv`,
  backtestOptimizationDraft: (id: string) =>
    request<BacktestOptimizationDraft>(`/api/backtests/${encodeURIComponent(id)}/optimization-draft`),
  compareBacktests: (payload: { runIds: string[]; includeCurves?: boolean }) =>
    request<BacktestCompareResult>("/api/compare/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  portfolioOptimizationCandidates: () =>
    request<{ items: PortfolioOptimizationCandidate[] }>("/api/portfolio-optimizations/candidates")
      .then((result) => result.items),
  portfolioOptimizations: () =>
    request<PortfolioOptimizationRun[]>("/api/portfolio-optimizations?paged=false&limit=1000"),
  previewPortfolioOptimization: (payload: {
    name?: string;
    runIds: string[];
    objective?: "sharpe" | "return" | "drawdown";
    step?: number;
    maxWeight?: number;
    allowShort?: boolean;
  }) => request<PortfolioOptimizationResult>("/api/portfolio-optimizations/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  optimizePortfolio: (payload: {
    name?: string;
    runIds: string[];
    objective?: "sharpe" | "return" | "drawdown";
    step?: number;
    maxWeight?: number;
    allowShort?: boolean;
  }) =>
    request<PortfolioOptimizationRun>("/api/portfolio-optimizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  archivePortfolioOptimization: (id: string) =>
    request<{ archived: boolean; id: string }>(`/api/portfolio-optimizations/${encodeURIComponent(id)}/archive`, { method: "POST" }),
  researchTemplates: () => request<{ items: ResearchTemplate[]; count: number }>("/api/research/templates"),
  researchRuns: () => request<ResearchRun[]>("/api/research/runs?paged=false&limit=1000"),
  researchRun: (id: string) => request<ResearchRun>(`/api/research/runs/${encodeURIComponent(id)}`),
  previewResearchRun: (payload: { template: string; name?: string; scope: DataScope; parameters: Record<string, unknown> }) =>
    request<DataScopeResolution>(`/api/research/runs/preview`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  createResearchRun: (payload: { template: string; name?: string; scope: DataScope; parameters: Record<string, unknown> }) =>
    request<ResearchRun>("/api/research/runs", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  deleteResearchRun: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/research/runs/${encodeURIComponent(id)}`, { method: "DELETE" }),
  retryResearchRun: (id: string) =>
    request<ResearchRun>(`/api/research/runs/${encodeURIComponent(id)}/retry`, { method: "POST" }),
  cancelResearchRun: (id: string) =>
    request<ResearchRun>(`/api/research/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  researchRunExportUrl: (id: string) => `/api/research/runs/${encodeURIComponent(id)}/export.csv`,
  researchArtifactUrl: (id: string, key: string) => `/api/research/runs/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(key)}`,
  researchBacktestDraft: (id: string) =>
    request<{ sourceResearchRunId: string; dataScope: DataScope; scopeHash: string; dataFingerprint: string; target: "backtest" | "batch" }>(`/api/research/runs/${encodeURIComponent(id)}/backtest-draft`),
  resolveDataScope: (scope: DataScope) =>
    request<DataScopeResolution>("/api/data/resolve", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scope)
    }),
  researchSessions: () => request<ResearchWorkspace[]>("/api/research/workspaces?paged=false&limit=1000"),
  createResearchSnapshot: (scope: DataScope, researchRunId?: string) =>
    request<{ snapshotId: string; dataFingerprint: string; count: number }>("/api/research/workspaces/snapshots", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(researchRunId ? { researchRunId } : { scope })
    }),
  startResearch: (payload: { projectId: string; port?: number; snapshotId?: string }) =>
    request<ResearchWorkspace>("/api/research/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  stopResearch: (id: string) =>
    request<ResearchWorkspace>(`/api/research/workspaces/${encodeURIComponent(id)}/stop`, { method: "POST" }),
  restartResearch: (id: string) =>
    request<ResearchWorkspace>(`/api/research/workspaces/${encodeURIComponent(id)}/restart`, { method: "POST" }),
  researchLogs: (id: string) =>
    request<{ logs: string; workspaceId: string }>(`/api/research/workspaces/${encodeURIComponent(id)}/logs`),
  runResearchChecks: (id: string, payload: { symbols?: string[]; startDate?: string; endDate?: string } = {}) =>
    request<ResearchCheckResult>(`/api/research/${encodeURIComponent(id)}/checks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  deleteResearch: (id: string, purgeWorkspace = false) =>
    request<{ deleted: boolean; id: string; workspacePurged: boolean }>(
      `/api/research/workspaces/${encodeURIComponent(id)}?purgeWorkspace=${purgeWorkspace ? "true" : "false"}`,
      { method: "DELETE" }
    ),
  reports: () => request<ReportRecord[]>("/api/reports?paged=false&limit=1000"),
  deleteReport: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/reports/${encodeURIComponent(id)}`, { method: "DELETE" }),
  createReport: (payload: { runId: string }) =>
    request<ReportRecord>("/api/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  reportExportUrl: (id: string, format: "html" | "markdown" | "pdf" | "csv" | "json") =>
    `/api/reports/${encodeURIComponent(id)}/export?format=${encodeURIComponent(format)}&view=report-layout-v2`,
  objectStoreItems: () => request<ObjectStoreItem[]>("/api/object-store"),
  uploadObjectStoreItem: (key: string, formData: FormData) =>
    request<ObjectStoreItem>(`/api/object-store/${encodePath(key)}`, {
      method: "POST",
      body: formData
    }),
  deleteObjectStoreItem: (key: string) =>
    request<{ deleted: boolean }>(`/api/object-store/${encodePath(key)}`, { method: "DELETE" }),
  paperCandidates: (projectId: string) =>
    request<PaperBacktestCandidate[]>(`/api/paper/accounts/candidates?projectId=${encodeURIComponent(projectId)}`),
  paperCertificationCohorts: () =>
    request<{ items: PaperCertificationCohort[]; count: number }>("/api/paper/certification-cohorts"),
  createPaperCertificationCohort: (payload: { name: string; accountIds: string[]; requiredSessions?: number }) =>
    request<PaperCertificationCohort>("/api/paper/certification-cohorts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  refreshPaperCertificationCohort: (id: string) =>
    request<PaperCertificationCohort>(`/api/paper/certification-cohorts/${encodeURIComponent(id)}/refresh`, {
      method: "POST"
    }),
  paperAccounts: (filters?: {
    status?: string;
    market?: string;
    strategy?: string;
    keyword?: string;
    health?: string;
    limit?: number;
    offset?: number;
  }) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value !== undefined && value !== "") query.set(key, String(value));
    });
    return request<PagedResponse<PaperAccount>>(`/api/paper/accounts?${query.toString()}`);
  },
  paperAccount: (id: string) =>
    request<PaperAccount>(`/api/paper/accounts/${encodeURIComponent(id)}`),
  createPaperAccount: (payload: {
    name: string;
    description?: string;
    marketScope: "china";
    baseCurrency: "CNY";
    initialCash: string;
    benchmarkSymbol: string;
    riskConfig?: Record<string, unknown>;
  }) => request<PaperAccount>("/api/paper/accounts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  updatePaperAccount: (id: string, payload: Record<string, unknown>) =>
    request<PaperAccount>(`/api/paper/accounts/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  deletePaperAccount: (id: string) =>
    request<{ deleted: boolean; id: string }>(`/api/paper/accounts/${encodeURIComponent(id)}`, {
      method: "DELETE"
    }),
  paperAccountAction: (id: string, action: "activate" | "pause" | "resume" | "archive") =>
    request<PaperAccount>(`/api/paper/accounts/${encodeURIComponent(id)}/${action}`, { method: "POST" }),
  clonePaperAccount: (id: string, payload: { name?: string; initialCash?: string } = {}) =>
    request<PaperAccount>(`/api/paper/accounts/${encodeURIComponent(id)}/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  paperAccountOverview: (id: string) =>
    request<PaperAccountOverview>(`/api/paper/accounts/${encodeURIComponent(id)}/overview`),
  paperAccountPositions: (id: string) =>
    request<PagedResponse<PaperPosition>>(`/api/paper/accounts/${encodeURIComponent(id)}/positions`),
  paperAccountOrders: (id: string) =>
    request<PagedResponse<Record<string, unknown>>>(`/api/paper/accounts/${encodeURIComponent(id)}/orders`),
  paperAccountTrades: (id: string) =>
    request<PagedResponse<Record<string, unknown>>>(`/api/paper/accounts/${encodeURIComponent(id)}/trades`),
  paperAccountSignals: (id: string) =>
    request<PagedResponse<PaperSignal>>(`/api/paper/accounts/${encodeURIComponent(id)}/signals`),
  paperAccountCycles: (id: string) =>
    request<PagedResponse<PaperExecutionCycle>>(`/api/paper/accounts/${encodeURIComponent(id)}/cycles`),
  paperAccountReports: (id: string) =>
    request<PagedResponse<Record<string, unknown>>>(`/api/paper/accounts/${encodeURIComponent(id)}/daily-reports`),
  paperAccountAudit: (id: string) =>
    request<PagedResponse<Record<string, unknown>>>(`/api/paper/accounts/${encodeURIComponent(id)}/audit`),
  paperAccountPerformance: (id: string) =>
    request<{ points: Array<Record<string, unknown>>; benchmarkSymbol: string; currency: string; dataTrust: PaperDataTrust }>(
      `/api/paper/accounts/${encodeURIComponent(id)}/performance`
    ),
  paperDeployments: (accountId: string) =>
    request<PaperDeployment[]>(`/api/paper/accounts/${encodeURIComponent(accountId)}/deployments`),
  createPaperDeployment: (accountId: string, payload: {
    name?: string;
    projectId: string;
    sourceBacktestId: string;
    scheduleType?: string;
    scheduleExpression?: string;
    marketTimezone?: string;
    executionTiming?: string;
    signalMode?: string;
    universeConfig?: Record<string, unknown>;
    isPrimary?: boolean;
  }) => request<PaperDeployment>(`/api/paper/accounts/${encodeURIComponent(accountId)}/deployments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  paperDeploymentAction: (id: string, action: "activate" | "pause" | "resume") =>
    request<PaperDeployment>(`/api/paper/deployments/${encodeURIComponent(id)}/${action}`, { method: "POST" }),
  runPaperDeploymentNow: (id: string, tradingDate?: string) =>
    request<PaperExecutionCycle>(`/api/paper/deployments/${encodeURIComponent(id)}/run-now`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tradingDate })
    }),
  comparePaperAccounts: (ids: string[]) => {
    const query = new URLSearchParams();
    ids.forEach((id) => query.append("accountId", id));
    return request<PaperAccountComparison>(`/api/paper/accounts/compare?${query.toString()}`);
  },
  ashareTechCapabilities: () => request<AshareTechCapabilities>("/api/insights/ashare-tech/capabilities"),
  ashareTechPromptTemplates: () =>
    request<{ items: AshareTechPromptTemplate[]; count: number }>("/api/insights/ashare-tech/prompt-templates"),
  ashareTechPromptTemplateVersions: (templateKey: string) =>
    request<{ items: AshareTechPromptTemplate[]; count: number }>(
      `/api/insights/ashare-tech/prompt-templates/${encodeURIComponent(templateKey)}/versions`
    ),
  saveAshareTechPromptTemplate: (payload: {
    name: string;
    description?: string;
    templateKey?: string;
    stagePrompts: Record<string, string>;
  }) => request<AshareTechPromptTemplate>(
    payload.templateKey
      ? `/api/insights/ashare-tech/prompt-templates/${encodeURIComponent(payload.templateKey)}/versions`
      : "/api/insights/ashare-tech/prompt-templates",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }
  ),
  ashareTechProductionProfile: () =>
    request<AshareTechProductionProfile | null>("/api/insights/ashare-tech/production-profile"),
  updateAshareTechProductionProfile: (payload: {
    provider: string;
    model: string;
    promptVersionId: string;
  }) => request<AshareTechProductionProfile>("/api/insights/ashare-tech/production-profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  }),
  ashareTechReports: () => request<AshareTechReportList>("/api/insights/ashare-tech/reports"),
  ashareTechReport: (id: string) => request<AshareTechReport>(`/api/insights/ashare-tech/reports/${encodeURIComponent(id)}`),
  deleteAshareTechReport: (id: string, force = false) =>
    request<{ deleted: boolean; id: string; deletedTasks: number; cancelledTasks: number; recoveredOrphan: boolean }>(
      `/api/insights/ashare-tech/reports/${encodeURIComponent(id)}${force ? "?force=true" : ""}`,
      { method: "DELETE" }
    ),
  createAshareTechReport: (payload: {
    requestedDate?: string;
    force?: boolean;
    analysisMode?: "auto" | "hybrid_multi_agent" | "deterministic";
    provider?: string;
    model?: string;
    promptVersionId?: string;
  }) =>
    request<{ id: string; taskId?: string | null; status: string; reused: boolean }>("/api/insights/ashare-tech/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }),
  diagnoseAshareTechModel: (payload?: { provider?: string; model?: string }) =>
    request<AshareTechModelDiagnostic>("/api/insights/ashare-tech/model-diagnostics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {})
    }),
  ashareTechAgentRuns: (reportId: string) =>
    request<{ items: AshareTechAgentRun[] }>(
      `/api/insights/ashare-tech/reports/${encodeURIComponent(reportId)}/agent-runs`
    ),
  ashareTechAgentRun: (runId: string) =>
    request<AshareTechAgentRun>(`/api/insights/ashare-tech/agent-runs/${encodeURIComponent(runId)}`),
  ashareTechEvaluations: (params: {
    horizonDays?: 1 | 5 | 20;
    symbol?: string;
    provider?: string;
    model?: string;
    promptVersion?: string;
    limit?: number;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.horizonDays) query.set("horizonDays", String(params.horizonDays));
    if (params.symbol) query.set("symbol", params.symbol);
    if (params.provider) query.set("provider", params.provider);
    if (params.model) query.set("model", params.model);
    if (params.promptVersion) query.set("promptVersion", params.promptVersion);
    query.set("limit", String(params.limit ?? 500));
    return request<{ items: AshareTechEvaluationItem[]; count: number }>(
      `/api/insights/ashare-tech/evaluations?${query.toString()}`
    );
  },
  ashareTechEvaluationSummary: (params: {
    horizonDays?: 1 | 5 | 20;
    provider?: string;
    model?: string;
    promptVersion?: string;
  } = {}) => {
    const query = new URLSearchParams();
    if (params.horizonDays) query.set("horizonDays", String(params.horizonDays));
    if (params.provider) query.set("provider", params.provider);
    if (params.model) query.set("model", params.model);
    if (params.promptVersion) query.set("promptVersion", params.promptVersion);
    return request<AshareTechEvaluationSummary>(
      `/api/insights/ashare-tech/evaluations/summary?${query.toString()}`
    );
  },
  refreshAshareTechEvaluations: () =>
    request<{ taskId: string; status: string }>("/api/insights/ashare-tech/evaluations/refresh", { method: "POST" }),
  ashareTechWatchlist: () => request<AshareTechWatchlist>("/api/insights/ashare-tech/watchlist"),
  addAshareTechWatchlistItem: (payload: { code: string; groupKey: AshareTechWatchlistItem["groupKey"]; ruleTags: AshareTechRuleTag[] }) =>
    request<AshareTechWatchlistItem>("/api/insights/ashare-tech/watchlist/items", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  updateAshareTechWatchlistItem: (code: string, payload: { enabled?: boolean; groupKey?: AshareTechWatchlistItem["groupKey"]; ruleTags?: AshareTechRuleTag[] }) =>
    request<AshareTechWatchlistItem>(`/api/insights/ashare-tech/watchlist/items/${encodeURIComponent(code)}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
    }),
  deleteAshareTechWatchlistItem: (code: string) =>
    request<{ deleted: boolean; code: string; watchlist: AshareTechWatchlist }>(`/api/insights/ashare-tech/watchlist/items/${encodeURIComponent(code)}`, { method: "DELETE" }),
  resetAshareTechWatchlist: () => request<AshareTechWatchlist>("/api/insights/ashare-tech/watchlist/reset", { method: "POST" }),
  clearLocalHistory: (payload?: { dryRun?: boolean; force?: boolean; confirmation?: string }) =>
    request<MaintenanceHistoryClearResult>("/api/maintenance/clear-history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dryRun: payload?.dryRun ?? false,
        force: payload?.force ?? false,
        confirmation: payload?.confirmation
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
  },
  setFuturesFeeSchedule: (payload: {
    product: string;
    exchange: string;
    openRate?: number;
    closeRate?: number;
    closeTodayRate?: number;
    perContract?: number;
    slippageTicks?: number;
    currency?: string;
    version: string;
    source?: string;
  }) => request<Record<string, unknown>>("/api/futures/fee-schedules", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  }),
  buildFuturesContinuous: (payload: {
    product: string;
    exchange: string;
    startDate: string;
    endDate: string;
    adjustment: "none" | "backward_ratio" | "backward_difference";
    contracts: number;
    strictMetadata?: boolean;
  }) => request<FuturesContinuousResult>("/api/futures/continuous-contracts", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  })
};
