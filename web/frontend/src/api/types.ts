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
  metrics: Record<string, number | null>;
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
