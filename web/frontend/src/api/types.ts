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
  capabilities?: string[];
  productionCertified?: boolean;
  commercial?: boolean;
  enabledByDefault?: boolean;
  disabledByDefault?: boolean;
  notes: string;
}

export interface DataSyncCatalogItem {
  provider: string;
  dataset_key: string;
  api_name: string;
  category: string;
  scope_type: string;
  cadence: string;
  permission_status: "unknown" | "available" | "empty" | "denied" | "retryable";
  permission_reason?: string | null;
  row_count: number;
  first_data_date?: string | null;
  last_data_date?: string | null;
  last_checked_at?: string | null;
  last_synced_at?: string | null;
  metadata?: Record<string, unknown>;
  sync_policy?: "bulk" | "incremental" | "on_demand" | "unavailable";
  skip_reason?: string | null;
  rate_limit_per_hour?: number | null;
  next_allowed_at?: string | null;
}

export interface DataSyncItem {
  id: string;
  run_id: string;
  dataset_key: string;
  status: string;
  processed: number;
  inserted: number;
  updated: number;
  failed: number;
  checkpoint?: Record<string, unknown> | null;
  error?: string | null;
  metrics?: {
    phase?: string;
    apiCalls?: number;
    apiCallsPerMinute?: number;
    apiQuotaPerMinute?: number;
    downloadedRows?: number;
    committedRows?: number;
    downloadRowsPerSecond?: number;
    writeRowsPerSecond?: number;
    queueDepth?: number;
    processedUnits?: number;
    totalUnits?: number;
    emptyUnits?: number;
    validatedRows?: number;
    quarantinedRows?: number;
    unitsPerSecond?: number;
    sessionProcessedUnits?: number;
    etaSeconds?: number | null;
    endpointCalls?: Record<string, number>;
    timingsMs?: Record<string, number>;
    elapsedSeconds?: number;
    diskFreeBytes?: number;
    diskTotalBytes?: number;
    diskFreePercent?: number;
    diskReserveBytes?: number;
    diskWritableBytes?: number;
    databaseBytes?: number;
    databaseLimitBytes?: number;
    databaseUsagePercent?: number;
    databaseLimitEnforced?: boolean;
    onDemandDatabaseLimitBytes?: number;
    databaseSizeSource?: string;
  } | null;
}

export interface DataSyncRun {
  id: string;
  task_id?: string | null;
  provider: string;
  mode: string;
  scope: string;
  status: string;
  requestedDatasets?: string[];
  summary?: Record<string, unknown>;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  cancel_requested?: boolean | number;
  canonical_status?: string | null;
  canonical_ready_at?: string | null;
  derivedStatus?: Record<string, unknown> | null;
  items?: DataSyncItem[];
}

export interface DerivedLayerWatermarks {
  items: Array<{
    layer_key: "parquet" | "clickhouse";
    scope_key: string;
    source: string;
    status: string;
    canonical_start?: string | null;
    canonical_end?: string | null;
    materialized_start?: string | null;
    materialized_end?: string | null;
    row_count: number;
    error?: string | null;
    updated_at: string;
  }>;
  count: number;
  layers: Record<string, {
    count: number;
    ready: number;
    failed: number;
    watermark?: string | null;
  }>;
  runs: Array<{
    id: string;
    trigger_type: string;
    status: string;
    created_at: string;
    finished_at?: string | null;
    error?: string | null;
  }>;
  schedule: {
    timezone: string;
    days: string;
    defaultTime: string;
  };
  asOfDate: string;
}

export interface DataSyncCatalog {
  provider: string;
  entitlementPoints: number;
  boundary: string;
  items: DataSyncCatalogItem[];
  count: number;
  available: number;
  storage?: {
    diskFreeBytes?: number;
    diskTotalBytes?: number;
    diskFreePercent?: number;
    diskReserveBytes?: number;
    diskWritableBytes?: number;
    databaseBytes?: number;
    databaseLimitBytes?: number;
    databaseUsagePercent?: number;
    databaseLimitEnforced?: boolean;
    onDemandDatabaseLimitBytes?: number;
    databaseSizeSource?: string;
  };
  activeRun?: DataSyncRun | null;
  latestRun?: DataSyncRun | null;
  hasCompletedInitialSync: boolean;
  recommendedMode: "initial_full" | "incremental";
}

export interface SecurityProfileIdentifier {
  provider?: string | null;
  identifier_type?: string | null;
  identifier_value?: string | null;
  exchange?: string | null;
  market?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  is_primary?: boolean | number;
  source?: string | null;
}

export interface SecurityProfileCoverage {
  key: string;
  label: string;
  rows: number;
  firstDate?: string | null;
  lastDate?: string | null;
  sources: string[];
}

export interface SecurityProfile {
  symbol: string;
  name: string;
  market: string;
  marketLabel: string;
  exchange?: string | null;
  listedDate?: string | null;
  delistedDate?: string | null;
  status?: string | null;
  isSt: boolean;
  industry?: string | null;
  concepts: string[];
  currency?: string | null;
  lotSize?: number | null;
  tickSize?: number | null;
  masterSource?: string | null;
  masterUpdatedAt?: string | null;
  hasLocalData: boolean;
  identifiers: SecurityProfileIdentifier[];
  coverage: SecurityProfileCoverage[];
  latestTradeStatus?: Record<string, unknown> | null;
  memberships: Array<Record<string, unknown>>;
  quote?: {
    tradeDate?: string | null;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    close?: number | null;
    previousClose?: number | null;
    change?: number | null;
    pctChange?: number | null;
    volume?: number | null;
    amount?: number | null;
    turnoverRate?: number | null;
    adjustmentFactor?: number | null;
    source?: string | null;
  } | null;
  adjustmentHistory: Array<Record<string, unknown>>;
  suspensionHistory: Array<Record<string, unknown>>;
  limitHistory: Array<Record<string, unknown>>;
}

export interface DatasetPreviewResult {
  dataset: string;
  items: Array<Record<string, unknown>>;
  count: number;
  limit: number;
  offset: number;
  storage: "canonical_table" | "compressed_archive" | string;
  updatedAt?: string | null;
}

export interface OnDemandStorageTarget {
  id: string;
  label: string;
  path: string;
  displayPath: string;
  kind: "mounted_data" | "parquet_lake" | "workspace" | "external" | string;
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
  type: "number" | "string" | "text";
  default?: string | number;
  min?: number;
  max?: number;
  step?: number;
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
  maxBatchRuns: number;
  jobTimeoutSeconds: number;
  logLevel: string;
}

export interface WorkflowExample {
  key: string;
  kind: "backtest" | "optimization" | "research";
  name: string;
  description: string;
  templateKey: string;
  mode: string;
  version: number;
  tags: string[];
  defaults: Record<string, unknown>;
}

export interface ExperimentBatchItem {
  id: string;
  batch_id: string;
  item_index: number;
  item_key: string;
  project_id?: string | null;
  symbol?: string | null;
  status: string;
  parameters: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  related_id?: string | null;
  error?: string | null;
  attempt: number;
}

export interface ExperimentBatch {
  id: string;
  kind: "backtest" | "optimization" | "research";
  mode: string;
  name: string;
  example_key?: string | null;
  status: string;
  config: Record<string, unknown>;
  summary?: {
    rankingMetric?: string;
    ranking?: Array<Record<string, any>>;
    candidates?: Array<Record<string, any>>;
    bestCandidate?: Record<string, any> | null;
    minCoverage?: number;
    parameterSensitivity?: ExperimentSensitivity[];
    walkForward?: Array<Record<string, any>>;
  } | null;
  walkForwardEvidence?: {
    id: string;
    status: string;
    dataset_version: string;
    universe_version: string;
    adjustment_contract: string;
    feature_pipeline_version: string;
    selection_metric: string;
    selection_rule: string;
    windows: Array<Record<string, any>>;
  } | null;
  total: number;
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  skipped: number;
  cancelled: number;
  cancel_requested: boolean | number;
  items?: ExperimentBatchItem[];
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ExperimentSensitivity {
  metric: string;
  xParameter: string;
  yParameter: string;
  xValues: number[];
  yValues: number[];
  cells: Array<{ x: number; y: number; value: number; median: number; count: number }>;
}

export interface ExperimentBatchComparison {
  rankingMetric: string;
  rankingBasis: string;
  batches: Array<{
    id: string;
    name: string;
    kind: string;
    mode: string;
    status: string;
    createdAt: string;
    rank: number;
    rankingValue?: number | null;
    metrics: {
      runs: number;
      successes: number;
      [metric: string]: number | { best?: number | null; median?: number | null; mean?: number | null; count: number };
    };
    bestRun?: Record<string, any> | null;
    parameterSensitivity: ExperimentSensitivity[];
    phaseSeries: Array<Record<string, any>>;
  }>;
  metricMatrix: Array<{ metric: string; values: Record<string, Record<string, number | null>> }>;
}

export interface ExperimentBatchPreview {
  kind: string;
  mode: string;
  expandedCount: number;
  parameterCandidates?: number;
  workUnits?: number;
  limit: number;
  withinLimit: boolean;
  effectiveConcurrency: number;
  selection: Record<string, unknown>;
  warnings: string[];
  sample: Array<Record<string, unknown>>;
}

export interface HelpArticleSummary {
  slug: string;
  title: string;
  group: "guide" | "reference";
  category: string;
  order: number;
  summary: string;
  status: "current" | "historical";
  snippet: string;
}

export interface HelpArticle extends Omit<HelpArticleSummary, "snippet"> {
  content: string;
}

export interface DependencyStatus {
  service: string;
  ok: boolean;
  detail: string | Record<string, unknown>;
  latency_ms?: number;
}

export interface DependencyHealth {
  status: "ok" | "degraded";
  executionStatus: "ok" | "degraded";
  executionBlockers: string[];
  operationalBlockers: string[];
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
  detail:
    | string
    | {
      [key: string]: unknown;
      engine?: string;
      host?: string;
      port?: number;
      database?: string;
      user?: string;
      path?: string;
      mode?: string;
      error?: string;
      missingTables?: string[];
      counts?: Record<string, number>;
      csi300MembershipRows?: number;
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
  display_name?: string;
  language: "Python" | "CSharp";
  algorithm_class: string;
  project_path: string;
  main_file: string;
  config?: Record<string, unknown>;
  run_count?: number;
  latest_run_at?: string | null;
  latest_run_status?: RunStatus | null;
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

export interface WorkflowSummary {
  workflow_id: string;
  started_at: string;
  updated_at: string;
  event_count: number;
  failure_count: number;
}

export interface WorkflowEvent {
  id: string;
  workflow_id: string;
  trace_id: string;
  stage: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  status: string;
  error_code?: string;
  message?: string;
  details?: Record<string, unknown>;
  created_at: string;
}

export interface WorkflowDetail {
  workflow_id: string;
  status: string;
  events: WorkflowEvent[];
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
  failure?: {
    stage: "preflight" | "queue" | "execution" | "validation" | "analysis" | string;
    code: string;
    message: string;
    retryable?: boolean;
    details?: Record<string, unknown>;
  } | null;
  created_at: string;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  artifacts?: string[];
  fingerprint?: Record<string, unknown> | null;
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
}

export interface BacktestPreflight {
  ready: boolean;
  market?: string;
  assetClass?: string;
  effectiveSource?: string;
  repaired: string[];
  items: Array<{
    role: string;
    repaired: boolean;
    reason?: string;
    before?: Record<string, unknown>;
    after?: Record<string, unknown>;
  }>;
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

export interface BacktestValidationGate {
  name: string;
  passed: boolean;
  severity: string;
  details?: Record<string, unknown>;
}

export interface BacktestValidation {
  schemaVersion?: number;
  generatedAt?: string;
  scope?: Record<string, unknown>;
  marketRules?: Record<string, unknown>;
  data?: Record<string, unknown>;
  gates?: BacktestValidationGate[];
  passed?: boolean;
  severity?: string;
  [key: string]: unknown;
}

export interface BacktestExperiment {
  schemaVersion?: number;
  runId?: string;
  createdAt?: string;
  strategy?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
  data?: Record<string, unknown>;
  environment?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface BacktestValidationResponse {
  job_id: string;
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
  fingerprint?: Record<string, unknown> | null;
}

export interface StrategyAdmissionGate {
  name: string;
  passed: boolean;
  severity: string;
  actual?: unknown;
  expected?: unknown;
  baseline?: unknown;
  reason?: string;
}

export interface StrategyAdmission {
  id: string;
  strategy_id: string;
  strategy_version_id?: string | null;
  parameters_sha256: string;
  profile_name: string;
  profile_version: string;
  sample_set: string;
  current_stage: "research" | "baseline_registered" | "admission_passed" | "paper_validated";
  baselineSnapshot?: Record<string, unknown> | null;
  evaluation?: {
    status?: "pass" | "watch" | "fail";
    stage?: string;
    aggregate?: Record<string, unknown>;
    gates?: StrategyAdmissionGate[];
    evaluatedAt?: string;
  } | null;
  events?: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
}

export interface BacktestAdmissionResponse {
  runId: string;
  strategyId?: string | null;
  parametersSha256: string;
  profile: string;
  registrationStatus?: "registered" | "not_registered" | "not_applicable";
  admission?: StrategyAdmission | null;
}

export interface PortfolioOptimizationResult {
  schemaVersion: number;
  objective: "sharpe" | "return" | "drawdown";
  runIds: string[];
  weights: Record<string, number>;
  metrics: Record<string, number>;
  alignedStart: string;
  alignedEnd: string;
  alignedPoints: number;
  candidateCount: number;
  equityCurve: ChartPoint[];
  generatedAt: string;
  baseCurrency: string;
  resolution: string;
  inputFingerprints: Record<string, string>;
}

export interface PortfolioOptimizationRun {
  id: string;
  name: string;
  status: string;
  objective: "sharpe" | "return" | "drawdown";
  runIds: string[];
  constraints: { step: number; maxWeight: number; allowShort: boolean };
  inputFingerprints: Record<string, string>;
  result?: PortfolioOptimizationResult | null;
  base_currency?: string | null;
  resolution?: string | null;
  error?: string | null;
  archived_at?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface PortfolioOptimizationCandidate {
  id: string;
  name?: string | null;
  projectId?: string | null;
  symbol?: string | null;
  currency: string;
  resolution: string;
  points: number;
  admissionEligible: boolean;
  finishedAt?: string | null;
  inputFingerprint: string;
}

export interface BacktestResult {
  id: string;
  job_id: string;
  summary_metrics: Record<string, unknown>;
  equity_curve: ChartPoint[];
  drawdown_curve: ChartPoint[];
  orders: Array<Record<string, unknown>>;
  trades: Array<Record<string, unknown>>;
  holdings: Array<Record<string, unknown>>;
  statistics: Record<string, unknown>;
  performance?: {
    validation?: BacktestValidation | null;
    experiment?: BacktestExperiment | null;
    [key: string]: unknown;
  } | null;
  raw_result_path?: string | null;
  created_at: string;
}

export interface OptimizationRun extends ExperimentBatch {
  objective_metric?: "sharpe" | "return" | "drawdown" | null;
  source_backtest_run_id?: string | null;
  scope_hash?: string | null;
  data_fingerprint?: string | null;
  archived_at?: string | null;
  /** Deprecated compatibility fields; new optimization runs use config/summary/items. */
  project_id?: string;
  parameters?: Record<string, unknown>;
  result?: {
    parameterGrid?: Record<string, unknown[]>;
    candidateCount?: number;
    best?: Record<string, unknown> | null;
    candidates?: Array<Record<string, unknown>>;
  } | null;
  results_dir?: string;
  error?: string | null;
}

export interface OptimizationRequest {
  name: string;
  mode: "single_symbol_grid" | "universe_robust" | "walk_forward" | "multi_strategy";
  projectIds: string[];
  dataScope: DataScope;
  execution: {
    cash: number;
    benchmarkSymbol?: string;
    feeModel?: string;
    slippageModel?: string;
    dockerImage: string;
  };
  fixedParametersByProject: Record<string, Record<string, unknown>>;
  parameterGrids: Record<string, Record<string, unknown>>;
  objective: "sharpe" | "return" | "drawdown";
  minCoverage: number;
  maxCandidates: number;
  walkForward?: { trainYears: number; testYears: number; stepYears: number; validationMonths?: number };
  sourceBacktestRunId?: string;
}

export interface BacktestOptimizationDraft extends Partial<OptimizationRequest> {
  sourceBacktestRunId: string;
  projectIds: string[];
  dataScope: DataScope;
  parameterSchemas: Record<string, StrategyParameter[]>;
  scopeHash: string;
  dataFingerprint?: string | null;
}

export interface BacktestCompareItem {
  runId: string;
  name?: string | null;
  symbol?: string | null;
  assetClass?: string | null;
  venue?: string | null;
  status: string;
  projectId?: string | null;
  createdAt?: string | null;
  finishedAt?: string | null;
  parameters: Record<string, unknown>;
  metrics: Record<string, number | string | boolean | null>;
  equityCurve?: ChartPoint[];
  normalizedEquityCurve?: ChartPoint[];
  drawdownCurve?: ChartPoint[];
  currency?: string;
  resolution?: string;
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
  error?: string | null;
}

export interface BacktestCompareResult {
  items: BacktestCompareItem[];
  rankings: Record<string, string[]>;
  compatibility?: {
    currencies: string[];
    resolutions: string[];
    rawNavComparable: boolean;
    riskMetricComparable: boolean;
    warnings: string[];
  };
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
  project_name?: string | null;
  readiness_status?: string | null;
  container_status?: string | null;
  workspace_path?: string | null;
  last_checked_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
}

export interface DataScope {
  asset: {
    assetClass: string;
    market: string;
    venue?: string | null;
    resolution: string;
    dataType: string;
  };
  selection: {
    type: "symbols" | "universe" | "products" | "all";
    values: string[];
  };
  time: {
    startDate?: string | null;
    endDate?: string | null;
    asOfDate?: string | null;
  };
  price: { adjust: string };
  provider: {
    source: string;
    mode: "strict" | "fallback";
    allowResearchSource: boolean;
  };
}

export interface DataScopeResolution {
  scope: DataScope;
  scopeHash: string;
  dataFingerprint: string;
  source: string;
  ready: boolean;
  coverage: { rows?: number; symbols?: number; first_date?: string | null; last_date?: string | null };
  certification?: Record<string, unknown> | null;
  sourceAttempts: Array<{ source: string; rows: number }>;
  blocking?: string[];
}

export interface ResearchTemplate {
  key: string;
  name: string;
  description: string;
  category: string;
  parameterSchema: Record<string, unknown>;
}

export interface ResearchResultTable {
  name: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  truncated?: boolean;
}

export interface ResearchRun {
  id: string;
  task_id?: string | null;
  template_key: string;
  name: string;
  status: string;
  scope: DataScope;
  parameters: Record<string, unknown>;
  result?: {
    schemaVersion: string;
    template: string;
    scopeHash: string;
    dataFingerprint: string;
    source: string;
    summary: Record<string, unknown>;
    charts: Array<Record<string, unknown>>;
    tables: ResearchResultTable[];
    warnings: string[];
  } | null;
  summary?: Record<string, unknown> | null;
  data_fingerprint?: string | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ResearchWorkspace extends ResearchSession {
  snapshot_id?: string | null;
}

export interface ResearchCheckResult {
  sessionId: string;
  projectId: string;
  generatedAt: string;
  passed: boolean;
  status: string;
  evidencePath: string;
  checks: Array<{ name: string; passed: boolean; detail?: unknown }>;
}

export interface ReportRecord {
  id: string;
  type?: "backtest" | "report";
  source?: string;
  dataSource?: string | null;
  task_id?: string | null;
  run_id: string;
  status: string;
  benchmark?: string | null;
  summaryMetrics?: Record<string, unknown>;
  hasStoredObjects?: boolean;
  hasFingerprint?: boolean;
  report_path?: string | null;
  result_json_path?: string | null;
  raw_result_object_id?: string | null;
  summary_object_id?: string | null;
  storedObjects?: Array<{ id: string; object_key: string; sha256: string; size: number }>;
  result?: BacktestResult | null;
  fingerprint?: Record<string, unknown> | null;
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
  error?: string | null;
  created_at: string;
}

export interface ObjectStoreItem {
  key: string;
  file_path: string;
  size: number;
  updated_at: string;
}

export interface PaperBacktestCandidate {
  id: string;
  name?: string | null;
  symbol: string;
  start: string;
  end: string;
  cash: number;
  finishedAt?: string | null;
  strategyVersionId?: string | null;
  parameterHash?: string | null;
  admissionStage?: string | null;
  validation?: BacktestValidation;
}

export interface PagedResponse<T> {
  items: T[];
  count: number;
  limit: number;
  offset: number;
  dataTrust?: PaperDataTrust;
}

export interface PaperDataTrust {
  valuationTrusted: boolean;
  reason: "historical_recertification_pending" | null;
}

export interface PaperAccount {
  id: string;
  shadow_session_id: string;
  name: string;
  description?: string | null;
  status: "draft" | "active" | "paused" | "error" | "archived";
  market_scope: "china";
  base_currency: "CNY";
  initial_cash: string;
  benchmark_symbol: string;
  current_generation: number;
  cash?: string;
  available_cash?: string;
  frozen_cash?: string;
  market_value?: string;
  total_equity?: string;
  realized_pnl?: string;
  unrealized_pnl?: string;
  daily_pnl?: string;
  cumulative_return?: string;
  benchmark_return?: string;
  excess_return?: string;
  position_count?: number;
  health_status?: string;
  primary_strategy?: string | null;
  last_successful_trading_date?: string | null;
  next_scheduled_at?: string | null;
  automation_status?: string | null;
  consecutive_failures?: number;
  last_run_status?: string | null;
  last_run_at?: string | null;
  last_failure_code?: string | null;
  last_failure_detail?: string | null;
  pending_signal_count?: number;
  pending_order_count?: number;
  last_valuation_at?: string | null;
  quote_data_timestamp?: string | null;
  source_checkpoint_digest?: string;
  created_at: string;
  updated_at: string;
}

export interface PaperDeployment {
  id: string;
  paper_account_id: string;
  version: number;
  name: string;
  status: "active" | "paused" | "disabled" | "error";
  is_primary: number | boolean;
  project_id: string;
  source_backtest_id: string;
  strategy_version_id?: string | null;
  project_snapshot_id: string;
  dataset_version_id: string;
  schedule_type: string;
  schedule_expression: string;
  market_timezone: string;
  execution_timing: "next_open";
  signal_mode: "paper_execute" | "signal_only";
  strategy_fingerprint: string;
  dataset_fingerprint: string;
  deployment_fingerprint: string;
  last_successful_trading_date?: string | null;
  next_scheduled_at?: string | null;
  consecutive_failures: number;
}

export interface PaperExecutionCycle {
  id: string;
  paper_account_id: string;
  deployment_id: string;
  trading_date: string;
  status: "scheduled" | "waiting_data" | "queued" | "running" | "finalizing" | "succeeded" | "skipped" | "failed";
  signal_count: number;
  intent_count: number;
  order_count: number;
  fill_count: number;
  rejected_count: number;
  skip_reason?: string | null;
  failure_code?: string | null;
  failure_detail?: string | null;
  result_digest?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface PaperAccountOverview {
  account: PaperAccount;
  deployment?: PaperDeployment | null;
  latestCycle?: PaperExecutionCycle | null;
  dataReadiness?: {
    symbol?: string;
    watermark?: {
      provider?: string;
      dataset_key?: string;
      last_data_date?: string | null;
      validation_status?: string;
      updated_at?: string;
    } | null;
    qa?: {
      id?: string;
      severity?: string;
      created_at?: string;
    } | null;
  };
  dataTrust: PaperDataTrust;
}

export interface PaperPosition {
  paper_account_id: string;
  symbol: string;
  security_name?: string | null;
  market: string;
  quantity: string;
  sellable_quantity: string;
  frozen_quantity: string;
  average_cost: string;
  certified_price?: string | null;
  market_value: string;
  account_weight: string;
  daily_pnl: string;
  unrealized_pnl: string;
  realized_pnl: string;
  quote_data_timestamp?: string | null;
  data_status: string;
}

export interface PaperSignal {
  id: string;
  paper_account_id: string;
  deployment_id: string;
  cycle_id: string;
  signal_type: string;
  symbol?: string | null;
  signal_timestamp: string;
  intended_execution_date?: string | null;
  target_quantity?: string | null;
  target_weight?: string | null;
  disposition: string;
  no_trade_reason?: string | null;
  lean_run_id?: string | null;
  data_timestamp?: string | null;
  evidence?: Record<string, unknown>;
}

export interface PaperAccountComparison {
  comparable: boolean;
  reason?: string | null;
  currencies: string[];
  comparisonStart?: string | null;
  valuationDate?: string | null;
  missingData: string[];
  dataTrust: PaperDataTrust;
  accounts: Array<{
    accountId: string;
    name: string;
    currency: string;
    benchmarkSymbol: string;
    cumulativeReturn: string;
    benchmarkReturn: string;
    excessReturn: string;
    turnover: string;
    tradeCount: number;
    positionCount: number;
    riskRejectCount: number;
    cashRatio: string;
    lastRunDate?: string | null;
  }>;
}

export interface InsightCapabilities {
  configured: boolean;
  provider?: string | null;
  model?: string | null;
  assetClasses: Array<"equity" | "crypto" | "crypto_future" | "future">;
  resolutions: string[];
  promptVersion: string;
}

export interface InsightEvidence {
  fact: string;
  sourceKey: "price" | "technical" | "data_quality" | "backtest";
}

export interface InsightSignalPayload {
  stance: "bullish" | "neutral" | "bearish";
  direction: "long" | "flat" | "short";
  intent: "enter" | "add" | "hold" | "reduce" | "exit";
  targetExposure: number;
  confidence: number;
  score: number;
  horizon: string;
  entryLow?: number | null;
  entryHigh?: number | null;
  stopLoss?: number | null;
  targetPrice?: number | null;
  invalidation?: string;
  reason?: string;
  actionable?: boolean;
}

export interface InsightSignalRecord {
  id: string;
  insight_report_id: string;
  status: string;
  rawSignal: Record<string, unknown>;
  finalSignal: InsightSignalPayload;
  guardrail: { passed: boolean; adjusted: boolean; violations: string[]; normalizedFields?: string[] };
}

export interface InsightTechnicalReport {
  metrics: Record<string, number | null>;
  assessment: {
    trend?: string;
    momentum?: string;
    volume?: string;
    volumeRatio20?: number | null;
    rangePosition20Pct?: number | null;
  };
  modelNotes?: string[];
}

export interface InsightAgentSummary {
  workflowVersion: string;
  objective: string;
  steps: Array<{ key: string; label: string; status: "complete" | "warning"; detail: string }>;
  evidenceCoverage: { factCount: number; sourceKeys: string[]; dataSources: string[] };
  uncertainties: string[];
  decision: {
    stance?: string;
    intent?: string;
    horizon?: string;
    score?: number;
    confidence?: number;
    actionable?: boolean;
    summary?: string;
  };
}

export interface InsightReport {
  id: string;
  task_id?: string | null;
  symbol: string;
  asset_class: string;
  market?: string | null;
  venue: string;
  resolution: string;
  data_type: string;
  as_of_date?: string | null;
  lookback_bars: number;
  backtest_run_id?: string | null;
  status: string;
  model?: string | null;
  prompt_version: string;
  input_fingerprint?: string | null;
  context?: Record<string, unknown> | null;
  report?: {
    summary?: { headline?: string; thesis?: string; score?: number };
    technical?: InsightTechnicalReport;
    agent?: InsightAgentSummary;
    risks?: string[];
    catalysts?: string[];
    evidence?: InsightEvidence[];
    dataQuality?: { level?: string; sources?: string[]; warnings?: string[] };
    disclaimer?: string;
  } | null;
  signal?: InsightSignalRecord | null;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface InsightListResponse {
  items: InsightReport[];
  count: number;
  limit: number;
  offset: number;
}

export interface AshareTechCapabilities {
  poolSize: number;
  totalPoolSize: number;
  defaultPoolSize: number;
  groups: Array<{ key: string; name: string; count: number }>;
  primarySource: string;
  crossCheckSource: string;
  promptVersion: string;
  configured: boolean;
  provider?: string | null;
  model?: string | null;
  endpointHost?: string | null;
  apiStyle: string;
  agentMode: string;
  defaultAnalysisMode: "hybrid_multi_agent" | "deterministic";
  stages: Array<{ key: string; name: string; sequence: number }>;
  evaluationHorizons: number[];
  agentPromptVersion: string;
  llmOptional: boolean;
  paperHandoff: boolean;
  schedule: string;
  labels: string[];
}

export type AshareTechRuleTag = "strong_ai" | "storage";

export interface AshareTechWatchlistItem {
  code: string;
  name: string;
  groupKey: "core" | "semiconductor_storage" | "ai_compute";
  group: string;
  enabled: boolean;
  ruleTags: AshareTechRuleTag[];
  source: string;
  created_at: string;
  updated_at: string;
}

export interface AshareTechWatchlist {
  items: AshareTechWatchlistItem[];
  count: number;
  enabledCount: number;
  maxSize: number;
  groups: Array<{ key: AshareTechWatchlistItem["groupKey"]; name: string }>;
  fingerprint: string;
}

export interface AshareTechStockRow {
  code: string;
  name: string;
  group: string;
  date?: string;
  close?: number | null;
  changePct?: number | null;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  ma120?: number | null;
  ma20DeviationPct?: number | null;
  ma60DeviationPct?: number | null;
  drawdown20Pct?: number | null;
  volatility20?: number | null;
  volumeRatio20?: number | null;
  amountRatio20?: number | null;
  turnoverRate?: number | null;
  ma20Direction?: string | null;
  ma60Direction?: string | null;
  ma20Position?: string;
  ma60Position?: string;
  movingAverageDirection?: string;
  macdStatus?: string;
  priceStructure: string;
  volumePriceState: string;
  triggerType: string;
  direction?: string;
  keySupport?: number | null;
  observationZone?: number[] | null;
  invalidation?: number | null;
  nextDayCondition?: string | null;
  announcementRisk?: string;
  conclusion: string;
  dataCompleteness?: { sampleCount?: number; missing?: string[]; latestDate?: string };
}

export interface AshareTechReportPayload {
  title: string;
  requestedDate: string;
  analysisDate: string;
  marketStatus: string;
  dataCutoffAt: string;
  primarySource?: string;
  crossCheckSource?: string;
  sourceConflicts?: Array<Record<string, unknown>>;
  summary?: string;
  conclusionFirst?: {
    lowBuy: string[];
    smallPositionTrial: string[];
    importantChanges: string[];
    highRisk: string[];
    versusPrevious: Record<string, string[] | string>;
  };
  focus?: AshareTechStockRow[];
  fullPool?: AshareTechStockRow[];
  groupSummary?: AshareTechGroupSummary[];
  marketEnvironment?: AshareTechMarketEnvironmentItem[];
  policyEvidence?: Array<{ date: string; title: string; url: string; source: string }>;
  doNotChase?: AshareTechStockRow[];
  nextTradingDayWatch?: Array<{ code?: string; name?: string; condition: string; invalidation?: number | null }>;
  finalThreeLines?: { mostWorthTracking: string; avoidChasingOrBreakdown: string; overallStage: string };
  modelNarrative?: Record<string, string>;
  narrativeStatus?: string;
  narrativeWarning?: string;
  agentRunSummary?: AshareTechAgentRunSummary;
  disclaimer: string;
}

export interface AshareTechAgentStage {
  id?: string;
  stage_key: string;
  sequence_no: number;
  status: "running" | "success" | "fallback" | "failed" | "skipped";
  provider?: string | null;
  model?: string | null;
  prompt_version: string;
  latency_ms?: number | null;
  attempt_count: number;
  error_category?: string | null;
  error?: string | null;
  output?: Record<string, unknown> | null;
  usage?: Record<string, number>;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface AshareTechAgentPrediction {
  id: string;
  symbol: string;
  horizon_days: 1 | 5 | 20;
  predicted_direction: "bullish" | "neutral" | "bearish";
  probabilities: { bullish: number; neutral: number; bearish: number };
  confidence: number;
  trend_score: number;
  rule_conclusion?: string | null;
  selection_rank?: number | null;
  selection_tier: "priority" | "watch" | "unranked";
  rationale: string;
  evidenceIds?: string[];
  neutral_band_pct: number;
  entry_date: string;
  entry_close: number;
  target_date?: string | null;
  benchmark_code: string;
  model: string;
  prompt_version: string;
}

export interface AshareTechAgentRunSummary {
  runId: string;
  analysisMode: string;
  status: string;
  provider?: string | null;
  model?: string | null;
  promptVersion: string;
  stages: AshareTechAgentStage[];
  topSelections: Array<{
    rank: number;
    symbol: string;
    tier: "priority" | "watch";
    consensusScore: number;
    rationale: string;
    evidenceIds: string[];
  }>;
  marketRegime?: string;
  summary?: string;
  predictionCount?: number;
  fallbackReason?: string | null;
  usage?: Record<string, number>;
}

export interface AshareTechAgentRun {
  id: string;
  report_id: string;
  requested_date: string;
  analysis_date: string;
  analysis_mode: string;
  status: string;
  provider?: string | null;
  requested_model?: string | null;
  prompt_version: string;
  fallback_reason?: string | null;
  stageSummary?: AshareTechAgentStage[];
  usage?: Record<string, number>;
  stages: AshareTechAgentStage[];
  predictions: AshareTechAgentPrediction[];
  created_at: string;
  finished_at?: string | null;
}

export interface AshareTechModelDiagnostic {
  configured: boolean;
  provider?: string | null;
  model?: string | null;
  endpointHost?: string | null;
  apiStyle: string;
  status: "ok" | "error" | "unconfigured";
  structuredJson?: boolean;
  latencyMs?: number;
  usage?: Record<string, number>;
  errorCategory?: string;
  error?: string;
  checkedAt: string;
}

export interface AshareTechEvaluationItem extends AshareTechAgentPrediction {
  evaluation_status?: "pending" | "evaluated" | "failed" | null;
  evaluated_date?: string | null;
  exit_close?: number | null;
  return_pct?: number | null;
  benchmark_return_pct?: number | null;
  excess_return_pct?: number | null;
  realized_direction?: "bullish" | "neutral" | "bearish" | null;
  direction_hit?: number | null;
  brier_score?: number | null;
  missing_reason?: string | null;
}

export interface AshareTechEvaluationSummary {
  sampleSize: number;
  pending: number;
  sampleSufficient: boolean;
  directionAccuracy?: number | null;
  meanBrier?: number | null;
  averageReturnPct?: number | null;
  averageExcessReturnPct?: number | null;
  selectedAverageReturnPct?: number | null;
  top5AverageReturnPct?: number | null;
  byHorizon: Array<{
    horizonDays: number;
    sampleSize: number;
    directionAccuracy?: number | null;
    meanBrier?: number | null;
    averageReturnPct?: number | null;
    averageExcessReturnPct?: number | null;
    top5AverageReturnPct?: number | null;
    top5LiftPct?: number | null;
  }>;
}

export interface AshareTechMarketEnvironmentItem {
  code: string;
  name: string;
  category?: "sector";
  keyword?: string;
  matchedName?: string;
  matchedKeyword?: string;
  matchRule?: "canonical" | "alias";
  unresolved?: boolean;
  attemptedAliases?: string[];
  attemptedSources?: string[];
  date?: string;
  close?: number | null;
  changePct?: number | null;
  volumeRatio20?: number | null;
  amountRatio20?: number | null;
  turnoverRate?: number | null;
  pullbackDays?: number;
  source: string;
  error?: string;
}

export interface AshareTechGroupSummary {
  group: string;
  source: string;
  averageChangePct?: number | null;
  totalAmount?: number | null;
  advancers: number;
  decliners: number;
  interpretation: string;
}

export interface AshareTechReport {
  id: string;
  task_id?: string | null;
  requested_date: string;
  analysis_date?: string | null;
  market_status: string;
  status: string;
  attempt_count: number;
  data_cutoff_at?: string | null;
  primary_source: string;
  sector_source?: string | null;
  dataCompleteness?: Record<string, unknown>;
  sourceConflicts?: Array<Record<string, unknown>>;
  sourceManifest?: Array<Record<string, unknown>>;
  report?: AshareTechReportPayload | null;
  model?: string | null;
  analysis_mode?: string | null;
  llm_status?: string | null;
  active_agent_run_id?: string | null;
  agentSummary?: AshareTechAgentRunSummary | null;
  prompt_version: string;
  input_fingerprint?: string | null;
  pool_fingerprint?: string | null;
  poolSnapshot?: { items: AshareTechWatchlistItem[]; count: number; fingerprint: string } | null;
  error?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface AshareTechReportList {
  items: AshareTechReport[];
  count: number;
  limit: number;
  offset: number;
}

export interface ChartPoint {
  time: string;
  value: number;
}

export interface CandlePoint {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StrategyIndicatorSeries {
  chart: string;
  name: string;
  points: ChartPoint[];
}

export interface OrderMarkerPoint {
  time: string;
  side: "BUY" | "SELL";
  symbol: string;
  securityName?: string | null;
  symbolDisplay?: string | null;
  quantity: number;
  price: number;
  fillPrice?: number;
  fill_price?: number;
  equityValue?: number | null;
  priceValue?: number | null;
  tag?: string | null;
}

export interface ChartAsset {
  symbol: string;
  name?: string | null;
  display?: string | null;
  market?: string | null;
  exchange?: string | null;
  orderCount?: number;
}

export interface ChartData {
  statistics: Record<string, string>;
  candles?: CandlePoint[];
  indicators?: StrategyIndicatorSeries[];
  series: {
    equity: ChartPoint[];
    return: ChartPoint[];
    cumulativeReturn?: ChartPoint[];
    drawdown: ChartPoint[];
    emaFast: ChartPoint[];
    emaSlow: ChartPoint[];
    benchmark: ChartPoint[];
    benchmarkReturn?: ChartPoint[];
    price: ChartPoint[];
  };
  seriesSources?: {
    benchmark?: string;
    benchmarkStatus?: "available" | "unavailable";
    [key: string]: unknown;
  };
  orders: Array<{
    time: string;
    side: "BUY" | "SELL";
    symbol: string;
    securityName?: string | null;
    symbolDisplay?: string | null;
    quantity: number;
    price: number;
    fill_price?: number;
    status?: string;
  }>;
  orderMarkers?: OrderMarkerPoint[];
  order_markers?: OrderMarkerPoint[];
  metadata?: {
    benchmarkSymbol?: string | null;
    comparisonBasis?: string;
    multiAsset?: boolean;
    availableAssets?: ChartAsset[];
    selectedAsset?: ChartAsset | null;
    [key: string]: unknown;
  };
}

export interface ScreeningItem {
  symbol: string;
  name?: string | null;
  symbolDisplay?: string | null;
  trend: string;
  technicalScore: number;
  fundamentalScore: number;
  fundamentalFieldCount?: number;
  overallScore: number;
  suitableToBuy: boolean;
  close?: number | null;
  smaFast?: number | null;
  smaSlow?: number | null;
  return20?: number | null;
  rsi?: number | null;
  volatility20?: number | null;
  fundamentals?: Record<string, number>;
  reasons?: string[];
  risks?: string[];
  selectionEligible?: boolean;
  selectionRisks?: string[];
}

export interface ScreeningReport {
  schemaVersion: number;
  sourceSchemaVersion?: number;
  mode: "screening";
  tradeSimulation: false;
  asOfDate?: string | null;
  universeCode?: string | null;
  summary: {
    schemaVersion?: number;
    mode?: string;
    tradeSimulation?: boolean;
    asOfDate?: string | null;
    universeCode?: string | null;
    evaluated: number;
    qualified: number;
    qualifiedSymbols?: string[];
    selected: string[];
    selectionCriteria?: {
      topN: number;
      minOverallScore: number;
      rsiMin: number;
      rsiMax: number;
      maxVolatility: number;
      maxRisks: number;
    };
  };
  items: ScreeningItem[];
  qualified: ScreeningItem[];
  selected: ScreeningItem[];
}

export interface DataQueryRow {
  timestamp: string;
  time?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source?: string;
}

export type DataRow = DataQueryRow;

export interface DataQueryResult {
  source: string;
  items: DataQueryRow[];
  count: number;
  enabled: boolean;
  message?: string;
  error?: string;
}

export interface FactorQuantileReturn {
  quantile: number;
  mean_return: number | null;
  count: number;
}

export interface FactorEvaluationSeriesPoint {
  trade_date: string;
  ic?: number;
  rank_ic?: number;
  count: number;
}

export interface FactorEvaluationResult {
  factor?: string;
  universe?: string;
  start_date?: string;
  end_date?: string;
  forward_days?: number;
  quantiles?: number;
  date_count?: number;
  observations?: number;
  mean_ic?: number | null;
  mean_rank_ic?: number | null;
  engine?: string;
  ic_series?: FactorEvaluationSeriesPoint[];
  rank_ic_series?: FactorEvaluationSeriesPoint[];
  quantile_returns?: FactorQuantileReturn[];
  matrix_preview?: unknown[];
  summary?: {
    symbolCount: number;
    rowCount: number;
    factorCount: number;
    universeMembers?: number;
    universe: string;
    startDate: string;
    endDate: string;
  };
  factors?: Array<{
    symbol: string;
    factor: string;
    quantile: number;
    count: number;
    validCount: number;
    mean: number;
    median: number;
    volatility: number;
  }>;
}

export interface CBondPoolItem {
  code: string;
  name: string;
  date: string;
  maturity: string;
  yield: number;
  price: number;
  duration: number;
}

export interface CBondRiskItem {
  date: string;
  metric: string;
  value: number;
}

export interface FuturesMainItem {
  contract_code: string;
  product: string;
  exchange: string;
  bar_date: string;
  close?: number | null;
  volume?: number | null;
  open_interest?: number | null;
  daysToExpiry?: number | null;
}

export interface FuturesContinuousResult {
  id: string;
  product: string;
  exchange: string;
  start_date: string;
  end_date: string;
  adjustment: string;
  contracts: number;
  fee_schedule_version: string;
  config: Record<string, unknown>;
  summary: {
    bars: number;
    rolls: number;
    totalVariationPnl: number;
    totalCommission: number;
    totalSlippage: number;
    totalNetPnl: number;
    maxMarginRequired: number;
    averageMarginRequired: number;
    cumulativeRollYield: number;
  };
  bars: Array<{
    trade_date: string;
    contract_code: string;
    raw_close: number;
    adjusted_close: number;
    margin_required: number;
    variation_pnl: number;
    commission: number;
    slippage: number;
    net_pnl: number;
    cumulative_net_pnl: number;
    is_roll: boolean | number;
    roll_gap?: number | null;
    roll_yield?: number | null;
  }>;
  rollEvents: Array<{
    id: string;
    trade_date: string;
    from_contract: string;
    to_contract: string;
    from_price: number;
    to_price: number;
    roll_gap: number;
    roll_yield: number;
    market_pnl: number;
    commission: number;
    slippage: number;
    net_pnl: number;
  }>;
}

export interface MaintenanceHistoryClearResult {
  status: "completed" | "ready" | "blocked";
  dryRun: boolean;
  force: boolean;
  message?: string;
  database?: Record<string, number>;
  deletedRows?: Record<string, number>;
  activeTasks?: string[];
  activeTaskCount?: number;
  runtime?: {
    filesRemoved: number;
    dirsRemoved: number;
    bytesRemoved: number;
    targets: string[];
  };
}
