import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Upload,
  message
} from "antd";
import {
  CloudDownloadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
  SlidersOutlined
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";

import { api } from "../api";
import dayjs from "dayjs";
import type {
  AppSettings,
  AssetClassInfo,
  BacktestAdmissionResponse,
  BacktestResult,
  BacktestRun,
  BacktestValidationResponse,
  CBondPoolItem,
  CBondRiskItem,
  ChartData,
  DataQueryResult,
  DataProvider,
  DatabaseHealth,
  DependencyHealth,
  FactorEvaluationResult,
  FuturesMainItem,
  IndexMember,
  IndexMembersResult,
  MarketInfo,
  ObjectStoreItem,
  OptimizationRun,
  PaperDailyReport,
  PaperSession,
  PortfolioOptimizationResult,
  Project,
  ReportRecord,
  StrategyTemplate,
  Task,
} from "../api";
import { CompareRunsPanel } from "./compare";
import { BacktestCharts, RunsTable, StatusTag } from "../components";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { BacktestTrustPanel, StrategyAdmissionPanel, ValidationStatusTag } from "../components/backtests/BacktestTrustPanel";
import { candlestickOption } from "../charts/candlestick";
import { defaultBarPreviewValues, defaultSettings } from "../config/defaults";
import { useAsyncData } from "../hooks";
import { asRecord, detailText, shortValue } from "../utils/display";
import {
  defaultTemplateFor,
  defaultVenueFor,
  projectAssetClass,
  projectDataType,
  projectMarket,
  projectResolution,
  projectTemplate,
  projectVenue,
  strategyFields,
  templateDefaults
} from "../utils/strategy";

const A_SHARE_BACKTEST_SOURCE_OPTIONS = [
  { value: "tushare", label: "TuShare Pro" },
  { value: "akshare", label: "AKShare" },
  { value: "baostock", label: "Baostock" },
  { value: "adata", label: "AData" },
  { value: "eastmoney", label: "EastMoney" },
  { value: "sina", label: "Sina Finance" },
  { value: "efinance", label: "Efinance" },
  { value: "tencent", label: "Tencent" },
  { value: "tonghuashun", label: "TongHuaShun" },
  { value: "yfinance", label: "YFinance" }
];
const ISO_DATE_FORMAT = "YYYY-MM-DD";

function normalizeDateInput(value: string) {
  const text = String(value).trim();
  const match = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (!match) {
    return text;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1) {
    return text;
  }
  const dayOfMonth = new Date(year, month, 0).getDate();
  const normalizedDay = Math.min(day, dayOfMonth);
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(normalizedDay).padStart(2, "0")}`;
}

function isValidDate(value: unknown) {
  if (typeof value !== "string") return false;
  return dayjs(normalizeDateInput(value), ISO_DATE_FORMAT, true).isValid();
}

function dateRule(fieldLabel: string) {
  return {
    validator(_: unknown, value: unknown) {
      if (!value) {
        return Promise.resolve();
      }
      if (isValidDate(value)) {
        return Promise.resolve();
      }
      return Promise.reject(new Error(`${fieldLabel} must be a valid YYYY-MM-DD date.`));
    },
  };
}

function defaultBacktestSource(nextMarket: string) {
  return nextMarket === "china" ? "tushare" : "";
}

function defaultProviderForMarket(nextMarket: string, markets: MarketInfo[]) {
  return markets.find((item) => item.key === nextMarket)?.defaultProvider ??
    (nextMarket === "china" ? "tushare" : nextMarket === "hongkong" ? "akshare" : "yfinance");
}

function defaultSymbolText(assetClass: string, nextMarket: string) {
  if (assetClass === "crypto") return "BTCUSDT, ETHUSDT";
  if (assetClass === "future") return "GC, ES";
  if (nextMarket === "china") return "000001";
  if (nextMarket === "hongkong") return "00700";
  return "AAPL";
}

function marketCostParameters(nextMarket: string, feeModel?: string, slippageModel?: string) {
  if (nextMarket !== "china") return {};
  const zeroFees = feeModel === "zero";
  return {
    commissionRate: zeroFees ? 0 : 0.0001,
    minCommission: 0,
    stampTaxSell: zeroFees ? 0 : 0.0005,
    transferFeeRate: zeroFees ? 0 : 0.00001,
    slippageBps: slippageModel === "zero" ? 0 : 5.0
  };
}

function normalizeConfigValue(value: unknown): unknown {
  if (value === undefined) {
    return undefined;
  }
  if (value === null) {
    return null;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeConfigValue(item));
  }
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value === "object") {
    return Object.keys(value).sort().reduce<Record<string, unknown>>((acc, key) => {
      const next = normalizeConfigValue((value as Record<string, unknown>)[key]);
      if (next !== undefined) {
        acc[key] = next;
      }
      return acc;
    }, {});
  }
  return value;
}

function normalizeProjectConfig(config: Record<string, unknown> = {}) {
  return normalizeConfigValue(config) as Record<string, unknown>;
}

function projectConfigEqual(left: Record<string, unknown> | undefined, right: Record<string, unknown> | undefined) {
  return JSON.stringify(normalizeProjectConfig(left)) === JSON.stringify(normalizeProjectConfig(right));
}

function projectConfigForRun(values: any, selectedTemplate?: StrategyTemplate) {
  const template = selectedTemplate;
  const templateDefaultsFromForm = templateDefaults(template);
  const mergedParameters = {
    ...templateDefaultsFromForm,
    ...(values.parameters || {})
  };
  return {
    assetClass: values.assetClass,
    market: values.market,
    venue: values.venue,
    resolution: values.resolution,
    dataType: values.dataType,
    templateKey: values.templateKey,
    source: values.source,
    symbol: values.symbol,
    start: normalizeDateInput(values.start),
    end: normalizeDateInput(values.end),
    benchmarkSymbol: values.benchmarkSymbol,
    cash: values.cash,
    feeModel: values.feeModel,
    slippageModel: values.slippageModel,
    dockerImage: values.dockerImage,
    parameters: mergedParameters
  };
}

function projectFormDefaults(project?: Project, templates: StrategyTemplate[] = [], settings?: AppSettings) {
  const safeSettings = settings || defaultSettings;
  const template = projectTemplate(project, templates);
  const defaults = templateDefaults(template);
  const market = String(project?.config?.market ?? safeSettings.defaultMarket ?? "china");
  const assetClass = String(project?.config?.assetClass ?? safeSettings.defaultAssetClass ?? "equity");
  const venue = String(project?.config?.venue ?? projectMarket(project) ?? market);
  const start = String(project?.config?.start ?? safeSettings.defaultStart ?? "2024-01-01");
  const end = String(project?.config?.end ?? safeSettings.defaultEnd ?? "2026-07-13");
  const cash = Number(project?.config?.cash ?? safeSettings.defaultCash);
  return {
    name: project?.name ?? "",
    assetClass,
    market,
    venue,
    resolution: String(project?.config?.resolution ?? safeSettings.defaultResolution ?? "daily"),
    dataType: String(project?.config?.dataType ?? safeSettings.defaultDataType ?? "trade"),
    templateKey: String(project?.config?.templateKey ?? template?.key ?? defaultTemplateFor(assetClass)),
    source: String(project?.config?.source ?? defaultBacktestSource(market)),
    symbol: String(project?.config?.symbol || defaultSymbolText(assetClass, market).split(",")[0]),
    start: start ? normalizeDateInput(start) : start,
    end: end ? normalizeDateInput(end) : end,
    benchmarkSymbol: String(project?.config?.benchmarkSymbol ?? (market === "china" ? "000300" : "SPY")),
    cash,
    feeModel: String(project?.config?.feeModel ?? "default"),
    slippageModel: String(project?.config?.slippageModel ?? "default"),
    dockerImage: String(project?.config?.dockerImage ?? safeSettings.dockerImage),
    parameters: {
      ...defaults,
      ...(project?.config?.parameters as Record<string, unknown> | undefined),
    },
  };
}

function providerSelectLabel(provider: DataProvider) {
  if (provider.disabledByDefault || provider.enabledByDefault === false) {
    return `${provider.name} (disabled)`;
  }
  if (provider.key === "tushare") return "TuShare Pro (default)";
  return provider.name;
}

function metricTruthy(value: unknown) {
  return value === true || String(value).toLowerCase() === "true";
}

export function Dashboard() {
  const navigate = useNavigate();
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const latest = runs.data[0];
  const activeTasks = tasks.data.filter((task) => ["created", "queued", "running"].includes(task.status)).length;
  const finishedRuns = runs.data.filter((run) => ["success", "succeeded", "failed", "cancelled"].includes(run.status));
  const successfulRuns = runs.data.filter((run) => run.status === "success" || run.status === "succeeded").length;
  const successRate = finishedRuns.length ? Math.round((successfulRuns / finishedRuns.length) * 100) : 0;
  const durations = runs.data.map((run) => run.duration_seconds).filter((value): value is number => typeof value === "number");
  const averageDuration = durations.length ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length) : 0;
  async function clearLocalHistory() {
    Modal.confirm({
      title: "Clear local history and cache?",
      content: "This will remove backtest/research history records and local runtime/cache files. Market data files and market data database entries will not be cleared.",
      okText: "Clear",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.clearLocalHistory({ force: true });
          message.success("Local history cleared");
          await Promise.all([runs.reload(), tasks.reload()]);
        } catch (error) {
          message.error((error as Error).message);
        }
      }
    });
  }
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Dashboard</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { runs.reload(); tasks.reload(); }}>Refresh</Button>
          <Button danger icon={<DeleteOutlined />} onClick={clearLocalHistory}>Clear Local History</Button>
        </Space>
      </div>
      <Card className="workflow-card" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<FolderOpenOutlined />} onClick={() => navigate("/projects")}>New Project</Button>
          <Button icon={<DatabaseOutlined />} onClick={() => navigate("/data")}>Fetch Data</Button>
          <Button icon={<PlayCircleOutlined />} onClick={() => navigate("/backtests")}>Run Backtest</Button>
          <Button icon={<ExperimentOutlined />} onClick={() => navigate("/paper")}>Paper Replay</Button>
          <Button icon={<SettingOutlined />} onClick={() => navigate("/settings")}>Settings</Button>
        </Space>
      </Card>
      <div className="grid">
        <Card><Statistic title="Backtests" value={runs.data.length} /></Card>
        <Card><Statistic title="Active Tasks" value={activeTasks} /></Card>
        <Card><Statistic title="Success Rate" value={successRate} suffix="%" /></Card>
        <Card><Statistic title="Average Duration" value={averageDuration} suffix="s" /></Card>
      </div>
      <div className="grid">
        <Card><Statistic title="Latest Net Profit" value={latest?.statistics?.["Net Profit"] ?? "N/A"} /></Card>
        <Card><Statistic title="Latest Sharpe" value={latest?.statistics?.["Sharpe Ratio"] ?? "N/A"} /></Card>
        <Card><Statistic title="Latest Status" value={latest?.status ?? "N/A"} /></Card>
        <Card><Statistic title="Latest Symbol" value={latest?.symbol ?? "N/A"} /></Card>
      </div>
      <Card title="Recent Backtests"><RunsTable runs={runs.data} onOpen={(id) => navigate(`/runs/${id}`)} /></Card>
    </>
  );
}

function MarketDataDownloader({
  compact = false,
  forcedAssetClass,
  forcedMarket,
  forcedVenue,
  forcedResolution,
  forcedDataType,
  showProvider = true,
  showAssetClass = true,
  showMarket = true,
  showVenue = true,
  showResolution = true,
  showDataType = true,
  showSourceSelect = true,
  showAdjust = true,
  showOverwrite = true,
  showApiKey = true,
  showLimitInput = true,
  showOutputSize = true,
  unboundedPreview = false
}: {
  compact?: boolean;
  forcedAssetClass?: string;
  forcedMarket?: string;
  forcedVenue?: string;
  forcedResolution?: string;
  forcedDataType?: string;
  showProvider?: boolean;
  showAssetClass?: boolean;
  showMarket?: boolean;
  showVenue?: boolean;
  showResolution?: boolean;
  showDataType?: boolean;
  showSourceSelect?: boolean;
  showAdjust?: boolean;
  showOverwrite?: boolean;
  showApiKey?: boolean;
  showLimitInput?: boolean;
  showOutputSize?: boolean;
  unboundedPreview?: boolean;
}) {
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const markets = useAsyncData<MarketInfo[]>(api.markets, []);
  const providers = useAsyncData<DataProvider[]>(api.dataProviders, []);
  const [symbolsText, setSymbolsText] = useState(defaultSymbolText(defaultBarPreviewValues.assetClass, defaultBarPreviewValues.market));
  const [symbolLookup, setSymbolLookup] = useState("");
  const [queryResult, setQueryResult] = useState<DataQueryResult>();
  const [securityInfo, setSecurityInfo] = useState<{ symbol: string; name: string; market: string; marketLabel?: string; hasLocalData?: boolean; identifierCount?: number; source?: string }>();
  const [queryLoading, setQueryLoading] = useState(false);
  const [fetchLoading, setFetchLoading] = useState(false);
  const previewRequestId = useRef(0);
  const [form] = Form.useForm();
  const selectedAssetClass = forcedAssetClass ?? (Form.useWatch("assetClass", form) || defaultBarPreviewValues.assetClass);
  const selectedMarket = forcedMarket ?? (Form.useWatch("market", form) || defaultBarPreviewValues.market);
  const selectedVenue = forcedVenue ?? (Form.useWatch("venue", form) || defaultVenueFor(selectedAssetClass, assetClasses.data, selectedMarket));
  const selectedResolution = forcedResolution ?? (Form.useWatch("resolution", form) || defaultBarPreviewValues.resolution);
  const selectedDataType = forcedDataType ?? (Form.useWatch("dataType", form) || defaultBarPreviewValues.dataType);
  const selectedProvider = Form.useWatch("provider", form) || defaultProviderForMarket(selectedMarket, markets.data);
  const querySymbol = symbolsText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)[0] || defaultSymbolText(selectedAssetClass, selectedMarket).split(",")[0];
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === selectedAssetClass);
  const chartOption = useMemo(() => candlestickOption(queryResult?.items ?? [], querySymbol), [queryResult?.items, querySymbol]);

  useEffect(() => {
    form.setFieldValue("assetClass", forcedAssetClass ?? form.getFieldValue("assetClass") ?? defaultBarPreviewValues.assetClass);
    form.setFieldValue("market", forcedMarket ?? form.getFieldValue("market") ?? defaultBarPreviewValues.market);
    form.setFieldValue("venue", forcedVenue ?? form.getFieldValue("venue") ?? defaultVenueFor(selectedAssetClass, assetClasses.data, selectedMarket));
    form.setFieldValue("resolution", forcedResolution ?? form.getFieldValue("resolution") ?? defaultBarPreviewValues.resolution);
    form.setFieldValue("dataType", forcedDataType ?? form.getFieldValue("dataType") ?? defaultBarPreviewValues.dataType);
    form.setFieldValue("source", form.getFieldValue("source") ?? defaultBarPreviewValues.source);
    form.setFieldValue("provider", form.getFieldValue("provider") ?? defaultProviderForMarket(selectedMarket, markets.data));
  }, [assetClasses.data, forcedAssetClass, forcedDataType, forcedMarket, forcedResolution, forcedVenue, form, markets.data, selectedAssetClass, selectedMarket]);

  useEffect(() => {
    const market = markets.data.find((item) => item.key === selectedMarket);
    const compatible = providers.data.filter((provider) => (
      provider.assetClasses?.includes(selectedAssetClass) ||
      (selectedAssetClass === "equity" && provider.markets.includes(selectedMarket))
    ));
    const enabled = compatible.filter((provider) => !(provider.disabledByDefault || provider.enabledByDefault === false));
    const marketDefault = market?.defaultProvider ?? defaultProviderForMarket(selectedMarket, markets.data);
    const fallback = enabled.find((provider) => provider.key === marketDefault)?.key ?? enabled[0]?.key;
    const selected = compatible.find((provider) => provider.key === selectedProvider);
    if (fallback && (!selected || selected.disabledByDefault || selected.enabledByDefault === false)) {
      form.setFieldValue("provider", fallback);
    } else if (market && selectedAssetClass === "equity" && !market.providers.includes(selectedProvider)) {
      form.setFieldValue("provider", fallback ?? market.defaultProvider);
    }
  }, [selectedAssetClass, selectedDataType, selectedMarket, selectedProvider, selectedResolution, selectedVenue, markets.data, providers.data, form]);

  function selectedSymbols() {
    const symbols = Array.from(new Set(symbolsText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)));
    if (symbols.length === 0) {
      message.error("Select or enter at least one symbol");
      return [];
    }
    return symbols;
  }

  async function loadSecurityInfo(symbol: string): Promise<{ symbol: string; name: string; market: string; marketLabel?: string; hasLocalData?: boolean; identifierCount?: number; source?: string }> {
    try {
      const [search, identifiers] = await Promise.all([
        api.searchSecurities(selectedMarket, symbol),
        api.dataIdentifiers(symbol).catch(() => ({ symbol, items: [], count: 0 }))
      ]);
      const matched = search.items.find((item) => item.symbol === symbol) ?? search.items[0];
      return {
        symbol,
        name: matched?.name ?? symbol,
        market: matched?.market ?? selectedMarket,
        marketLabel: matched?.marketLabel,
        hasLocalData: matched?.hasLocalData,
        identifierCount: identifiers.count,
        source: identifiers.items[0]?.source ? String(identifiers.items[0].source) : undefined
      };
    } catch {
      return { symbol, name: symbol, market: selectedMarket };
    }
  }

  async function queryLocalBars(values: any, symbol: string) {
    return api.queryData({
      source: values.source ?? "database",
      symbol,
      assetClass: selectedAssetClass,
      market: selectedMarket,
      venue: selectedVenue,
      resolution: selectedResolution,
      dataType: selectedDataType,
      adjust: values.adjust,
      startDate: values.startDate,
      endDate: values.endDate,
      limit: unboundedPreview ? 0 : values.limit ?? defaultBarPreviewValues.limit
    });
  }

  async function previewMarketData(values: any) {
    const [symbol] = selectedSymbols();
    if (!symbol) return;
    const requestId = ++previewRequestId.current;
    setQueryLoading(true);
    setQueryResult(undefined);
    setSecurityInfo(undefined);
    try {
      const security = await loadSecurityInfo(symbol);
      if (requestId !== previewRequestId.current) return;
      setSecurityInfo(security);
      let result = await queryLocalBars(values, symbol);
      if (requestId !== previewRequestId.current) return;
      if (result.enabled && result.items.length === 0 && selectedMarket === "china" && values.provider === "tushare") {
        message.info(`No local MySQL bars for ${symbol}; fetching from TuShare Pro and saving locally.`);
        await api.fetchData({
          symbol,
          assetClass: selectedAssetClass,
          market: selectedMarket,
          venue: selectedVenue,
          resolution: selectedResolution,
          dataType: selectedDataType,
          provider: "tushare",
          apiKey: values.apiKey,
          outputsize: values.outputsize ?? "compact",
          startDate: values.startDate,
          endDate: values.endDate,
          adjust: values.adjust,
          overwrite: Boolean(values.overwrite)
        });
        if (requestId !== previewRequestId.current) return;
        result = await queryLocalBars(values, symbol);
        if (requestId !== previewRequestId.current) return;
      }
      setQueryResult(result);
      if (!result.enabled) {
        message.warning(result.error ?? "Selected local data store is unavailable.");
      } else if (result.items.length === 0) {
        message.warning(`No local MySQL bars found for ${symbol}.`);
      }
    } catch (error) {
      if (requestId === previewRequestId.current) {
        message.error((error as Error).message);
      }
    } finally {
      if (requestId === previewRequestId.current) {
        setQueryLoading(false);
      }
    }
  }

  async function fetchMarketData(values: any) {
    const symbols = selectedSymbols();
    if (symbols.length === 0) return;
    setFetchLoading(true);
    try {
      const task = await api.fetchBatchData({
        symbols,
        assetClass: selectedAssetClass,
        market: selectedMarket,
        venue: selectedVenue,
        resolution: selectedResolution,
        dataType: selectedDataType,
        provider: values.provider,
        apiKey: values.apiKey,
        outputsize: values.outputsize ?? "compact",
        startDate: values.startDate,
        endDate: values.endDate,
        adjust: values.adjust,
        overwrite: Boolean(values.overwrite)
      });
      message.success(`Data fetch queued: ${task.id}`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setFetchLoading(false);
    }
  }

  const marketProviders = providers.data.filter((provider) => (
    provider.assetClasses?.includes(selectedAssetClass) ||
    (selectedAssetClass === "equity" && provider.markets.includes(selectedMarket))
  ));
  const venueOptions = selectedAssetInfo?.venues.map((venue) => ({ value: venue, label: venue })) ?? [];
  const resolutionOptions = ["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }));
  const dataTypeOptions = (selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }));

  return (
    <Card title={compact ? "Market Data" : "Market Data Preview & Download"}>
      <Form
        form={form}
        layout="vertical"
        onFinish={fetchMarketData}
        initialValues={{
          source: defaultBarPreviewValues.source,
          assetClass: forcedAssetClass ?? defaultBarPreviewValues.assetClass,
          market: forcedMarket ?? defaultBarPreviewValues.market,
          venue: forcedVenue ?? defaultBarPreviewValues.venue,
          resolution: forcedResolution ?? defaultBarPreviewValues.resolution,
          dataType: forcedDataType ?? defaultBarPreviewValues.dataType,
          provider: defaultBarPreviewValues.providerSource,
          outputsize: "compact",
          adjust: defaultBarPreviewValues.adjust,
          startDate: defaultBarPreviewValues.startDate,
          endDate: defaultBarPreviewValues.endDate,
          limit: defaultBarPreviewValues.limit,
          overwrite: false
        }}
      >
        <div className="field-grid six">
          {showSourceSelect && (
            <Form.Item name="source" label="Preview Store">
              <Select
                options={[
                  { value: "database", label: "Local MySQL" },
                  { value: "clickhouse", label: "ClickHouse" },
                  { value: "duckdb", label: "DuckDB Parquet" }
                ]}
              />
            </Form.Item>
          )}
          {showAssetClass && (
            <Form.Item name="assetClass" label="Asset Class">
              <Select
                disabled={Boolean(forcedAssetClass)}
                options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))}
                onChange={(value) => {
                  const nextVenue = defaultVenueFor(value, assetClasses.data, selectedMarket);
                  form.setFieldsValue({
                    venue: nextVenue,
                    provider: value === "crypto" ? "binance" : defaultProviderForMarket(selectedMarket, markets.data)
                  });
                  setSymbolsText(defaultSymbolText(value, selectedMarket));
                }}
              />
            </Form.Item>
          )}
          {showMarket && (
            <Form.Item name="market" label="Market">
              <Select
                disabled={Boolean(forcedMarket)}
                options={markets.data.map((item) => ({ value: item.key, label: item.name }))}
                onChange={(value) => {
                  const nextVenue = selectedAssetClass === "equity" ? value : defaultVenueFor(selectedAssetClass, assetClasses.data, value);
                  form.setFieldsValue({ venue: nextVenue, provider: defaultProviderForMarket(value, markets.data) });
                  setSymbolsText(defaultSymbolText(selectedAssetClass, value));
                }}
              />
            </Form.Item>
          )}
          {showVenue && (
            <Form.Item name="venue" label="Venue">
              <Select disabled={Boolean(forcedVenue) || selectedAssetClass === "equity"} options={venueOptions} />
            </Form.Item>
          )}
          {showResolution && (
            <Form.Item name="resolution" label="Resolution">
              <Select disabled={Boolean(forcedResolution)} options={resolutionOptions} />
            </Form.Item>
          )}
          {showDataType && (
            <Form.Item name="dataType" label="Data Type">
              <Select disabled={Boolean(forcedDataType)} options={dataTypeOptions} />
            </Form.Item>
          )}
          {showProvider && (
            <Form.Item name="provider" label="Provider">
              <Select
                options={marketProviders.map((provider) => ({
                  value: provider.key,
                  label: providerSelectLabel(provider),
                  disabled: provider.disabledByDefault || provider.enabledByDefault === false
                }))}
              />
            </Form.Item>
          )}
          {showAdjust && (
            <Form.Item name="adjust" label="Adjust">
              <Select options={[{ value: "raw", label: "Raw" }, { value: "qfq", label: "QFQ" }, { value: "hfq", label: "HFQ" }]} />
            </Form.Item>
          )}
          <Form.Item
            name="startDate"
            label="Start"
            rules={[{ required: true, message: "Start date is required" }, dateRule("Start date")]}
          >
            <DateStringPicker testId="market-data-start-input" />
          </Form.Item>
          <Form.Item
            name="endDate"
            label="End"
            rules={[
              { required: true, message: "End date is required" },
              dateRule("End date"),
              ({ getFieldValue }) => ({
                validator(_, value) {
                  const start = getFieldValue("startDate");
                  if (!value || !start) return Promise.resolve();
                  if (!isValidDate(start) || !isValidDate(value)) return Promise.resolve();
                  if (dayjs(value).isBefore(dayjs(start))) {
                    return Promise.reject(new Error("End date must be on or after start date"));
                  }
                  return Promise.resolve();
                }
              })
            ]}
          >
            <DateStringPicker testId="market-data-end-input" />
          </Form.Item>
          {showLimitInput && <Form.Item name="limit" label="Preview Rows"><InputNumber min={1} max={5000} style={{ width: "100%" }} /></Form.Item>}
          {showOutputSize && (
            <Form.Item name="outputsize" label="Output Size">
              <Select disabled={selectedProvider !== "alpha_vantage"} options={[{ value: "compact" }, { value: "full" }]} />
            </Form.Item>
          )}
          {(showApiKey && (selectedProvider === "alpha_vantage")) && (
            <Form.Item name="apiKey" label="API Key"><Input.Password placeholder="or environment variable" /></Form.Item>
          )}
          {showOverwrite && <Form.Item name="overwrite" valuePropName="checked" label=" "><Checkbox>Overwrite local files</Checkbox></Form.Item>}
        </div>
        <Space.Compact style={{ width: "100%", marginBottom: 12 }}>
          <SecuritySearch
            assetClass={selectedAssetClass}
            market={selectedMarket}
            value={symbolLookup}
            onChange={setSymbolLookup}
            onSelectSecurity={(security) => {
              const existing = selectedSymbols();
              setSymbolsText(Array.from(new Set([...existing, security.symbol])).join(", "));
              setSymbolLookup("");
            }}
            placeholder="搜索代码 / 公司 / 拼音"
            style={{ width: 320 }}
          />
          <Input
            value={symbolsText}
            onChange={(event) => setSymbolsText(event.target.value)}
            placeholder={selectedAssetClass === "crypto" ? "BTCUSDT, ETHUSDT" : selectedAssetClass === "future" ? "GC, ES" : selectedMarket === "china" ? "600519, 000001" : selectedMarket === "hongkong" ? "00700, 00941" : "AAPL, MSFT"}
          />
          <Button data-testid="market-data-preview-button" icon={<ReloadOutlined />} loading={queryLoading} onClick={() => previewMarketData(form.getFieldsValue())}>Preview</Button>
          <Button data-testid="market-data-fetch-button" type="primary" icon={<CloudDownloadOutlined />} htmlType="submit" loading={fetchLoading}>Download</Button>
        </Space.Compact>
      </Form>
      {securityInfo && (
        <Card size="small" title="Company Info" style={{ marginBottom: 12 }}>
          <Space wrap>
            <Tag color="blue">{securityInfo.symbol}</Tag>
            <Tag>{securityInfo.name}</Tag>
            <Tag color={securityInfo.market === "china" ? "red" : securityInfo.market === "hongkong" ? "green" : "blue"}>{securityInfo.marketLabel ?? securityInfo.market}</Tag>
            <Tag color={securityInfo.hasLocalData ? "success" : "warning"}>{securityInfo.hasLocalData ? "local data" : "local data pending"}</Tag>
            {securityInfo.identifierCount !== undefined && <Tag>{securityInfo.identifierCount} identifiers</Tag>}
            {securityInfo.source && <Tag>{securityInfo.source}</Tag>}
          </Space>
        </Card>
      )}
      {queryResult && !queryResult.enabled && <Alert style={{ marginBottom: 12 }} type="warning" showIcon message={queryResult.error ?? "Selected data source is unavailable."} />}
      {queryResult?.enabled && queryResult.message && <Alert style={{ marginBottom: 12 }} type="info" showIcon message={queryResult.message} />}
      {queryResult?.enabled && queryResult.items.length === 0 && <Alert style={{ marginBottom: 12 }} type="info" showIcon message="No local bars matched the selected filters. Use Download to fetch and save data locally." />}
      {queryResult?.enabled && queryResult.items.length > 0 && (
        <>
          <Space wrap style={{ marginBottom: 12 }}>
            <Tag color="blue">{queryResult.source ?? "data"}</Tag>
            <Tag>{queryResult.count} bars</Tag>
            <Tag>{`${queryResult.items[0].timestamp.slice(0, 10)} -> ${queryResult.items[queryResult.items.length - 1].timestamp.slice(0, 10)}`}</Tag>
            <Tag>{queryResult.items[0].source}</Tag>
          </Space>
          <ReactECharts style={{ height: compact ? 360 : 540, marginBottom: 8 }} option={chartOption} />
        </>
      )}
      {selectedAssetClass !== "equity" && selectedProvider !== "binance" && (
        <Alert style={{ marginBottom: 12 }} type="warning" showIcon message="This asset class currently uses local LEAN files or CSV import unless Binance crypto daily is selected." />
      )}
      <Alert
        style={{ marginTop: 12 }}
        type="info"
        showIcon
        message="Public data sources may throttle or change. Equity A/HK support is daily-bar only; crypto import is daily Binance spot in this version; futures should use local LEAN files or CSV import with verified contract metadata."
      />
    </Card>
  );
}

export function ProjectsPage() {
  const navigate = useNavigate();
  const [createForm] = Form.useForm();
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const markets = useAsyncData<MarketInfo[]>(api.markets, []);
  const settings = useAsyncData(api.settings, defaultSettings);
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const [form] = Form.useForm();
  const [symbols, setSymbols] = useState<string[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [saving, setSaving] = useState(false);
  const selectedAssetClass = Form.useWatch("assetClass", form) || settings.data.defaultAssetClass;
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === selectedAssetClass);
  const selectedMarket = Form.useWatch("market", form) || settings.data.defaultMarket;
  const selectedVenue = Form.useWatch("venue", form) || selectedMarket;
  const selectedResolution = Form.useWatch("resolution", form) || settings.data.defaultResolution;
  const selectedDataType = Form.useWatch("dataType", form) || settings.data.defaultDataType;
  const selectedTemplateKey = Form.useWatch("templateKey", form);
  const selectedProject = projects.data.find((item) => item.id === selectedProjectId);
  const selectedTemplate = templates.data.find((item) => item.key === (selectedTemplateKey || selectedProject?.config?.templateKey));

  useEffect(() => {
    if (selectedProjectId && projects.data.some((project) => project.id === selectedProjectId)) {
      return;
    }
    if (projects.data.length === 0) {
      setSelectedProjectId(undefined);
      return;
    }
    setSelectedProjectId(projects.data[0].id);
  }, [projects.data, selectedProjectId]);

  useEffect(() => {
    if (!selectedProject) return;
    const nextValues = projectFormDefaults(selectedProject, templates.data, settings.data);
    if (nextValues.venue === "undefined" && nextValues.market) {
      nextValues.venue = nextValues.market;
    }
    form.setFieldsValue(nextValues);
  }, [form, selectedProject, settings.data, templates.data, selectedProject?.id]);

  useEffect(() => {
    api.symbols(selectedMarket, selectedAssetClass, selectedVenue, selectedResolution, selectedDataType)
      .then((result) => setSymbols(result.symbols))
      .catch((error) => message.error((error as Error).message));
  }, [selectedAssetClass, selectedDataType, selectedMarket, selectedResolution, selectedVenue]);

  async function createProject(values: any) {
    const template = templates.data.find((item) => item.key === values.templateKey);
    const project = await api.createProject({
      name: values.name,
      language: "Python",
      algorithmClass: values.algorithmClass,
      templateKey: values.templateKey,
      assetClass: values.assetClass,
      market: values.market,
      venue: values.assetClass === "equity" ? values.market : values.venue,
      resolution: values.resolution,
      dataType: values.dataType,
      parameters: templateDefaults(template)
    });
    message.success("Project created");
    await projects.reload();
    setSelectedProjectId(project.id);
    createForm.resetFields();
  }

  function parseProjectConfig(values: any) {
    const template = selectedTemplate || projectTemplate(selectedProject, templates.data);
    return {
      ...projectConfigForRun(values, template)
    };
  }

  async function saveProject() {
    if (!selectedProject) return;
    setSaving(true);
    try {
      const values = form.getFieldsValue(true);
      const config = parseProjectConfig(values);
      const payload = {
        name: String(values.name ?? selectedProject.name),
        config
      };
      await api.updateProject(selectedProject.id, payload);
      message.success("Project configuration saved");
      await projects.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function backtestValuesForRequest(values: any) {
    const template = selectedTemplate || projectTemplate(selectedProject, templates.data);
    const config = projectConfigForRun(values, template);
    return {
      runName: `${values.symbol} ${config.start} -> ${config.end}`,
      projectId: selectedProject?.id,
      assetClass: config.assetClass,
      market: config.market,
      venue: config.venue || config.market,
      resolution: config.resolution,
      dataType: config.dataType,
      source: config.source,
      symbol: String(values.symbol ?? "").trim().toUpperCase(),
      start: config.start,
      end: config.end,
      cash: Number(values.cash),
      benchmarkSymbol: config.benchmarkSymbol,
      feeModel: config.feeModel,
      slippageModel: config.slippageModel,
      dockerImage: config.dockerImage,
      parameters: {
        ...config.parameters,
        benchmarkSymbol: config.benchmarkSymbol,
        feeModel: config.feeModel,
        slippageModel: config.slippageModel,
        source: config.source,
        ...marketCostParameters(config.market, config.feeModel, config.slippageModel)
      },
      baseConfig: config
    };
  }

  async function runBacktest() {
    if (!selectedProject) return;
    if (submitting) return;
    const values = form.getFieldsValue(true);
    const request = backtestValuesForRequest(values);
    if (!request.symbol) {
      message.error("Symbol is required.");
      return;
    }
    if (!request.start || !isValidDate(request.start) || !request.end || !isValidDate(request.end)) {
      message.error("Please set valid start and end dates.");
      return;
    }
    if (dayjs(request.end).isBefore(dayjs(request.start))) {
      message.error("End date must be on or after start date");
      return;
    }
    setSubmitting(true);
    try {
      const nextConfig = parseProjectConfig(values);
      const shouldClone = !projectConfigEqual((selectedProject.config as Record<string, unknown> | undefined), nextConfig);
      let targetProjectId = selectedProject.id;
      if (shouldClone) {
        const copied = await api.cloneProject(selectedProject.id, {
          name: `${selectedProject.name} (copy ${dayjs().format("YYYYMMDD-HHmmss")})`,
          config: nextConfig,
        });
        targetProjectId = copied.id;
        await projects.reload();
        setSelectedProjectId(copied.id);
        message.success("Saved configuration as a new project.");
      }
      const run = await api.createBacktest({
        symbol: request.symbol,
        name: request.runName,
        assetClass: request.assetClass,
        market: request.market,
        venue: request.venue,
        resolution: request.resolution,
        dataType: request.dataType,
        start: request.start,
        end: request.end,
        cash: request.cash,
        source: request.source,
        benchmarkSymbol: request.benchmarkSymbol,
        feeModel: request.feeModel,
        slippageModel: request.slippageModel,
        dockerImage: request.dockerImage,
        projectId: targetProjectId,
        parameters: request.parameters,
      });
      message.success("Backtest queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function deleteProject(project: Project) {
    Modal.confirm({
      title: `Delete ${project.name}?`,
      content: "This will delete the project and its related runs, reports, tasks, and runtime files.",
      okButtonProps: { danger: true },
      onOk: async () => {
        await api.deleteProject(project.id);
        message.success("Project deleted");
        await projects.reload();
      }
    });
  }
  const projectRuns = runs.data.filter((run) => run.project_id === selectedProject?.id);
  const projectTasks = tasks.data.filter((task) => task.project_id === selectedProject?.id);

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Projects</h1>
        <Button icon={<ReloadOutlined />} onClick={projects.reload}>Refresh</Button>
      </div>
      <Card title="Create Project">
        <Form form={createForm} layout="vertical" onFinish={createProject} initialValues={{ assetClass: "equity", market: "china", venue: "china", resolution: "daily", dataType: "trade", templateKey: "ema_cross" }}>
          <div className="field-grid">
            <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="A Share RSI Strategy" /></Form.Item>
            <Form.Item name="assetClass" label="Asset Class">
              <Select
                data-testid="project-asset-select"
                virtual={false}
                options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))}
                onChange={(value) => {
                  createForm.setFieldValue("templateKey", defaultTemplateFor(value));
                  createForm.setFieldValue("venue", defaultVenueFor(value, assetClasses.data, createForm.getFieldValue("market") || "usa"));
                }}
              />
            </Form.Item>
            <Form.Item name="market" label="Market"><Select data-testid="project-market-select" virtual={false} options={markets.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select data-testid="project-venue-select" virtual={false} disabled={selectedAssetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select data-testid="project-resolution-select" virtual={false} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select data-testid="project-data-type-select" virtual={false} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="templateKey" label="Strategy"><Select data-testid="project-template-select" virtual={false} options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="algorithmClass" label="Class"><Input placeholder="Auto-generated if empty" /></Form.Item>
          </div>
          <Button type="primary" htmlType="submit">Create</Button>
        </Form>
      </Card>
      {selectedProject && (
        <Card title="Project Configuration" style={{ marginTop: 16 }}>
          <div className="toolbar" style={{ marginBottom: 12 }}>
            <h2 className="page-title" style={{ margin: 0 }}>Current Project: {selectedProject.name}</h2>
            <Select
              style={{ width: 320 }}
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              options={projects.data.map((project) => ({ value: project.id, label: project.name }))}
            />
          </div>
          <Form form={form} layout="vertical" initialValues={projectFormDefaults(selectedProject, templates.data, settings.data)} key={`${selectedProject.id}-${templates.data.length}-${settings.data.defaultMarket}`}>
            <div className="field-grid">
              <Form.Item name="name" label="Project Name" rules={[{ required: true }]}><Input placeholder="Project name" /></Form.Item>
              <Form.Item name="assetClass" label="Asset">
                <Select
                  data-testid="project-asset-select"
                  virtual={false}
                  options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))}
                  onChange={(value) => {
                    form.setFieldValue("templateKey", defaultTemplateFor(value));
                    form.setFieldValue("venue", defaultVenueFor(value, assetClasses.data, form.getFieldValue("market") || "usa"));
                  }}
                />
              </Form.Item>
              <Form.Item name="market" label="Market">
                <Select
                  data-testid="project-market-select"
                  virtual={false}
                  options={markets.data.map((item) => ({ value: item.key, label: item.name }))}
                  onChange={(value) => {
                    form.setFieldValue("source", defaultBacktestSource(value));
                    form.setFieldValue("benchmarkSymbol", value === "china" ? "000300" : "SPY");
                  }}
                />
              </Form.Item>
              <Form.Item name="venue" label="Venue">
                <Select
                  data-testid="project-venue-select"
                  virtual={false}
                  disabled={selectedAssetClass === "equity"}
                  options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))}
                />
              </Form.Item>
              <Form.Item name="resolution" label="Resolution">
                <Select data-testid="project-resolution-select" virtual={false} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="dataType" label="Data Type">
                <Select data-testid="project-data-type-select" virtual={false} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="templateKey" label="Strategy"><Select data-testid="project-template-select" virtual={false} options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
              <Form.Item name="source" label="Data Source">
                {selectedMarket === "china" ? (
                  <Select virtual={false} showSearch optionFilterProp="label" options={A_SHARE_BACKTEST_SOURCE_OPTIONS} />
                ) : (
                  <Input placeholder="optional provider source" />
                )}
              </Form.Item>
              <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={selectedAssetClass} market={selectedMarket} localSymbols={symbols} /></Form.Item>
              <Form.Item name="start" label="Start" rules={[{ required: true, message: "Start date is required" }, dateRule("Start date")]}><DateStringPicker /></Form.Item>
              <Form.Item name="end" label="End" rules={[{ required: true, message: "End date is required" }, dateRule("End date"), ({ getFieldValue }) => ({ validator(_, value) {
                const start = getFieldValue("start");
                if (!value || !start || !isValidDate(start) || !isValidDate(value)) return Promise.resolve();
                if (dayjs(value).isBefore(dayjs(start))) {
                  return Promise.reject(new Error("End date must be on or after start date"));
                }
                return Promise.resolve();
              }})]}><DateStringPicker /></Form.Item>
              <Form.Item name="cash" label="Cash">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="dockerImage" label="Docker Image"><Input /></Form.Item>
              <Form.Item name="benchmarkSymbol" label="Benchmark" rules={[{ required: true, message: "Benchmark is required" }]}><Input /></Form.Item>
              <Form.Item name="feeModel" label="Fee Model"><Select virtual={false} options={[{ value: "default", label: "Default A-share statutory" }, { value: "zero", label: "Zero Fees" }]} /></Form.Item>
              <Form.Item name="slippageModel" label="Slippage Model"><Select virtual={false} options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Slippage" }]} /></Form.Item>
            </div>
            {selectedTemplate && <div className="field-grid">{strategyFields(selectedTemplate)}</div>}
            <Space wrap>
              <Button icon={<ReloadOutlined />} type="default" onClick={saveProject} loading={saving} disabled={saving || !selectedProjectId}>Save Configuration</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={runBacktest} loading={submitting} disabled={submitting || !selectedProjectId}>Run Backtest</Button>
            </Space>
          </Form>
          <div className="grid" style={{ marginTop: 16 }}>
            <Card><Statistic title="Backtests" value={projectRuns.length} /></Card>
            <Card><Statistic title="Tasks" value={projectTasks.length} /></Card>
            <Card><Statistic title="Symbol" value={String(form.getFieldValue("symbol") || "-")} /></Card>
            <Card><Statistic title="Local Symbols" value={symbols.length} /></Card>
          </div>
          <Card title="Project Backtests" style={{ marginTop: 16 }}><RunsTable runs={projectRuns} onOpen={(id) => navigate(`/runs/${id}`)} /></Card>
        </Card>
      )}
      <Card title="Projects" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          size="small"
          dataSource={projects.data}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Name", dataIndex: "name" },
            { title: "Asset", render: (_, project) => String(project.config?.assetClass ?? "equity") },
            { title: "Venue", render: (_, project) => String(project.config?.venue ?? project.config?.market ?? "usa") },
            { title: "Strategy", render: (_, project) => String(project.config?.templateKey ?? "custom") },
            { title: "Updated", dataIndex: "updated_at" },
            {
              title: "Actions",
              width: 190,
              render: (_, project) => (
                <Space>
                  <Button size="small" type="primary" onClick={() => setSelectedProjectId(project.id)}>Open</Button>
                  <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteProject(project)} />
                </Space>
              )
            }
          ]}
        />
      </Card>
    </>
  );
}

export function DataPage() {
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const [csvForm] = Form.useForm();
  const csvAssetClass = Form.useWatch("assetClass", csvForm) || "equity";
  const csvMarket = Form.useWatch("market", csvForm) || "china";

  async function importCsv(values: any) {
    const file = values.file?.fileList?.[0]?.originFileObj;
    if (!file) return message.error("Choose a CSV file");
    const formData = new FormData();
    formData.append("symbol", values.symbol ?? "");
    formData.append("assetClass", values.assetClass ?? "equity");
    formData.append("market", values.market ?? "usa");
    formData.append("venue", "");
    formData.append("dataType", "trade");
    formData.append("overwrite", "false");
    formData.append("dateCol", "timestamp");
    formData.append("openCol", "open");
    formData.append("highCol", "high");
    formData.append("lowCol", "low");
    formData.append("closeCol", "close");
    formData.append("volumeCol", "volume");
    formData.append("file", file);
    await api.importCsv(formData);
    message.success("CSV imported");
    csvForm.resetFields();
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Data Library</h1></div>
      <MarketDataDownloader />
      <Card title="Import CSV" style={{ marginTop: 16 }}>
        <Form form={csvForm} layout="vertical" onFinish={importCsv} initialValues={{ assetClass: "equity", market: "china" }}>
          <div className="field-grid three">
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={csvAssetClass} market={csvMarket} /></Form.Item>
            <Form.Item name="assetClass" label="Asset Class"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          </div>
          <Space wrap>
            <Form.Item name="file" label="CSV" rules={[{ required: true }]}><Upload beforeUpload={() => false} maxCount={1}><Button>Choose CSV</Button></Upload></Form.Item>
            <Button type="primary" htmlType="submit">Import</Button>
          </Space>
        </Form>
      </Card>
    </>
  );
}

export function BacktestsPage() {
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const settings = useAsyncData<AppSettings>(api.settings, defaultSettings);
  const [filters, setFilters] = useState<{ name?: string; status?: string; market?: string; projectId?: string; symbol?: string }>({});
  const loadRuns = useCallback(() => api.backtests(filters), [filters]);
  const runs = useAsyncData(loadRuns, []);
  const [form] = Form.useForm();
  const [historyForm] = Form.useForm();
  const [assetClass, setAssetClass] = useState("equity");
  const [market, setMarket] = useState("usa");
  const [venue, setVenue] = useState("usa");
  const [resolution, setResolution] = useState("daily");
  const [dataType, setDataType] = useState("trade");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>();
  const [submitting, setSubmitting] = useState(false);

  const selectedProject = projects.data.find((item) => item.id === selectedProjectId);
  const selectedTemplate = projectTemplate(selectedProject, templates.data);
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === assetClass);

  useEffect(() => {
    setAssetClass(settings.data.defaultAssetClass);
    setMarket(settings.data.defaultMarket);
    setVenue(settings.data.defaultVenue);
    setResolution(settings.data.defaultResolution);
    setDataType(settings.data.defaultDataType);
    form.setFieldsValue({
      assetClass: settings.data.defaultAssetClass,
      market: settings.data.defaultMarket,
      venue: settings.data.defaultVenue,
      resolution: settings.data.defaultResolution,
      dataType: settings.data.defaultDataType
    });
  }, [form, settings.data.defaultAssetClass, settings.data.defaultDataType, settings.data.defaultMarket, settings.data.defaultResolution, settings.data.defaultVenue]);

  useEffect(() => {
    api.symbols(market, assetClass, venue, resolution, dataType).then((result) => setSymbols(result.symbols)).catch((error) => message.error((error as Error).message));
  }, [assetClass, dataType, market, resolution, venue]);

  async function submit(values: any) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const run = await api.createBacktest({
        ...values,
        symbol: String(values.symbol ?? "").trim().toUpperCase(),
        assetClass,
        market,
        venue,
        resolution,
        dataType,
        projectId: values.projectId,
        parameters: {
          ...(values.parameters ?? {}),
          ...marketCostParameters(market, values.feeModel, values.slippageModel),
          benchmarkSymbol: values.benchmarkSymbol,
          feeModel: values.feeModel,
          slippageModel: values.slippageModel,
          source: values.source
        }
      });
      message.success("Backtest queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  const runsForDisplay = runs.data.filter((run) => {
    const name = String((filters as any).name ?? "").trim().toLowerCase();
    const marketFilter = String((filters as any).market ?? "").trim().toLowerCase();
    const runMarket = String(run.parameters?.market ?? run.venue ?? "").toLowerCase();
    return (!name || String(run.name ?? run.id).toLowerCase().includes(name)) &&
      (!marketFilter || runMarket === marketFilter);
  });

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Backtests</h1><Button icon={<ReloadOutlined />} onClick={runs.reload}>Refresh</Button></div>
      <Card title="New Backtest">
        <Form
          form={form}
          key={`${market}-${selectedProjectId ?? "none"}-${templates.data.length}`}
          layout="vertical"
          onFinish={submit}
          initialValues={{
            name: `Backtest ${symbols[0] ?? (settings.data.defaultMarket === "china" ? "000001" : "AAPL")}`,
            assetClass: settings.data.defaultAssetClass,
            market: settings.data.defaultMarket,
            venue: settings.data.defaultVenue,
            resolution: settings.data.defaultResolution,
            dataType: settings.data.defaultDataType,
            symbol: symbols[0] ?? (settings.data.defaultMarket === "china" ? "000001" : settings.data.defaultMarket === "hongkong" ? "00700" : "AAPL"),
            start: settings.data.defaultStart,
            end: settings.data.defaultEnd,
            cash: settings.data.defaultCash,
            benchmarkSymbol: settings.data.defaultMarket === "china" ? "000300" : "SPY",
            feeModel: "default",
            slippageModel: "default",
            source: defaultBacktestSource(settings.data.defaultMarket),
            dockerImage: settings.data.dockerImage,
            parameters: templateDefaults(selectedTemplate)
          }}
        >
          <div className="field-grid six">
            <Form.Item name="projectId" label="Project" rules={[{ required: true, message: "Project strategy is required" }]}><Select data-testid="backtest-project-select" virtual={false} showSearch optionFilterProp="label" allowClear onChange={(value) => { setSelectedProjectId(value); const project = projects.data.find((item) => item.id === value); if (project) { const nextMarket = projectMarket(project); const next = { assetClass: projectAssetClass(project), market: nextMarket, venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), benchmarkSymbol: nextMarket === "china" ? "000300" : "SPY", source: defaultBacktestSource(nextMarket), parameters: templateDefaults(projectTemplate(project, templates.data)) }; setAssetClass(next.assetClass); setMarket(next.market); setVenue(next.venue); setResolution(next.resolution); setDataType(next.dataType); form.setFieldsValue(next); } }} options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
            <Form.Item name="name" label="Backtest Name" rules={[{ required: true, message: "Backtest name is required" }]}><Input data-testid="backtest-name-input" /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select data-testid="backtest-asset-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { const nextVenue = defaultVenueFor(value, assetClasses.data, market); setAssetClass(value); setVenue(nextVenue); form.setFieldsValue({ venue: nextVenue }); }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select data-testid="backtest-market-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { setMarket(value); if (assetClass === "equity") { setVenue(value); form.setFieldValue("venue", value); } form.setFieldValue("benchmarkSymbol", value === "china" ? "000300" : "SPY"); form.setFieldValue("source", defaultBacktestSource(value)); }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} onChange={setVenue} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select data-testid="backtest-resolution-select" virtual={false} showSearch optionFilterProp="label" onChange={setResolution} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select data-testid="backtest-data-type-select" virtual={false} showSearch optionFilterProp="label" onChange={setDataType} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true, message: "Symbol is required" }]}><SecuritySearch data-testid="backtest-symbol-input" assetClass={assetClass} market={market} localSymbols={symbols} /></Form.Item>
            <Form.Item name="start" label="Start" rules={[{ required: true, message: "Start date is required" }, dateRule("Start date")]}><DateStringPicker testId="backtest-start-input" /></Form.Item>
            <Form.Item
              name="end"
              label="End"
              rules={[
                { required: true, message: "End date is required" },
                dateRule("End date"),
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const start = getFieldValue("start");
                    if (!value || !start || !isValidDate(start) || !isValidDate(value)) return Promise.resolve();
                    if (dayjs(value).isBefore(dayjs(start))) {
                      return Promise.reject(new Error("End date must be on or after start date"));
                    }
                    return Promise.resolve();
                  }
                })
              ]}
            >
              <DateStringPicker testId="backtest-end-input" />
            </Form.Item>
            <Form.Item
              name="cash"
              label="Cash"
              rules={[
                { required: true, message: "Initial cash is required" },
                {
                  validator(_, value) {
                    if (Number(value) > 0) return Promise.resolve();
                    return Promise.reject(new Error("Initial cash must be greater than 0"));
                  }
                }
              ]}
            >
              <InputNumber style={{ width: "100%" }} data-testid="backtest-cash-input" />
            </Form.Item>
            <Form.Item name="benchmarkSymbol" label="Benchmark" rules={[{ required: true, message: "Benchmark is required" }]}><Input data-testid="backtest-benchmark-input" /></Form.Item>
            <Form.Item name="feeModel" label="Fee Model"><Select data-testid="backtest-fee-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default A-share statutory" }, { value: "zero", label: "Zero Fees" }]} /></Form.Item>
            <Form.Item name="slippageModel" label="Slippage Model"><Select data-testid="backtest-slippage-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Slippage" }]} /></Form.Item>
            <Form.Item name="source" label="Data Source">
              {market === "china" ? (
                <Select data-testid="backtest-source-select" virtual={false} showSearch optionFilterProp="label" options={A_SHARE_BACKTEST_SOURCE_OPTIONS} />
              ) : (
                <Input data-testid="backtest-source-input" placeholder="optional provider source" />
              )}
            </Form.Item>
            <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
            {strategyFields(selectedTemplate)}
          </div>
          <Button data-testid="run-backtest-button" type="primary" icon={<PlayCircleOutlined />} htmlType="submit" loading={submitting} disabled={submitting}>Run</Button>
        </Form>
      </Card>
      <Card title="History" style={{ marginTop: 16 }}>
        <Form form={historyForm} layout="inline" style={{ marginBottom: 12 }} onFinish={(values) => setFilters(values)}>
          <Form.Item name="name" label="Name"><Input placeholder="Name" style={{ width: 180 }} /></Form.Item>
          <Form.Item name="status" label="Status"><Select data-testid="history-status-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Status" style={{ width: 150 }} options={["created", "queued", "running", "success", "failed", "cancelled"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="market" label="Market"><Select data-testid="history-market-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Market" style={{ width: 150 }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          <Form.Item name="projectId" label="Project"><Select data-testid="history-project-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Project" style={{ width: 220 }} options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
          <Form.Item name="symbol" label="Symbol"><SecuritySearch market="all" placeholder="代码 / 公司" style={{ width: 180 }} /></Form.Item>
          <Button htmlType="submit">Filter</Button>
          <Button onClick={() => { historyForm.resetFields(); setFilters({}); }}>Clear</Button>
        </Form>
        <RunsTable runs={runsForDisplay} onOpen={(id) => navigate(`/runs/${id}`)} />
      </Card>
    </>
  );
}

export function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<BacktestRun>();
  const [chart, setChart] = useState<ChartData>();
  const [result, setResult] = useState<BacktestResult>();
  const [trust, setTrust] = useState<BacktestValidationResponse>();
  const [admission, setAdmission] = useState<BacktestAdmissionResponse>();
  const [logs, setLogs] = useState("");
  const active = run ? ["created", "queued", "running"].includes(run.status) : false;
  const reload = useCallback(async () => {
    if (!id) return;
    const next = await api.backtest(id);
    setRun(next);
    setLogs((await api.logs(id)).logs);
    try {
      setTrust(await api.backtestValidation(id));
    } catch {
      setTrust(undefined);
    }
    try {
      setAdmission(await api.backtestAdmission(id));
    } catch {
      setAdmission(undefined);
    }
    if (next.result_json_path) setChart(await api.chartData(id));
    if (next.status === "success" || next.status === "succeeded") {
      try {
        setResult((await api.backtestResult(id)).result);
      } catch {
        setResult(undefined);
      }
    }
  }, [id]);
  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(reload, 1000);
    return () => window.clearInterval(timer);
  }, [active, reload]);
  async function cancelRun() {
    if (!id) return;
    const next = await api.cancelBacktest(id);
    setRun(next);
    message.success("Cancellation requested");
    await reload();
  }
  if (!run) return <Alert type="info" message="Loading run..." />;
  const validation = trust?.validation ?? run.validation ?? result?.performance?.validation;
  const experiment = trust?.experiment ?? run.experiment ?? result?.performance?.experiment;
  const fingerprint = trust?.fingerprint ?? run.fingerprint;
  const summaryMetrics = result?.summary_metrics ?? {};
  const sharpeMetric = summaryMetrics["Recomputed Sharpe"] ?? run.statistics?.["Sharpe Ratio"];
  const sharpeWarning = metricTruthy(summaryMetrics["Short Window Unstable"]);
  const metricCards = [
    { title: "Initial Cash", value: run.parameters?.initialCash ?? run.parameters?.initial_cash ?? run.parameters?.cash },
    { title: "End Equity", value: run.statistics?.["End Equity"] },
    { title: "Total Return", value: run.statistics?.["Net Profit"] ?? summaryMetrics["Total Return"] },
    { title: "Net Profit", value: run.statistics?.["Net Profit"] },
    { title: "Sharpe", value: sharpeMetric, warning: sharpeWarning },
    { title: "Drawdown", value: run.statistics?.["Drawdown"] ?? run.statistics?.["Max Drawdown"] },
    { title: "Total Trades", value: run.statistics?.["Total Trades"] ?? run.statistics?.["Total Orders"] ?? result?.orders?.length },
    { title: "VaR 95%", value: summaryMetrics["VaR 95%"] },
    { title: "Expected Shortfall 95%", value: summaryMetrics["Expected Shortfall 95%"] },
    { title: "Tracking Error", value: summaryMetrics["Computed Tracking Error"] },
    { title: "Information Ratio", value: summaryMetrics["Computed Information Ratio"] },
    { title: "Market Correlation", value: summaryMetrics["Market Correlation"] },
    { title: "Position HHI", value: summaryMetrics["Position HHI"] },
    { title: "Top Position Weight", value: summaryMetrics["Top Position Weight"] },
  ];
  const records = {
    orders: result?.orders ?? chart?.orders ?? [],
    trades: result?.trades ?? [],
    holdings: result?.holdings ?? []
  };
  const recordColumns = [
    { title: "Record", dataIndex: "record" },
    { title: "Field", dataIndex: "field" },
    { title: "Value", dataIndex: "value", render: (value: unknown) => shortValue(value) }
  ];
  function recordRows(rows: Array<Record<string, unknown>>) {
    return rows.flatMap((row, index) => {
      const fields = Object.entries(row);
      if (fields.length === 0) {
        return [{ id: `${index}-empty`, record: index + 1, field: "—", value: "<empty>" }];
      }
      return fields.map(([field, value]) => ({
        id: `${index}-${field}`,
        record: index + 1,
        field,
        value,
      }));
    });
  }
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">{run.name ?? run.id}</h1>
        <Space>
          <span data-testid="run-status"><StatusTag status={run.status} /></span>
          {active && <Button danger onClick={cancelRun}>Cancel</Button>}
          <Button onClick={reload} icon={<ReloadOutlined />}>Refresh</Button>
        </Space>
      </div>
      {(run.error_message || run.error) && <Alert type="error" showIcon message={run.error_message ?? run.error} style={{ marginBottom: 16 }} />}
      {sharpeWarning && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Sharpe is marked unstable because the effective daily return sample is short."
        />
      )}
      <div className="grid">
        {metricCards.map((item) => (
          <Card key={item.title} data-testid={`metric-${item.title.toLowerCase().replace(/\s+/g, "-")}`}>
            <Statistic title={item.title} value={shortValue(item.value ?? "N/A")} />
            {item.warning && <Tag color="orange">short window</Tag>}
          </Card>
        ))}
      </div>
      <Tabs
        items={[
          {
            key: "status",
            label: "Status",
            children: (
              <Card data-testid="run-status-panel">
                <Space wrap>
                  <Tag>backtest_id: {run.id}</Tag>
                  <Tag>name: {run.name ?? "-"}</Tag>
                  <Tag>strategy: {run.project_id ?? "default"}</Tag>
                  <Tag>symbol: {run.symbol}</Tag>
                  <Tag>market: {String(run.parameters?.market ?? run.venue ?? "-")}</Tag>
                  <Tag>start: {run.parameters?.start}</Tag>
                  <Tag>end: {run.parameters?.end}</Tag>
                  <Tag>cash: {String(run.parameters?.cash ?? "-")}</Tag>
                  <Tag>created: {run.created_at}</Tag>
                  {run.queued_at && <Tag>queued: {run.queued_at}</Tag>}
                  {run.started_at && <Tag>started: {run.started_at}</Tag>}
                  {run.finished_at && <Tag>finished: {run.finished_at}</Tag>}
                  {run.duration_seconds != null && <Tag>duration: {run.duration_seconds}s</Tag>}
                  {run.container_name && <Tag>container: {run.container_name}</Tag>}
                </Space>
              </Card>
            )
          },
          {
            key: "config",
            label: "Config",
            children: <Card title="Parameters"><Space wrap>{Object.entries(run.parameters).map(([key, value]) => <Tag key={key}>{key}: {String(value)}</Tag>)}</Space></Card>
          },
          {
            key: "metrics",
            label: "Metrics",
            children: (
              <Card title="Summary" data-testid="metrics-table">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="key"
                  dataSource={Object.entries(result?.summary_metrics ?? run.statistics ?? {}).map(([key, value]) => ({ key, value }))}
                  columns={[{ title: "Metric", dataIndex: "key" }, { title: "Value", dataIndex: "value" }]}
                />
              </Card>
            )
          },
          {
            key: "validation",
            label: "Validation",
            children: <BacktestTrustPanel validation={validation} experiment={experiment} fingerprint={fingerprint} />
          },
          {
            key: "admission",
            label: "Admission",
            children: <StrategyAdmissionPanel value={admission} />
          },
          { key: "charts", label: "Charts", children: chart ? <BacktestCharts chartData={chart} /> : <Alert type="info" message="Charts are available after a successful run." /> },
          {
            key: "records",
            label: "Records",
            children: (
              <div data-testid="records-panel">
                <Card title={`Orders (${records.orders.length})`}>
                  {records.orders.length > 0 ? (
                    <Table data-testid="result-orders-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.orders)} columns={recordColumns} />
                  ) : <Alert type="info" message="No orders were parsed for this run." />}
                </Card>
                <Card title={`Trades (${records.trades.length})`} style={{ marginTop: 16 }}>
                  {records.trades.length > 0 ? (
                    <Table data-testid="result-trades-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.trades)} columns={recordColumns} />
                  ) : <Alert type="info" message="No trades were parsed for this run." />}
                </Card>
                <Card title={`Holdings (${records.holdings.length})`} style={{ marginTop: 16 }}>
                  {records.holdings.length > 0 ? (
                    <Table data-testid="result-holdings-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.holdings)} columns={recordColumns} />
                  ) : <Alert type="info" message="No holdings were parsed for this run." />}
                </Card>
              </div>
            )
          },
          {
            key: "raw",
            label: "Raw Files",
            children: <Card title="Artifacts">{(run.artifacts ?? []).map((name) => <a className="artifact-link" key={name} target="_blank" href={`/api/backtests/${run.id}/artifacts/${name}`}>{name}</a>)}</Card>
          },
          { key: "logs", label: "Logs", children: <Card><pre data-testid="backtest-logs" className="log-view">{logs || "No logs yet."}</pre></Card> }
        ]}
      />
    </>
  );
}

export function OptimizationPage() {
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const optimizations = useAsyncData(api.optimizations, []);
  const [form] = Form.useForm();
  const [portfolioForm] = Form.useForm();
  const [portfolioResult, setPortfolioResult] = useState<PortfolioOptimizationResult>();
  const [portfolioSubmitting, setPortfolioSubmitting] = useState(false);
  const assetClass = Form.useWatch("assetClass", form) || "equity";
  const market = Form.useWatch("market", form) || "china";
  const selectedProjectId = Form.useWatch("projectId", form);
  const selectedProject = projects.data.find((item) => item.id === selectedProjectId);
  const selectedTemplate = projectTemplate(selectedProject, templates.data);
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === assetClass);
  function parseGridValues(value: unknown) {
    return String(value ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        if (item.toLowerCase() === "true") return true;
        if (item.toLowerCase() === "false") return false;
        const numeric = Number(item);
        return Number.isFinite(numeric) ? numeric : item;
      });
  }
  function parseJsonObject(value: unknown) {
    const text = String(value ?? "").trim();
    if (!text) return {};
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  }
  function bestCandidate(run: OptimizationRun) {
    return (run.result?.best ?? null) as Record<string, unknown> | null;
  }
  async function submit(values: any) {
    const gridFromFields = Object.fromEntries(
      Object.entries(values.parameterGrid ?? {})
        .map(([key, value]) => [key, parseGridValues(value)])
        .filter(([, value]) => Array.isArray(value) && value.length)
    );
    const parameterGrid = { ...gridFromFields, ...parseJsonObject(values.parameterGridJson) };
    await api.createOptimization({
      ...values,
      parameters: parseJsonObject(values.parametersJson),
      parameterGrid
    });
    message.success("Optimization queued");
    optimizations.reload();
  }
  async function submitPortfolio(values: any) {
    const runIds = String(values.runIds ?? "")
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    setPortfolioSubmitting(true);
    try {
      setPortfolioResult(await api.optimizePortfolio({
        runIds,
        objective: values.objective,
        step: Number(values.step),
        maxWeight: Number(values.maxWeight),
        allowShort: false
      }));
      message.success("Portfolio weights optimized");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setPortfolioSubmitting(false);
    }
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Optimization</h1><Button icon={<ReloadOutlined />} onClick={optimizations.reload}>Refresh</Button></div>
      <Tabs
        items={[
          {
            key: "grid",
            label: "Parameter Grid",
            children: (
              <>
                <Card title="Parameter Grid">
                  <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "china", venue: "china", resolution: "daily", dataType: "trade", symbol: "000001", start: "2024-01-01", end: "2026-07-13", cash: 300000, maxCandidates: 50, dockerImage: defaultSettings.dockerImage }}>
                    <div className="field-grid">
                      <Form.Item name="projectId" label="Project" rules={[{ required: true }]}><Select onChange={(value) => { const project = projects.data.find((item) => item.id === value); if (project) { const template = projectTemplate(project, templates.data); form.setFieldsValue({ assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), parameterGrid: Object.fromEntries((template?.parameters ?? []).map((parameter) => [parameter.key, String(parameter.default ?? "")])) }); } }} options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
                      <Form.Item name="assetClass" label="Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
                      <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
                      <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item name="symbol" label="Symbol"><SecuritySearch assetClass={assetClass} market={market} /></Form.Item>
                      <Form.Item name="start" label="Start"><DateStringPicker /></Form.Item>
                      <Form.Item name="end" label="End"><DateStringPicker /></Form.Item>
                      <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="maxCandidates" label="Max Candidates"><InputNumber min={1} max={200} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
                    </div>
                    <div className="field-grid">
                      {(selectedTemplate?.parameters ?? []).map((parameter) => (
                        <Form.Item key={parameter.key} name={["parameterGrid", parameter.key]} label={`${parameter.label} Grid`}>
                          <Input placeholder={String(parameter.default ?? "")} />
                        </Form.Item>
                      ))}
                    </div>
                    <Form.Item name="parameterGridJson" label="Custom Parameter Grid JSON">
                      <Input.TextArea rows={3} placeholder='{"period":[10,20,30],"threshold":[0.1,0.2]}' />
                    </Form.Item>
                    <Form.Item name="parametersJson" label="Fixed Parameters JSON">
                      <Input.TextArea rows={3} placeholder='{"benchmarkSymbol":"SPY"}' />
                    </Form.Item>
                    <Button type="primary" icon={<SlidersOutlined />} htmlType="submit">Queue Optimization</Button>
                  </Form>
                </Card>
                <Card title="Optimization Runs" style={{ marginTop: 16 }}>
                  <Table<OptimizationRun> rowKey="id" dataSource={optimizations.data} size="small" columns={[
                    { title: "ID", dataIndex: "id", ellipsis: true },
                    { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
                    { title: "Candidates", render: (_, run) => run.result?.candidateCount ?? run.result?.candidates?.length ?? "-" },
                    { title: "Best", render: (_, run) => shortValue(bestCandidate(run)?.overrides ?? "-") },
                    { title: "Created", dataIndex: "created_at" }
                  ]} />
                </Card>
              </>
            )
          },
          {
            key: "portfolio",
            label: "Portfolio Weights",
            children: (
              <>
                <Card title="Admission-Gated Portfolio Optimization">
                  <Alert
                    type="info"
                    showIcon
                    message="Only successful run IDs whose strategy parameter set passed admission can be optimized."
                    style={{ marginBottom: 16 }}
                  />
                  <Form
                    form={portfolioForm}
                    layout="vertical"
                    onFinish={submitPortfolio}
                    initialValues={{ objective: "sharpe", step: 0.1, maxWeight: 1.0 }}
                  >
                    <Form.Item name="runIds" label="Run IDs" rules={[{ required: true }]}>
                      <Input.TextArea rows={4} placeholder="run-id-1, run-id-2" />
                    </Form.Item>
                    <div className="field-grid">
                      <Form.Item name="objective" label="Objective">
                        <Select options={[
                          { value: "sharpe", label: "Maximum Sharpe" },
                          { value: "return", label: "Maximum Annual Return" },
                          { value: "drawdown", label: "Minimum Drawdown" }
                        ]} />
                      </Form.Item>
                      <Form.Item name="step" label="Weight Step">
                        <InputNumber min={0.01} max={0.5} step={0.05} style={{ width: "100%" }} />
                      </Form.Item>
                      <Form.Item name="maxWeight" label="Maximum Weight">
                        <InputNumber min={0.01} max={1} step={0.05} style={{ width: "100%" }} />
                      </Form.Item>
                    </div>
                    <Button type="primary" htmlType="submit" loading={portfolioSubmitting}>Optimize Weights</Button>
                  </Form>
                </Card>
                {portfolioResult && (
                  <div className="two-column" style={{ marginTop: 16 }}>
                    <Card title="Weights">
                      <Table
                        size="small"
                        pagination={false}
                        rowKey="runId"
                        dataSource={Object.entries(portfolioResult.weights).map(([runId, weight]) => ({ runId, weight }))}
                        columns={[
                          { title: "Run ID", dataIndex: "runId" },
                          { title: "Weight", dataIndex: "weight", render: (value) => `${(Number(value) * 100).toFixed(1)}%` }
                        ]}
                      />
                    </Card>
                    <Card title={`Metrics (${portfolioResult.candidateCount} candidates)`}>
                      <Table
                        size="small"
                        pagination={false}
                        rowKey="metric"
                        dataSource={Object.entries(portfolioResult.metrics).map(([metric, value]) => ({ metric, value }))}
                        columns={[
                          { title: "Metric", dataIndex: "metric" },
                          { title: "Value", dataIndex: "value", render: (value) => shortValue(value) }
                        ]}
                      />
                    </Card>
                  </div>
                )}
              </>
            )
          },
          { key: "compare", label: "Compare Runs", children: <CompareRunsPanel /> }
        ]}
      />
    </>
  );
}
