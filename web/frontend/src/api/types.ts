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
  fingerprint?: Record<string, unknown> | null;
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
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

export interface OptimizationRun {
  id: string;
  task_id?: string | null;
  project_id: string;
  status: string;
  parameters: Record<string, unknown>;
  result?: {
    parameterGrid?: Record<string, unknown[]>;
    candidateCount?: number;
    best?: Record<string, unknown> | null;
    candidates?: Array<Record<string, unknown>>;
  } | null;
  results_dir: string;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
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
  drawdownCurve?: ChartPoint[];
  validation?: BacktestValidation | null;
  experiment?: BacktestExperiment | null;
  error?: string | null;
}

export interface BacktestCompareResult {
  items: BacktestCompareItem[];
  rankings: Record<string, string[]>;
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

export interface PaperDailyReport {
  id: string;
  session_id: string;
  trade_date: string;
  schemaVersion?: number;
  sessionId?: string;
  tradeDate?: string;
  executionPolicy?: string;
  cash?: number;
  NAV?: number;
  dailyReturn?: number;
  cumulativeReturn?: number;
  excessReturn?: number;
  benchmark?: { symbol?: string | null; close?: number | null; dailyReturn?: number | null; return?: number | null };
  qa?: { passed?: boolean; severity?: string };
  rejectionReasons?: string[];
  warnings?: string[];
  fingerprint?: string;
  report?: Record<string, unknown>;
}

export interface InsightCapabilities {
  configured: boolean;
  provider?: string | null;
  model?: string | null;
  assetClasses: Array<"equity" | "crypto" | "crypto_future" | "future">;
  resolutions: string[];
  paperHandoffAssetClasses: string[];
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
  guardrail: { passed: boolean; adjusted: boolean; violations: string[] };
  paper_session_id?: string | null;
  paper_signal_id?: string | null;
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
    technical?: Record<string, unknown>;
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
  model?: string | null;
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
  disclaimer: string;
}

export interface AshareTechMarketEnvironmentItem {
  code: string;
  name: string;
  category?: "sector";
  keyword?: string;
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

export interface OrderMarkerPoint {
  time: string;
  side: "BUY" | "SELL";
  symbol: string;
  quantity: number;
  price: number;
  fillPrice?: number;
  fill_price?: number;
  equityValue?: number | null;
  priceValue?: number | null;
  tag?: string | null;
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
    fill_price?: number;
    status?: string;
  }>;
  orderMarkers?: OrderMarkerPoint[];
  order_markers?: OrderMarkerPoint[];
  metadata?: Record<string, unknown>;
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
  code: string;
  description: string;
  exchange: string;
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
