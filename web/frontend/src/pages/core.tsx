import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
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
  ArrowLeftOutlined,
  CloudDownloadOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SaveOutlined,
  SettingOutlined,
  SlidersOutlined
} from "@ant-design/icons";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react";
import Editor from "@monaco-editor/react";

import { api } from "../api";
import dayjs from "dayjs";
import type {
  AppSettings,
  AssetClassInfo,
  BacktestAdmissionResponse,
  BacktestExperiment,
  BacktestPreflight,
  BacktestResult,
  BacktestRun,
  BacktestValidation,
  BacktestValidationResponse,
  CBondPoolItem,
  CBondRiskItem,
  ChartData,
  DataQueryResult,
  DataProvider,
  DataSyncCatalog,
  DataSyncRun,
  DerivedLayerWatermarks,
  OnDemandStorageTarget,
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
  SecurityProfile,
  StrategyTemplate,
  Task,
  WorkflowExample,
} from "../api";
import { CompareRunsPanel } from "./compare";
import { BacktestCharts, RunsTable, StatusTag } from "../components";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { AdvancedFields, FormActions, FormGrid, FormSection } from "../components/forms/FormLayout";
import { DatasetPreviewPanel } from "../components/data/DatasetPreviewPanel";
import { BacktestTrustPanel, StrategyAdmissionPanel, ValidationStatusTag } from "../components/backtests/BacktestTrustPanel";
import { RunDetailPanelBoundary } from "../components/backtests/RunDetailPanelBoundary";
import { ExampleGallery } from "../components/examples/ExampleGallery";
import { BatchWorkbench } from "../components/experiments/BatchWorkbench";
import { candlestickOption } from "../charts/candlestick";
import { defaultBarPreviewValues, defaultSettings } from "../config/defaults";
import { useAsyncData } from "../hooks";
import { buildBacktestRequest, marketCostParameters } from "../domain/backtest-request";
import {
  asRecord,
  detailText,
  formatCurrency,
  formatDateTime,
  formatDuration,
  formatInteger,
  formatNumber,
  formatPercent,
  isRecord,
  shortValue
} from "../utils/display";
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

function dataSourceLabel(value: string) {
  if (["securities", "canonical"].includes(value)) return "本地证券主表";
  return value.replace(/^tushare(?=:|$)/, "TuShare Pro");
}

function quoteNumber(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined || !Number.isFinite(Number(value))
    ? "-"
    : Number(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function compactMarketNumber(value: number | null | undefined) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (Math.abs(number) >= 100_000_000) return `${(number / 100_000_000).toFixed(2)} 亿`;
  if (Math.abs(number) >= 10_000) return `${(number / 10_000).toFixed(2)} 万`;
  return number.toLocaleString();
}

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
  return nextMarket === "china" || nextMarket === "hongkong" ? "tushare" : "";
}

function defaultBenchmark(nextMarket: string) {
  if (nextMarket === "china") return "000300";
  if (nextMarket === "hongkong") return "02800";
  return "SPY";
}

function defaultProviderForMarket(nextMarket: string, markets: MarketInfo[]) {
  return markets.find((item) => item.key === nextMarket)?.defaultProvider ??
    (nextMarket === "china" || nextMarket === "hongkong" ? "tushare" : "yfinance");
}

function defaultSymbolText(assetClass: string, nextMarket: string) {
  if (assetClass === "crypto") return "BTCUSDT, ETHUSDT";
  if (assetClass === "future") return "GC, ES";
  if (nextMarket === "china") return "000001";
  if (nextMarket === "hongkong") return "00700";
  return "AAPL";
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
  const end = String(project?.config?.end ?? safeSettings.defaultEnd ?? dayjs().format(ISO_DATE_FORMAT));
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
    benchmarkSymbol: String(project?.config?.benchmarkSymbol ?? defaultBenchmark(market)),
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

type BacktestMetricKind = "currency" | "integer" | "number" | "percent" | "text";

function formatBacktestMetric(value: unknown, kind: BacktestMetricKind = "number", currency = "USD") {
  if (value == null || value === "") return "—";
  if (kind === "currency") return formatCurrency(value, currency);
  if (kind === "integer") return formatInteger(value);
  if (kind === "percent") return formatPercent(value);
  if (kind === "text") return shortValue(value);
  return formatNumber(value);
}

function humanizeField(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function BacktestMetricCard({
  title,
  value,
  kind = "number",
  currency,
  warning,
  featured = false,
}: {
  title: string;
  value: unknown;
  kind?: BacktestMetricKind;
  currency?: string;
  warning?: boolean;
  featured?: boolean;
}) {
  return (
    <Card
      className={`backtest-metric-card${featured ? " backtest-metric-card--featured" : ""}`}
      data-testid={`metric-${title.toLowerCase().replace(/\s+/g, "-")}`}
    >
      <div className="backtest-metric-label">{title}</div>
      <div className="backtest-metric-value">{formatBacktestMetric(value, kind, currency)}</div>
      {warning && <Tag color="orange">short window</Tag>}
    </Card>
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
  const [listedDate, setListedDate] = useState<string>();
  const [queryResult, setQueryResult] = useState<DataQueryResult>();
  const [securityInfo, setSecurityInfo] = useState<SecurityProfile>();
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
    if (selectedAssetClass !== "equity" || !querySymbol) {
      setListedDate(undefined);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void api.searchSecurities(selectedMarket, querySymbol, 20)
        .then((result) => {
          if (!active) return;
          const security = result.items.find((item) => item.symbol.toUpperCase() === querySymbol.toUpperCase());
          const nextListedDate = security?.listedDate ?? undefined;
          setListedDate(nextListedDate);
          if (nextListedDate) {
            form.setFieldValue("startDate", nextListedDate);
          }
        })
        .catch(() => {
          if (active) setListedDate(undefined);
        });
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [form, querySymbol, selectedAssetClass, selectedMarket]);

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

  async function loadSecurityInfo(symbol: string): Promise<SecurityProfile> {
    try {
      return await api.securityProfile(selectedMarket, symbol);
    } catch {
      const search = await api.searchSecurities(selectedMarket, symbol);
      const matched = search.items.find((item) => item.symbol === symbol) ?? search.items[0];
      return {
        symbol,
        name: matched?.name ?? symbol,
        market: matched?.market ?? selectedMarket,
        marketLabel: matched?.marketLabel ?? selectedMarket,
        exchange: matched?.exchange,
        listedDate: matched?.listedDate,
        status: matched?.status,
        isSt: false,
        concepts: [],
        hasLocalData: Boolean(matched?.hasLocalData),
        identifiers: [],
        coverage: [],
        memberships: [],
        adjustmentHistory: [],
        suspensionHistory: [],
        limitHistory: []
      };
    }
  }

  async function queryLocalBars(values: any, symbol: string, providerOverride?: string) {
    return api.queryData({
      source: values.source ?? "database",
      symbol,
      assetClass: selectedAssetClass,
      market: selectedMarket,
      venue: selectedVenue,
      resolution: selectedResolution,
      dataType: selectedDataType,
      providerSource: providerOverride ?? values.provider,
      providerMode: "strict",
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
      const effectiveStartDate = security.listedDate && (!values.startDate || dayjs(values.startDate).isBefore(dayjs(security.listedDate)))
        ? security.listedDate
        : values.startDate;
      if (effectiveStartDate !== values.startDate) {
        form.setFieldValue("startDate", effectiveStartDate);
      }
      const effectiveValues = { ...values, startDate: effectiveStartDate };
      let result = await queryLocalBars(effectiveValues, symbol);
      if (requestId !== previewRequestId.current) return;
      if (result.enabled && result.items.length === 0 && ["china", "hongkong"].includes(selectedMarket)) {
        message.info(`本地没有 ${symbol} 数据，正在按需从 TuShare Pro 获取并缓存。`);
        await api.fetchData({
          symbol,
          assetClass: selectedAssetClass,
          market: selectedMarket,
          venue: selectedVenue,
          resolution: selectedResolution,
          dataType: selectedDataType,
          provider: "tushare",
          apiKey: values.apiKey,
          outputsize: "full",
          startDate: effectiveStartDate,
          endDate: dayjs().format(ISO_DATE_FORMAT),
          adjust: values.adjust,
          overwrite: Boolean(values.overwrite)
        });
        if (requestId !== previewRequestId.current) return;
        setSecurityInfo(await loadSecurityInfo(symbol));
        result = await queryLocalBars(effectiveValues, symbol, "tushare");
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
      const primarySecurity = await loadSecurityInfo(symbols[0]);
      const effectiveStartDate = primarySecurity.listedDate && (!values.startDate || dayjs(values.startDate).isBefore(dayjs(primarySecurity.listedDate)))
        ? primarySecurity.listedDate
        : values.startDate;
      if (effectiveStartDate !== values.startDate) {
        form.setFieldValue("startDate", effectiveStartDate);
      }
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
        startDate: effectiveStartDate,
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
        <FormSection title="Data source" description="Select the store, market and bar definition.">
          <FormGrid>
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
          </FormGrid>
        </FormSection>
        <FormSection title="Instrument scope" description="Search one or more symbols to preview or download.">
          <FormGrid>
            <Form.Item className="form-field--full" label="Symbols">
              <SecuritySearch
                assetClass={selectedAssetClass}
                market={selectedMarket}
                value={symbolsText}
                onChange={(value) => setSymbolsText(value.toUpperCase())}
                onSelectSecurity={(security) => {
                  setSymbolsText(security.symbol);
                  const nextListedDate = security.listedDate ?? undefined;
                  setListedDate(nextListedDate);
                  if (nextListedDate) form.setFieldValue("startDate", nextListedDate);
                }}
                placeholder={selectedAssetClass === "equity" ? "搜索代码 / 公司 / 拼音，或直接输入代码" : "输入 Symbol"}
              />
            </Form.Item>
          </FormGrid>
        </FormSection>
        <FormSection title="Time range" description="Choose the requested history window.">
          <FormGrid>
          <Form.Item
            name="startDate"
            label="Start"
            extra={listedDate ? `最早可选：上市日 ${listedDate}` : undefined}
            rules={[
              { required: true, message: "Start date is required" },
              dateRule("Start date"),
              {
                validator(_, value) {
                  if (!value || !listedDate || !isValidDate(value)) return Promise.resolve();
                  if (dayjs(value).isBefore(dayjs(listedDate), "day")) {
                    return Promise.reject(new Error(`Start date cannot be earlier than listing date ${listedDate}`));
                  }
                  return Promise.resolve();
                }
              }
            ]}
          >
            <DateStringPicker
              testId="market-data-start-input"
              disabledDate={(current) => Boolean(listedDate && current.isBefore(dayjs(listedDate), "day"))}
            />
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
          </FormGrid>
        </FormSection>
        {(showLimitInput || showOutputSize) && <FormSection title="Output options">
          <FormGrid>
          {showLimitInput && <Form.Item name="limit" label="Preview Rows"><InputNumber min={1} max={5000} style={{ width: "100%" }} /></Form.Item>}
          {showOutputSize && (
            <Form.Item name="outputsize" label="Output Size">
              <Select disabled={selectedProvider !== "alpha_vantage"} options={[{ value: "compact" }, { value: "full" }]} />
            </Form.Item>
          )}
          </FormGrid>
        </FormSection>}
        {((showApiKey && selectedProvider === "alpha_vantage") || showOverwrite) && (
          <AdvancedFields>
            <FormGrid>
              {(showApiKey && selectedProvider === "alpha_vantage") && (
                <Form.Item className="form-field--wide" name="apiKey" label="API Key"><Input.Password placeholder="or environment variable" /></Form.Item>
              )}
              {showOverwrite && <Form.Item name="overwrite" valuePropName="checked" label=" "><Checkbox>Overwrite local files</Checkbox></Form.Item>}
            </FormGrid>
          </AdvancedFields>
        )}
        <FormActions>
          <Button
            data-testid="market-data-preview-button"
            icon={<ReloadOutlined />}
            loading={queryLoading}
            onClick={() => void form.validateFields().then(previewMarketData).catch(() => undefined)}
          >Preview</Button>
          <Button data-testid="market-data-fetch-button" type="primary" icon={<CloudDownloadOutlined />} htmlType="submit" loading={fetchLoading}>Download</Button>
        </FormActions>
      </Form>
      {securityInfo && (
        <Card size="small" className="stock-preview-card" style={{ marginBottom: 12 }}>
          <div className="stock-quote-hero">
            <div className="stock-quote-identity">
              <div className="stock-quote-title">
                <span>{securityInfo.name}</span>
                {securityInfo.isSt && <Tag color="warning">ST</Tag>}
                <Tag color={securityInfo.status === "listed" || securityInfo.status === "active" ? "success" : "default"}>{securityInfo.status || "未知状态"}</Tag>
              </div>
              <div className="stock-quote-subtitle">{securityInfo.symbol} · {securityInfo.marketLabel}{securityInfo.exchange ? ` / ${securityInfo.exchange}` : ""} · {securityInfo.industry || "行业未分类"}</div>
            </div>
            <div className={`stock-quote-price ${(securityInfo.quote?.pctChange ?? 0) >= 0 ? "up" : "down"}`}>
              <div className="stock-quote-last">{quoteNumber(securityInfo.quote?.close)}</div>
              <div className="stock-quote-change">
                {securityInfo.quote?.change !== null && securityInfo.quote?.change !== undefined && Number(securityInfo.quote.change) > 0 ? "+" : ""}{quoteNumber(securityInfo.quote?.change)}
                <span>{securityInfo.quote?.pctChange !== null && securityInfo.quote?.pctChange !== undefined && Number(securityInfo.quote.pctChange) > 0 ? "+" : ""}{quoteNumber(securityInfo.quote?.pctChange)}%</span>
              </div>
              <div className="stock-quote-date">截至 {securityInfo.quote?.tradeDate || "-"}</div>
            </div>
            <div className="stock-quote-metrics">
              <div><span>今开</span><strong>{quoteNumber(securityInfo.quote?.open)}</strong></div>
              <div><span>最高</span><strong>{quoteNumber(securityInfo.quote?.high)}</strong></div>
              <div><span>最低</span><strong>{quoteNumber(securityInfo.quote?.low)}</strong></div>
              <div><span>昨收</span><strong>{quoteNumber(securityInfo.quote?.previousClose)}</strong></div>
              <div><span>成交量</span><strong>{compactMarketNumber(securityInfo.quote?.volume)}</strong></div>
              <div><span>成交额</span><strong>{compactMarketNumber(securityInfo.quote?.amount)}</strong></div>
              <div><span>换手率</span><strong>{quoteNumber(securityInfo.quote?.turnoverRate)}%</strong></div>
              <div><span>复权因子</span><strong>{quoteNumber(securityInfo.quote?.adjustmentFactor, 4)}</strong></div>
            </div>
          </div>
          <Tabs
            size="small"
            items={[
              {
                key: "chart",
                label: "行情走势",
                children: (
                  <>
                    {queryResult && !queryResult.enabled && <Alert style={{ marginBottom: 12 }} type="warning" showIcon message={queryResult.error ?? "所选数据源不可用"} />}
                    {queryResult?.enabled && queryResult.message && <Alert style={{ marginBottom: 12 }} type="info" showIcon message={queryResult.message} />}
                    {queryResult?.enabled && queryResult.items.length === 0 && <Alert style={{ marginBottom: 12 }} type="info" showIcon message="所选日期范围没有本地日线数据。" />}
                    {queryResult?.enabled && queryResult.items.length > 0 && (
                      <>
                        <Space wrap style={{ marginBottom: 12 }}>
                          <Tag color="blue">{dataSourceLabel(queryResult.source ?? "data")}</Tag>
                          <Tag>{queryResult.count.toLocaleString()} 根日线</Tag>
                          <Tag>{`${queryResult.items[0].timestamp.slice(0, 10)} → ${queryResult.items[queryResult.items.length - 1].timestamp.slice(0, 10)}`}</Tag>
                        </Space>
                        <ReactECharts style={{ height: compact ? 360 : 540, marginBottom: 8 }} option={chartOption} />
                      </>
                    )}
                  </>
                )
              },
              {
                key: "profile",
                label: "公司资料",
                children: (
                  <Descriptions bordered size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
                    <Descriptions.Item label="证券代码">{securityInfo.symbol}</Descriptions.Item>
                    <Descriptions.Item label="证券名称">{securityInfo.name}</Descriptions.Item>
                    <Descriptions.Item label="市场 / 交易所">{securityInfo.marketLabel}{securityInfo.exchange ? ` / ${securityInfo.exchange}` : ""}</Descriptions.Item>
                    <Descriptions.Item label="上市日期">{securityInfo.listedDate || "-"}</Descriptions.Item>
                    <Descriptions.Item label="上市状态">
                      <Space size={4}><Tag color={securityInfo.status === "listed" || securityInfo.status === "active" ? "success" : "default"}>{securityInfo.status || "未知"}</Tag>{securityInfo.isSt && <Tag color="warning">ST</Tag>}</Space>
                    </Descriptions.Item>
                    <Descriptions.Item label="行业">{securityInfo.industry || "-"}</Descriptions.Item>
                    <Descriptions.Item label="币种 / 交易单位">{securityInfo.currency || "-"}{securityInfo.lotSize ? ` / ${securityInfo.lotSize}` : ""}</Descriptions.Item>
                    <Descriptions.Item label="主数据来源">{securityInfo.masterSource ? dataSourceLabel(securityInfo.masterSource) : "本地证券主表"}</Descriptions.Item>
                    <Descriptions.Item label="本地数据">{securityInfo.hasLocalData ? <Tag color="success">已入库</Tag> : <Tag color="warning">暂无覆盖</Tag>}</Descriptions.Item>
                    {securityInfo.concepts.length > 0 && <Descriptions.Item label="概念" span={3}><Space wrap>{securityInfo.concepts.map((item) => <Tag key={item}>{item}</Tag>)}</Space></Descriptions.Item>}
                  </Descriptions>
                )
              },
              {
                key: "adjustments",
                label: `复权因子 (${securityInfo.adjustmentHistory.length})`,
                children: (
                  <Table
                    size="small"
                    pagination={{ pageSize: 20, hideOnSinglePage: true }}
                    rowKey={(row) => `${row.trade_date}:${row.source}`}
                    dataSource={securityInfo.adjustmentHistory}
                    locale={{ emptyText: "暂无复权因子" }}
                    columns={[
                      { title: "交易日", dataIndex: "trade_date" },
                      { title: "复权因子", dataIndex: "adj_factor", render: (value: number) => quoteNumber(value, 6) },
                      { title: "来源", dataIndex: "source", render: (value: string) => dataSourceLabel(value) }
                    ]}
                  />
                )
              },
              {
                key: "suspensions",
                label: `停牌历史 (${securityInfo.suspensionHistory.length})`,
                children: (
                  <Table
                    size="small"
                    pagination={{ pageSize: 20, hideOnSinglePage: true }}
                    rowKey={(row) => `${row.trade_date}:${row.source}`}
                    dataSource={securityInfo.suspensionHistory}
                    locale={{ emptyText: "该股票暂无 suspend_d 停牌记录" }}
                    columns={[
                      { title: "停牌日期", dataIndex: "trade_date" },
                      { title: "停牌", dataIndex: "is_suspended", render: (value: unknown) => Number(value) ? <Tag color="error">停牌</Tag> : <Tag color="success">正常</Tag> },
                      { title: "可买", dataIndex: "can_buy", render: (value: unknown) => Number(value) ? "是" : "否" },
                      { title: "可卖", dataIndex: "can_sell", render: (value: unknown) => Number(value) ? "是" : "否" },
                      { title: "来源", dataIndex: "source", render: (value: string) => dataSourceLabel(value) }
                    ]}
                  />
                )
              },
              {
                key: "limits",
                label: `涨跌停历史 (${securityInfo.limitHistory.length})`,
                children: (
                  <Table
                    size="small"
                    pagination={{ pageSize: 20, hideOnSinglePage: true }}
                    rowKey={(row) => `${row.trade_date}:${row.source}`}
                    dataSource={securityInfo.limitHistory}
                    locale={{ emptyText: "该股票暂无 stk_limit 记录" }}
                    columns={[
                      { title: "交易日", dataIndex: "trade_date" },
                      { title: "涨停价", dataIndex: "limit_up", render: (value: number) => <span className="quote-up-text">{quoteNumber(value)}</span> },
                      { title: "跌停价", dataIndex: "limit_down", render: (value: number) => <span className="quote-down-text">{quoteNumber(value)}</span> },
                      { title: "ST", dataIndex: "is_st", render: (value: unknown) => Number(value) ? <Tag color="warning">是</Tag> : "否" },
                      { title: "来源", dataIndex: "source", render: (value: string) => dataSourceLabel(value) }
                    ]}
                  />
                )
              },
              {
                key: "coverage",
                label: "数据档案",
                children: (
                  <Tabs
                    size="small"
                    items={[
                      {
                        key: "coverage-detail",
                        label: `数据覆盖 (${securityInfo.coverage.length})`,
                        children: <Table size="small" pagination={false} rowKey="key" dataSource={securityInfo.coverage} columns={[
                          { title: "数据库数据", dataIndex: "label" },
                          { title: "记录数", dataIndex: "rows", align: "right", render: (value: number) => value.toLocaleString() },
                          { title: "起始日期", dataIndex: "firstDate", render: (value: string | null) => value || "-" },
                          { title: "最新日期", dataIndex: "lastDate", render: (value: string | null) => value || "-" },
                          { title: "来源", dataIndex: "sources", render: (sources: string[]) => <Space wrap>{sources.map((source) => <Tag key={source}>{dataSourceLabel(source)}</Tag>)}</Space> }
                        ]} />
                      },
                      {
                        key: "identifier-detail",
                        label: `标识符 (${securityInfo.identifiers.length})`,
                        children: <Table size="small" pagination={false} rowKey={(row) => `${row.provider}:${row.identifier_type}:${row.identifier_value}`} dataSource={securityInfo.identifiers} columns={[
                          { title: "系统", dataIndex: "provider" },
                          { title: "类型", dataIndex: "identifier_type" },
                          { title: "标识值", dataIndex: "identifier_value" },
                          { title: "交易所", dataIndex: "exchange" },
                          { title: "主标识", dataIndex: "is_primary", render: (value: boolean | number) => value ? <Tag color="blue">是</Tag> : "否" }
                        ]} />
                      }
                    ]}
                  />
                )
              },
              {
                key: "memberships",
                label: `股票池 (${securityInfo.memberships.length})`,
                children: (
                  <Table
                    size="small"
                    pagination={{ pageSize: 10, hideOnSinglePage: true }}
                    rowKey={(row) => `${row.universe_code}:${row.start_date}`}
                    dataSource={securityInfo.memberships}
                    locale={{ emptyText: "暂无股票池或指数成分记录" }}
                    columns={[
                      { title: "股票池 / 指数", dataIndex: "universe_code" },
                      { title: "生效日期", dataIndex: "start_date" },
                      { title: "结束日期", dataIndex: "end_date", render: (value: string | null) => value || "当前" },
                      { title: "权重", dataIndex: "weight", render: (value: number | null) => value ?? "-" },
                      { title: "来源", dataIndex: "source" }
                    ]}
                  />
                )
              }
            ]}
          />
        </Card>
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
  const projectEditorRef = useRef<HTMLDivElement>(null);
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
  const [dirty, setDirty] = useState(false);
  const [preflight, setPreflight] = useState<BacktestPreflight>();
  const [sourcePath, setSourcePath] = useState("");
  const [sourceCode, setSourceCode] = useState("");
  const [sourceDirty, setSourceDirty] = useState(false);
  const [sourceLoading, setSourceLoading] = useState(false);
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
    setDirty(false);
    setPreflight(undefined);
  }, [form, selectedProject, settings.data, templates.data, selectedProject?.id]);

  useEffect(() => {
    if (!selectedProject) {
      setSourcePath("");
      setSourceCode("");
      return;
    }
    let active = true;
    const path = selectedProject.main_file || String(selectedProject.config?.mainFile || "main.py");
    setSourceLoading(true);
    api.readProjectFile(selectedProject.id, path)
      .then((file) => {
        if (!active) return;
        setSourcePath(file.path);
        setSourceCode(file.content);
        setSourceDirty(false);
      })
      .catch((error) => {
        if (active) message.error((error as Error).message);
      })
      .finally(() => {
        if (active) setSourceLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedProject?.id]);

  useEffect(() => {
    let active = true;
    api.symbols(selectedMarket, selectedAssetClass, selectedVenue, selectedResolution, selectedDataType)
      .then((result) => {
        if (active) setSymbols(result.symbols);
      })
      .catch((error) => {
        if (active) message.error((error as Error).message);
      });
    return () => {
      active = false;
    };
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
      const values = await form.validateFields();
      const config = parseProjectConfig(values);
      const payload = {
        name: String(values.name ?? selectedProject.name),
        config
      };
      await api.updateProject(selectedProject.id, payload);
      message.success("Project configuration saved");
      await projects.reload();
      setDirty(false);
      setPreflight(undefined);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function saveSource() {
    if (!selectedProject || !sourcePath) return;
    setSourceLoading(true);
    try {
      await api.writeProjectFile(selectedProject.id, sourcePath, sourceCode);
      setSourceDirty(false);
      message.success("Strategy source saved");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSourceLoading(false);
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
    let values: any;
    try {
      values = await form.validateFields();
    } catch {
      message.error("Please correct the project configuration before running.");
      return;
    }
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
      await api.updateProject(selectedProject.id, {
        name: String(values.name ?? selectedProject.name),
        config: nextConfig,
      });
      setDirty(false);
      const payload = buildBacktestRequest({
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
        projectId: selectedProject.id,
        parameters: request.parameters,
      });
      const readiness = await api.preflightBacktest(payload);
      setPreflight(readiness);
      if (readiness.repaired.length > 0) {
        message.success(`Data repaired: ${readiness.repaired.join(", ")}`);
      }
      const run = await api.createBacktest(payload);
      await projects.reload();
      message.success("Backtest queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function deleteProject(project: Project) {
    let confirmation = "";
    Modal.confirm({
      title: `Delete ${project.name}?`,
      content: <div>
        <Alert
          type="error"
          showIcon
          message="This is a cascading delete"
          description={`The project, ${project.run_count ?? 0} backtests, related reports, tasks, optimizations, research sessions and managed runtime files will be removed.`}
          style={{ marginBottom: 12 }}
        />
        <p>Type the project name to confirm:</p>
        <Input placeholder={project.name} onChange={(event) => { confirmation = event.target.value; }} />
      </div>,
      okText: "Delete project and history",
      okButtonProps: { danger: true },
      onOk: async () => {
        if (confirmation !== project.name) throw new Error("Project name does not match.");
        await api.deleteProject(project.id);
        message.success("Project deleted");
        await projects.reload();
      }
    });
  }

  function duplicateProject(project: Project) {
    const baseName = project.display_name || project.name;
    let duplicateName = `${baseName} variant`;
    Modal.confirm({
      title: `Duplicate ${baseName}`,
      content: (
        <Input
          defaultValue={duplicateName}
          placeholder="Enter a meaningful project name"
          onChange={(event) => { duplicateName = event.target.value.trim(); }}
        />
      ),
      okText: "Duplicate",
      onOk: async () => {
        if (
          !duplicateName
          || duplicateName.toLocaleLowerCase() === baseName.toLocaleLowerCase()
          || /\(copy\s+\d{8}-\d{6}\)/i.test(duplicateName)
        ) {
          throw new Error("Enter a meaningful name without an automatic copy timestamp.");
        }
        const duplicated = await api.cloneProject(project.id, { name: duplicateName });
        await projects.reload();
        setSelectedProjectId(duplicated.id);
        message.success("Project duplicated");
      },
    });
  }

  function openProject(project: Project) {
    setSelectedProjectId(project.id);
    window.requestAnimationFrame(() => {
      projectEditorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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
          <FormSection title="Project identity" description="Choose the project name, asset and starter strategy.">
          <FormGrid>
            <Form.Item className="form-field--wide" name="name" label="Name" rules={[{ required: true }]}><Input placeholder="A Share RSI Strategy" /></Form.Item>
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
            <Form.Item name="templateKey" label="Strategy"><Select data-testid="project-template-select" virtual={false} options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormSection title="Market data" description="Defaults used when the project is opened for a backtest.">
          <FormGrid>
            <Form.Item name="market" label="Market"><Select data-testid="project-market-select" virtual={false} options={markets.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select data-testid="project-venue-select" virtual={false} disabled={selectedAssetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select data-testid="project-resolution-select" virtual={false} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select data-testid="project-data-type-select" virtual={false} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
          </FormGrid>
          </FormSection>
          <AdvancedFields>
            <FormGrid><Form.Item className="form-field--wide" name="algorithmClass" label="Algorithm Class"><Input placeholder="Auto-generated if empty" /></Form.Item></FormGrid>
          </AdvancedFields>
          <FormActions><Button type="primary" htmlType="submit">Create Project</Button></FormActions>
        </Form>
      </Card>
      {selectedProject && (
        <div ref={projectEditorRef}>
        <Card title="Project Configuration" style={{ marginTop: 16 }}>
          <div className="toolbar" style={{ marginBottom: 12 }}>
            <h2 className="page-title" style={{ margin: 0 }}>Current Project: {selectedProject.display_name || selectedProject.name}</h2>
            <Select
              style={{ width: 320 }}
              value={selectedProjectId}
              onChange={setSelectedProjectId}
              options={projects.data.map((project) => ({ value: project.id, label: project.display_name || project.name }))}
            />
          </div>
          <Form
            form={form}
            layout="vertical"
            initialValues={projectFormDefaults(selectedProject, templates.data, settings.data)}
            key={`${selectedProject.id}-${templates.data.length}-${settings.data.defaultMarket}`}
            onValuesChange={() => {
              setDirty(true);
              setPreflight(undefined);
            }}
          >
            <FormSection title="Basic information">
            <FormGrid>
              <Form.Item className="form-field--wide" name="name" label="Project Name" rules={[{ required: true }]}><Input placeholder="Project name" /></Form.Item>
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
              <Form.Item name="templateKey" label="Strategy"><Select data-testid="project-template-select" virtual={false} options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            </FormGrid>
            </FormSection>
            <FormSection title="Market data">
            <FormGrid>
              <Form.Item name="market" label="Market">
                <Select
                  data-testid="project-market-select"
                  virtual={false}
                  options={markets.data.map((item) => ({ value: item.key, label: item.name }))}
                  onChange={(value) => {
                    form.setFieldValue("source", defaultBacktestSource(value));
                    form.setFieldValue("benchmarkSymbol", defaultBenchmark(value));
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
              <Form.Item className="form-field--wide" name="source" label="Data Source">
                {selectedMarket === "china" ? (
                  <Select virtual={false} showSearch optionFilterProp="label" options={A_SHARE_BACKTEST_SOURCE_OPTIONS} />
                ) : (
                  <Input placeholder="optional provider source" />
                )}
              </Form.Item>
            </FormGrid>
            </FormSection>
            <FormSection title="Backtest defaults">
            <FormGrid>
              <Form.Item className="form-field--wide" name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={selectedAssetClass} market={selectedMarket} localSymbols={symbols} /></Form.Item>
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
              <Form.Item name="benchmarkSymbol" label="Benchmark" rules={[{ required: true, message: "Benchmark is required" }]}><Input /></Form.Item>
              <Form.Item name="feeModel" label="Fee Model"><Select virtual={false} options={[{ value: "default", label: "Default A-share costs" }, { value: "zero", label: "Zero Fees (research only)" }]} /></Form.Item>
              <Form.Item name="slippageModel" label="Slippage Model"><Select virtual={false} options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Slippage" }]} /></Form.Item>
            </FormGrid>
            </FormSection>
            {selectedTemplate && <FormSection title="Strategy parameters"><FormGrid>{strategyFields(selectedTemplate)}</FormGrid></FormSection>}
            <AdvancedFields label="Runtime environment">
              <FormGrid><Form.Item className="form-field--wide" name="dockerImage" label="Docker Image"><Input /></Form.Item></FormGrid>
            </AdvancedFields>
            {preflight?.ready && (
              <Alert
                type={preflight.repaired.length > 0 ? "warning" : "success"}
                showIcon
                style={{ marginBottom: 16 }}
                message={preflight.repaired.length > 0
                  ? `Data is ready after repairing: ${preflight.repaired.join(", ")}`
                  : `Data is ready from ${preflight.effectiveSource || "the selected source"}.`}
              />
            )}
            <FormActions>
              <Button icon={<SaveOutlined />} type="default" onClick={saveProject} loading={saving} disabled={saving || !selectedProjectId}>Save{dirty ? " Changes" : ""}</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={runBacktest} loading={submitting} disabled={submitting || !selectedProjectId}>Save & Run</Button>
            </FormActions>
          </Form>
          <div className="grid" style={{ marginTop: 16 }}>
            <Card>
              <Statistic title="Backtests" value={projectRuns.length} />
              <Button
                type="link"
                style={{ paddingInline: 0 }}
                onClick={() => navigate(`/backtests?view=history&projectId=${encodeURIComponent(selectedProject.id)}`)}
              >
                View project history
              </Button>
            </Card>
            <Card><Statistic title="Tasks" value={projectTasks.length} /></Card>
            <Card><Statistic title="Symbol" value={String(form.getFieldValue("symbol") || "-")} /></Card>
            <Card><Statistic title="Local Symbols" value={symbols.length} /></Card>
          </div>
        </Card>
        <Card
          title="Strategy Source"
          style={{ marginTop: 16 }}
          extra={<Space><Tag>{sourcePath || "main.py"}</Tag><Button data-testid="save-project-source" type="primary" loading={sourceLoading} disabled={!sourceDirty} onClick={saveSource}>Save Source</Button></Space>}
        >
          <Editor
            height="520px"
            language={sourcePath.endsWith(".cs") ? "csharp" : "python"}
            value={sourceCode}
            loading="Loading strategy source..."
            onChange={(value?: string) => { setSourceCode(value || ""); setSourceDirty(true); }}
            options={{ minimap: { enabled: false }, automaticLayout: true }}
          />
        </Card>
        </div>
      )}
      <Card title="Projects" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          size="small"
          dataSource={projects.data}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Name", render: (_, project) => project.display_name || project.name },
            { title: "Asset", render: (_, project) => String(project.config?.assetClass ?? "equity") },
            { title: "Venue", render: (_, project) => String(project.config?.venue ?? project.config?.market ?? "usa") },
            {
              title: "Strategy",
              render: (_, project) => templates.data.find((item) => item.key === project.config?.templateKey)?.name
                || String(project.config?.templateKey ?? "Custom")
            },
            { title: "Runs", render: (_, project) => project.run_count ?? 0 },
            { title: "Latest", render: (_, project) => project.latest_run_status ? <StatusTag status={project.latest_run_status} /> : "-" },
            { title: "Updated", dataIndex: "updated_at" },
            {
              title: "Actions",
              width: 240,
              render: (_, project) => (
                <Space>
                  <Button size="small" type="primary" onClick={() => openProject(project)}>Open</Button>
                  <Button size="small" icon={<CopyOutlined />} onClick={() => duplicateProject(project)}>Duplicate</Button>
                  <Button
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    aria-label={`Delete ${project.display_name || project.name}`}
                    onClick={() => deleteProject(project)}
                  />
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
  const catalog = useAsyncData<DataSyncCatalog>(api.dataCatalog, {
    provider: "tushare", entitlementPoints: 5000, boundary: "low_frequency", items: [], count: 0, available: 0,
    activeRun: null, latestRun: null, hasCompletedInitialSync: false, recommendedMode: "initial_full"
  }, false);
  const [syncRun, setSyncRun] = useState<DataSyncRun>();
  const derivedWatermarks = useAsyncData<DerivedLayerWatermarks>(api.derivedLayerWatermarks, {
    items: [],
    count: 0,
    layers: {},
    runs: [],
    schedule: { timezone: "Asia/Shanghai", days: "Monday-Friday", defaultTime: "19:30" },
    asOfDate: ""
  }, false);
  const [syncActionLoading, setSyncActionLoading] = useState(false);
  const loadOnDemandStorageTargets = useCallback(
    () => api.onDemandStorageTargets().then((result) => result.items),
    []
  );
  const storageTargets = useAsyncData<OnDemandStorageTarget[]>(
    loadOnDemandStorageTargets,
    [],
    false,
    "data:on-demand-storage-targets"
  );
  const [downloadForm] = Form.useForm();
  const [downloadDataset, setDownloadDataset] = useState<DataSyncCatalog["items"][number] | null>(null);
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadTasks, setDownloadTasks] = useState<Record<string, Task>>({});
  const [showAdditionalDatasets, setShowAdditionalDatasets] = useState(false);
  const selectedStorageTarget = Form.useWatch("storageTarget", downloadForm);
  const selectedStorage = storageTargets.data.find((item) => item.id === selectedStorageTarget);
  const [csvForm] = Form.useForm();
  const [csvImporting, setCsvImporting] = useState(false);
  const csvAssetClass = Form.useWatch("assetClass", csvForm) || "equity";
  const csvMarket = Form.useWatch("market", csvForm) || "china";

  const catalogSync = catalog.data.activeRun || undefined;
  const currentSync = catalogSync && catalogSync.id !== syncRun?.id
    ? catalogSync
    : (syncRun || catalogSync || catalog.data.latestRun || undefined);
  const activeSync = Boolean(currentSync && ["queued", "running", "cancelling"].includes(currentSync.status));
  const syncModeLabel = ({
    initial_full: "首次全量建库",
    incremental: "增量更新",
    resume_checkpoint: "从检查点继续",
    full_rebuild: "显式全量重建"
  } as Record<string, string>)[currentSync?.mode || ""] || currentSync?.mode || "自动判断";
  const syncItemsByDataset = useMemo(
    () => new Map((currentSync?.items ?? []).map((item) => [item.dataset_key, item])),
    [currentSync?.items]
  );
  const catalogRows = useMemo(
    () => catalog.data.items.map((item) => ({ ...item, syncItem: syncItemsByDataset.get(item.dataset_key) })),
    [catalog.data.items, syncItemsByDataset]
  );
  const oneClickCatalogRows = useMemo(
    () => catalogRows.filter((item) => item.sync_policy !== "on_demand"),
    [catalogRows]
  );
  const additionalCatalogRows = useMemo(
    () => catalogRows.filter((item) => item.sync_policy === "on_demand"),
    [catalogRows]
  );
  const visibleCatalogRows = showAdditionalDatasets
    ? [...oneClickCatalogRows, ...additionalCatalogRows]
    : oneClickCatalogRows;
  const syncProgress = useMemo(() => {
    const items = currentSync?.items ?? [];
    const terminal = new Set(["success", "partial", "skipped", "failed", "cancelled"]);
    const completed = items.filter((item) => terminal.has(item.status)).length;
    const active = items.find((item) => ["checking", "running"].includes(item.status));
    return {
      active,
      completed,
      total: items.length,
      percent: items.length ? Math.round((completed / items.length) * 100) : 0,
      denied: catalogRows.filter((item) => item.permission_status === "denied").length,
      retryable: catalogRows.filter((item) => item.permission_status === "retryable").length,
      onDemand: catalogRows.filter((item) => item.sync_policy === "on_demand").length,
    };
  }, [catalogRows, currentSync?.items]);

  function permissionReason(item: typeof catalogRows[number]) {
    if (item.sync_policy === "on_demand") return "按需获取，不参与一键更新";
    if (item.permission_status === "denied") return "无权限，本次已跳过";
    if (item.permission_status === "retryable") return "接口限频或暂时不可用，本次暂缓";
    if (item.permission_status === "empty") {
      return item.syncItem?.status === "success"
        ? "本轮同步已成功；权限探测区间无事件记录属于正常结果"
        : "接口已验证可访问；探测区间无事件记录属于正常结果";
    }
    if (item.permission_status === "available") return "已验证可访问";
    return "尚未验证";
  }

  function permissionDisplayStatus(item: typeof catalogRows[number]) {
    // An empty entitlement probe proves that the endpoint is reachable and
    // authorized. Event datasets such as suspend_d legitimately return no
    // rows for quiet probe windows, so do not present that as a failure-like
    // EMPTY state beside a successful synchronization.
    return item.permission_status === "empty" ? "available" : item.permission_status;
  }

  function syncError(item: typeof catalogRows[number]) {
    if (!item.syncItem?.error) return permissionReason(item);
    if (item.syncItem.status === "skipped") return permissionReason(item);
    try {
      const parsed = JSON.parse(item.syncItem.error) as { failed?: number };
      if (parsed.failed) return `${parsed.failed} 个标的失败，悬停查看详情`;
    } catch {
      // Provider errors are shown verbatim in the tooltip below.
    }
    return item.syncItem.error;
  }

  useEffect(() => {
    const activeId = currentSync?.id;
    if (!activeId) return;
    let cancelled = false;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const next = await api.dataSyncRun(activeId);
        if (!cancelled) {
          setSyncRun(next);
          if (!["queued", "running", "cancelling"].includes(next.status)) void catalog.reload();
        }
      } catch {
        // The next scheduled refresh retries transient polling failures.
      } finally {
        refreshing = false;
      }
    };
    void refresh();
    if (!["queued", "running", "cancelling"].includes(currentSync?.status || "")) return () => { cancelled = true; };
    const timer = window.setInterval(() => { void refresh(); }, 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [currentSync?.id, currentSync?.status]);

  useEffect(() => {
    const active = Object.entries(downloadTasks).filter(([, task]) => ["queued", "running"].includes(task.status));
    if (!active.length) return;
    let cancelled = false;
    let refreshing = false;
    const refresh = async () => {
      if (refreshing) return;
      refreshing = true;
      try {
        const items = await Promise.all(
          active.map(([dataset, task]) => api.task(task.id).then((next) => [dataset, next] as const))
        );
        if (!cancelled) setDownloadTasks((current) => ({ ...current, ...Object.fromEntries(items) }));
      } catch {
        // The next scheduled refresh retries transient polling failures.
      } finally {
        refreshing = false;
      }
    };
    const timer = window.setInterval(() => { void refresh(); }, 2000);
    void refresh();
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [Object.values(downloadTasks).map((task) => `${task.id}:${task.status}`).join("|")]);

  function openOnDemandDownload(item: DataSyncCatalog["items"][number]) {
    setDownloadDataset(item);
    downloadForm.resetFields();
    downloadForm.setFieldsValue({
      dataset: item.dataset_key,
      relativePath: `tushare-on-demand/${item.dataset_key}`,
      format: "parquet",
      startDate: dayjs().subtract(30, "day").format("YYYY-MM-DD"),
      endDate: dayjs().format("YYYY-MM-DD"),
      apiParameters: "{}",
    });
  }

  async function submitOnDemandDownload(values: Record<string, string>) {
    if (!downloadDataset) return;
    setDownloadLoading(true);
    try {
      const parsed = JSON.parse(values.apiParameters || "{}") as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("额外 API 参数必须是 JSON 对象");
      }
      const task = await api.createOnDemandDownload({
        dataset: downloadDataset.dataset_key,
        storageTarget: values.storageTarget,
        relativePath: values.relativePath,
        format: values.format as "parquet" | "jsonl",
        startDate: values.startDate || undefined,
        endDate: values.endDate || undefined,
        symbol: values.symbol || undefined,
        apiParameters: parsed as Record<string, unknown>,
      });
      setDownloadTasks((current) => ({ ...current, [downloadDataset.dataset_key]: task }));
      setDownloadDataset(null);
      message.success(`${task.title} 已进入按需下载队列`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDownloadLoading(false);
    }
  }

  async function startFullSync(mode: "auto" | "incremental" | "full_rebuild" = "auto") {
    setSyncActionLoading(true);
    try {
      const run = await api.createDataSyncRun(undefined, mode);
      setSyncRun(run);
      message.success("TuShare Pro 全库更新已进入后台队列");
      catalog.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSyncActionLoading(false);
    }
  }

  function confirmFullSync() {
    const incremental = catalog.data.hasCompletedInitialSync;
    Modal.confirm({
      title: incremental ? "增量更新本地全部市场与研究数据？" : "首次全量建立本地数据库？",
      content: incremental
        ? "将从已保存的水位和检查点开始，仅拉取新增或缺失数据。港美股和每小时级限频数据不会扫描，仅在实际使用时按需获取。"
        : "尚未发现成功完成的首次建库记录。将按当前权限全量建立本地市场与研究数据库，完成后系统会持久记住，后续按钮自动切换为增量更新。",
      okText: incremental ? "开始增量更新" : "开始全量建库",
      onOk: () => startFullSync("auto")
    });
  }

  function confirmRebuild() {
    Modal.confirm({
      title: "确认全量重建本地数据？",
      content: "全量重建会忽略增量水位并重新读取批量数据。仅在复权口径或已有数据确实错误时使用。",
      okText: "全量重建",
      okButtonProps: { danger: true },
      onOk: () => startFullSync("full_rebuild")
    });
  }

  async function cancelFullSync() {
    if (!currentSync) return;
    setSyncActionLoading(true);
    try {
      setSyncRun(await api.cancelDataSyncRun(currentSync.id));
      await catalog.reload();
      message.info("数据更新已停止，可从检查点继续");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSyncActionLoading(false);
    }
  }

  async function resumeFullSync() {
    if (!currentSync) return;
    setSyncActionLoading(true);
    try {
      setSyncRun(await api.resumeDataSyncRun(currentSync.id));
      message.success("数据更新已从检查点恢复");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSyncActionLoading(false);
    }
  }

  async function importCsv(values: any) {
    const file = values.file?.fileList?.[0]?.originFileObj;
    if (!file) return message.error("请选择 CSV 文件");
    if (!String(file.name || "").toLowerCase().endsWith(".csv")) {
      return message.error("文件扩展名必须是 .csv");
    }
    const preview = await file.slice(0, 64 * 1024).text();
    const lines = preview.replace(/^\uFEFF/, "").split(/\r?\n/).filter((line: string) => line.trim());
    if (lines.length < 2) {
      return message.error("CSV 必须包含表头和至少一行数据");
    }
    const headers = lines[0].split(",").map((value: string) => value.trim().replace(/^['\"]|['\"]$/g, ""));
    const requiredHeaders = ["timestamp", "open", "high", "low", "close", "volume"];
    const missingHeaders = requiredHeaders.filter((header) => !headers.includes(header));
    if (missingHeaders.length > 0) {
      return message.error(`CSV 缺少字段：${missingHeaders.join(", ")}。请下载并使用标准模板。`);
    }
    setCsvImporting(true);
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
    try {
      const result = await api.importCsv(formData);
      message.success(`CSV 导入成功：${Number(result.rows || 0).toLocaleString()} rows`);
      csvForm.resetFields();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setCsvImporting(false);
    }
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Data Library</h1></div>
      <Card
        title="Local MySQL · TuShare Pro 全库更新"
        style={{ marginBottom: 16 }}
        extra={<Space>
          <Button icon={<ReloadOutlined />} onClick={() => { catalog.reload(); derivedWatermarks.reload(); if (currentSync) api.dataSyncRun(currentSync.id).then(setSyncRun); }}>刷新</Button>
          {activeSync
            ? <Button danger loading={syncActionLoading} onClick={cancelFullSync}>{currentSync?.status === "cancelling" ? "强制停止" : "停止"}</Button>
            : currentSync && ["failed", "cancelled", "partial"].includes(currentSync.status)
              ? <>
                  <Button type="primary" loading={syncActionLoading} onClick={resumeFullSync}>继续检查点</Button>
                  <Button loading={syncActionLoading} onClick={() => startFullSync("incremental")}>重新增量</Button>
                  <Button danger loading={syncActionLoading} onClick={confirmRebuild}>全量重建</Button>
                </>
              : <Button data-testid="sync-all-data-button" type="primary" icon={<DatabaseOutlined />} loading={syncActionLoading} onClick={confirmFullSync}>{catalog.data.hasCompletedInitialSync ? "一键增量更新" : "一键全量更新"}</Button>}
        </Space>}
      >
        {catalog.error && <Alert type="warning" showIcon message="同步目录尚未初始化" description={catalog.error.message} style={{ marginBottom: 12 }} />}
        <div className="grid">
          <Card size="small"><Statistic title="TuShare 权限" value={`${catalog.data.entitlementPoints} 积分`} /></Card>
          <Card size="small"><Statistic title="批量数据集" value={catalog.data.count - syncProgress.onDemand} /></Card>
          <Card size="small"><Statistic title="按需数据集" value={syncProgress.onDemand} /></Card>
          <Card size="small">
            <Statistic
              title="MySQL 物理占用（一键更新不限额）"
              value={((catalog.data.storage?.databaseBytes || 0) / 1024 / 1024 / 1024).toFixed(1)}
              suffix="GiB"
            />
          </Card>
          <Card size="small"><Statistic title="已验证可用" value={catalog.data.available} /></Card>
          <Card size="small"><Statistic title="更新模式" value={syncModeLabel} /></Card>
          <Card size="small"><Statistic title="同步状态" value={currentSync?.status || "idle"} /></Card>
        </div>
        <Alert
          type="info"
          showIcon
          style={{ margin: "12px 0" }}
          message="实际接口探测优先于积分推断"
          description={`一键更新只保留 A 股执行数据、基准指数及 CFFEX/SSE 期货期权合约目录。具体合约行情、财务、基金、港美股、宏观及特色数据仅在 Preview、项目、研究或回测实际使用时查询。当前有 ${syncProgress.denied} 个无权限数据集、${syncProgress.onDemand} 个按需数据集、${syncProgress.retryable} 个暂时限频数据集。`}
        />
        <Card
          size="small"
          title="独立派生层水位"
          style={{ marginBottom: 12 }}
          extra={<span className="data-catalog-meta">{derivedWatermarks.data.schedule.days} {derivedWatermarks.data.schedule.defaultTime} {derivedWatermarks.data.schedule.timezone}</span>}
        >
          <Space wrap>
            {(["parquet", "clickhouse"] as const).map((layer) => {
              const state = derivedWatermarks.data.layers[layer];
              return (
                <Tag key={layer} color={!state ? "default" : state.failed ? "error" : state.ready === state.count ? "success" : "warning"}>
                  {layer} · {state?.watermark || "未建立水位"} · ready {state?.ready || 0}/{state?.count || 0}
                </Tag>
              );
            })}
            {derivedWatermarks.data.runs[0] && (
              <span className="data-catalog-meta">
                最近维护 {derivedWatermarks.data.runs[0].status} · {derivedWatermarks.data.runs[0].created_at}
              </span>
            )}
          </Space>
        </Card>
        {currentSync && (
          <Card size="small" style={{ marginBottom: 12 }}>
            <Space direction="vertical" style={{ width: "100%" }} size={4}>
              <Space wrap>
                <StatusTag status={currentSync.status} />
                {currentSync.canonical_status && (
                  <Tag color={currentSync.canonical_status === "ready" ? "success" : "processing"}>
                    MySQL {currentSync.canonical_status}
                  </Tag>
                )}
                {Boolean(currentSync.derivedStatus?.status) && (
                  <Tag color={currentSync.derivedStatus?.status === "ready" ? "success" : currentSync.derivedStatus?.status === "partial" ? "warning" : "processing"}>
                    派生层 {String(currentSync.derivedStatus?.status)}
                    {currentSync.derivedStatus?.completed !== undefined && currentSync.derivedStatus?.total
                      ? ` ${String(currentSync.derivedStatus?.completed)}/${String(currentSync.derivedStatus?.total)}`
                      : ""}
                  </Tag>
                )}
                <strong>
                  {syncProgress.active
                    ? `${syncProgress.active.status === "checking" ? "正在检查" : "正在更新"}：${syncProgress.active.dataset_key}`
                    : currentSync.status === "queued"
                      ? "等待数据 worker 接收任务"
                      : `已处理 ${syncProgress.completed}/${syncProgress.total} 个数据集`}
                </strong>
                {Boolean(syncProgress.active?.checkpoint?.symbol) && syncProgress.active && (
                  <span>
                    {String(syncProgress.active.checkpoint?.symbol)} · {String(syncProgress.active.checkpoint?.index ?? "-")}/{String(syncProgress.active.checkpoint?.total ?? "-")}
                  </span>
                )}
                {syncProgress.active?.metrics?.phase && <Tag color="processing">{syncProgress.active.metrics.phase}</Tag>}
                {syncProgress.active?.metrics?.apiCalls !== undefined && (
                  <span>
                    API {syncProgress.active.metrics.apiCalls.toLocaleString()} 次真实调用
                    {syncProgress.active.metrics.apiQuotaPerMinute !== undefined
                      ? ` · 限额 ${syncProgress.active.metrics.apiQuotaPerMinute}/min`
                      : ""}
                  </span>
                )}
                {syncProgress.active?.metrics?.endpointCalls && Object.keys(syncProgress.active.metrics.endpointCalls).length > 0 && (
                  <span>
                    {Object.entries(syncProgress.active.metrics.endpointCalls)
                      .sort(([left], [right]) => left.localeCompare(right))
                      .map(([endpoint, count]) => `${endpoint} ${count}`)
                      .join(" · ")}
                  </span>
                )}
                {syncProgress.active?.metrics?.downloadedRows !== undefined && (
                  <span>下载 {syncProgress.active.metrics.downloadedRows.toLocaleString()} rows</span>
                )}
                {syncProgress.active?.metrics?.committedRows !== undefined && (
                  <span>入库 {syncProgress.active.metrics.committedRows.toLocaleString()} rows</span>
                )}
                {syncProgress.active?.metrics?.writeRowsPerSecond !== undefined && (
                  <span>写入 {Math.round(syncProgress.active.metrics.writeRowsPerSecond).toLocaleString()} rows/s</span>
                )}
                {syncProgress.active?.metrics?.unitsPerSecond !== undefined && (
                  <span>处理 {syncProgress.active.metrics.unitsPerSecond.toFixed(1)} 个工作单元/s</span>
                )}
                {syncProgress.active?.metrics?.emptyUnits !== undefined && (
                  <span>空结果 {syncProgress.active.metrics.emptyUnits.toLocaleString()} 个</span>
                )}
                {syncProgress.active?.metrics?.validatedRows !== undefined && (
                  <span>校验 {syncProgress.active.metrics.validatedRows.toLocaleString()} rows</span>
                )}
                {Boolean(syncProgress.active?.metrics?.quarantinedRows) && (
                  <span>隔离 {syncProgress.active?.metrics?.quarantinedRows?.toLocaleString()} rows</span>
                )}
                {syncProgress.active?.metrics?.etaSeconds !== undefined && syncProgress.active.metrics.etaSeconds !== null && (
                  <span>
                    ETA {syncProgress.active.metrics.etaSeconds >= 60
                      ? `${Math.ceil(syncProgress.active.metrics.etaSeconds / 60)} 分钟`
                      : `${Math.ceil(syncProgress.active.metrics.etaSeconds)} 秒`}
                  </span>
                )}
                {syncProgress.active?.metrics?.diskFreeBytes !== undefined && (
                  <span>
                    磁盘可用 {(syncProgress.active.metrics.diskFreeBytes / 1024 / 1024 / 1024).toFixed(1)} GiB
                    {syncProgress.active.metrics.diskReserveBytes !== undefined
                      ? ` · 安全预留 ${(syncProgress.active.metrics.diskReserveBytes / 1024 / 1024 / 1024).toFixed(1)} GiB`
                      : ""}
                  </span>
                )}
                {syncProgress.active?.metrics?.databaseBytes !== undefined && (
                  <span>
                    MySQL 物理占用 {(syncProgress.active.metrics.databaseBytes / 1024 / 1024 / 1024).toFixed(1)} GiB · 一键更新不限额
                  </span>
                )}
              </Space>
              <Progress percent={syncProgress.percent} size="small" status={currentSync.status === "failed" ? "exception" : "active"} />
            </Space>
          </Card>
        )}
        {currentSync?.error && <Alert type="error" showIcon message={currentSync.error} style={{ marginBottom: 12 }} />}
        {catalogRows.length > 0 && (
          <>
            <div className="data-catalog-visibility">
              <div>
                <strong>一键更新数据集（{oneClickCatalogRows.length}）</strong>
                <div className="data-catalog-meta">默认仅显示参与一键全量/增量更新的数据及状态。</div>
              </div>
              {additionalCatalogRows.length > 0 && (
                <Button onClick={() => setShowAdditionalDatasets((current) => !current)}>
                  {showAdditionalDatasets
                    ? "收起其他数据集"
                    : `展开其他按需数据集（${additionalCatalogRows.length}）`}
                </Button>
              )}
            </div>
            <Table
              className="data-catalog-table"
              size="small"
              rowKey="dataset_key"
              dataSource={visibleCatalogRows}
              pagination={showAdditionalDatasets ? { pageSize: 20, showSizeChanger: true } : false}
              tableLayout="fixed"
              columns={[
              {
                title: "数据集",
                width: "21%",
                render: (_, item) => {
                  const display = syncError(item);
                  const detail = item.syncItem?.error || item.permission_reason || display;
                  return (
                    <div>
                      <div className="data-catalog-primary">{item.dataset_key}</div>
                      <div className="data-catalog-meta">{item.category}</div>
                      <Tooltip title={detail}>
                        <div className="data-catalog-note">{display}</div>
                      </Tooltip>
                    </div>
                  );
                }
              },
              {
                title: "状态",
                width: "18%",
                render: (_, item) => (
                  <div className="data-catalog-tags">
                    <Tooltip title={item.sync_policy === "on_demand" ? "按需获取，不参与一键更新" : "参与一键更新"}>
                      <Tag color={item.sync_policy === "on_demand" ? "blue" : undefined}>
                        {item.sync_policy === "on_demand" ? "按需" : "批量"}
                      </Tag>
                    </Tooltip>
                    <Tooltip title={permissionReason(item)}>
                      <span><StatusTag status={permissionDisplayStatus(item)} /></span>
                    </Tooltip>
                    {item.syncItem && (
                      <Tooltip title="本轮同步状态"><span><StatusTag status={item.syncItem.status} /></span></Tooltip>
                    )}
                    {Boolean(item.syncItem?.failed) && <Tag color="error">失败 {item.syncItem?.failed}</Tag>}
                  </div>
                )
              },
              {
                title: "同步进度",
                width: "28%",
                render: (_, item) => {
                  const checkpoint = item.syncItem?.checkpoint as { symbol?: string; index?: number; total?: number } | null | undefined;
                  const checkpointIndex = Number(checkpoint?.index || 0);
                  const checkpointTotal = Number(checkpoint?.total || 0);
                  const percent = checkpointTotal ? Math.min(100, Math.round(checkpointIndex * 100 / checkpointTotal)) : 0;
                  const writeRate = item.syncItem?.metrics?.writeRowsPerSecond;
                  if (!item.syncItem) return <span className="data-catalog-meta">尚未同步</span>;
                  return (
                    <div className="data-catalog-progress">
                      {checkpointTotal > 0 && (
                        <>
                          <div className="data-catalog-progress-title">
                            <span>{checkpoint?.symbol || "进度"}</span>
                            <span>{checkpointIndex.toLocaleString()} / {checkpointTotal.toLocaleString()}</span>
                          </div>
                          <Progress percent={percent} size="small" showInfo={false} />
                        </>
                      )}
                      <div className="data-catalog-stats">
                        <span>处理 {item.syncItem.processed.toLocaleString()}</span>
                        <span>入库 {item.syncItem.inserted.toLocaleString()}</span>
                        <span>写入 {writeRate !== undefined ? `${Math.round(writeRate).toLocaleString()}/s` : "-"}</span>
                      </div>
                    </div>
                  );
                }
              },
              {
                title: "数据范围",
                width: "20%",
                render: (_, item) => (
                  <div>
                    <div className="data-catalog-primary">
                      {Number(item.row_count || 0).toLocaleString()} <span className="data-catalog-unit">rows</span>
                    </div>
                    <div className="data-catalog-meta">
                      {item.first_data_date ? `${item.first_data_date} → ${item.last_data_date || "-"}` : "暂无覆盖日期"}
                    </div>
                  </div>
                )
              },
              {
                title: "操作",
                width: "13%",
                render: (_, item) => {
                  if (item.sync_policy !== "on_demand") return <span className="data-catalog-meta">随一键更新</span>;
                  const task = downloadTasks[item.dataset_key];
                  const busy = Boolean(task && ["queued", "running"].includes(task.status));
                  return (
                    <div className="data-catalog-actions">
                      <Tooltip title={activeSync ? "一键更新进行中，为避免共享 TuShare 配额竞争，完成后可单独下载" : undefined}>
                        <Button
                          size="small"
                          icon={<CloudDownloadOutlined />}
                          loading={busy}
                          disabled={item.permission_status === "denied" || activeSync}
                          onClick={() => openOnDemandDownload(item)}
                        >
                          {task?.status === "success" ? "再次下载" : "单独下载"}
                        </Button>
                      </Tooltip>
                      {task && !busy && (
                        <Tooltip title={task.error || task.artifacts?.[0] || task.status}>
                          <span><StatusTag status={task.status} /></span>
                        </Tooltip>
                      )}
                    </div>
                  );
                }
              }
              ]}
            />
          </>
        )}
      </Card>
      <Modal
        title={`单独下载数据集${downloadDataset ? ` · ${downloadDataset.dataset_key}` : ""}`}
        open={Boolean(downloadDataset)}
        onCancel={() => setDownloadDataset(null)}
        onOk={() => downloadForm.submit()}
        okText="开始下载"
        confirmLoading={downloadLoading}
        width={680}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="文件只写入你明确选择的存储位置"
          description="存储目标必须手动选择。外置硬盘或 NAS 需要先挂载到服务，并通过 LEAN_ON_DEMAND_EXPORT_ROOTS 配置后才会出现在列表中。"
        />
        <Form form={downloadForm} layout="vertical" onFinish={submitOnDemandDownload}>
          <Form.Item name="dataset" label="数据集"><Input disabled /></Form.Item>
          <FormGrid modal>
            <Form.Item name="storageTarget" label="下载地址" rules={[{ required: true, message: "请选择下载地址" }]}>
              <Select
                placeholder="请选择，不使用默认硬盘目录"
                loading={storageTargets.loading}
                options={storageTargets.data.map((item) => ({
                  value: item.id,
                  label: `${item.label} · ${item.displayPath}`,
                }))}
              />
            </Form.Item>
            <Form.Item name="relativePath" label="目标子目录" rules={[{ required: true }]}>
              <Input placeholder="例如 tushare-on-demand/fund_nav" />
            </Form.Item>
          </FormGrid>
          {selectedStorage && (
            <Alert type="success" showIcon style={{ marginBottom: 12 }} message={`实际保存到：${selectedStorage.displayPath}`} />
          )}
          <FormGrid modal>
            <Form.Item name="format" label="文件格式" rules={[{ required: true }]}>
              <Select options={[{ value: "parquet", label: "Parquet" }, { value: "jsonl", label: "JSON Lines" }]} />
            </Form.Item>
            <Form.Item
              name="symbol"
              label="标的代码"
              rules={[{ required: downloadDataset?.scope_type === "instrument", message: "该数据集需要标的代码" }]}
            >
              <Input placeholder={downloadDataset?.scope_type === "instrument" ? "必填，例如 600519" : "可选"} />
            </Form.Item>
            <Form.Item label="接口限制">
              <Input disabled value={downloadDataset?.rate_limit_per_hour ? `${downloadDataset.rate_limit_per_hour} 次/小时` : "全局 500 次/分钟"} />
            </Form.Item>
          </FormGrid>
          <FormGrid modal>
            <Form.Item name="startDate" label="开始日期"><Input placeholder="YYYY-MM-DD" /></Form.Item>
            <Form.Item name="endDate" label="结束日期"><Input placeholder="YYYY-MM-DD" /></Form.Item>
          </FormGrid>
          <Form.Item
            name="apiParameters"
            label="额外 TuShare 参数（JSON，可选）"
            tooltip="用于 index_code、exchange、trade_date 等数据集专有参数；这里的值会覆盖自动生成的参数。"
          >
            <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} placeholder='例如 {"exchange":"CFFEX"}' />
          </Form.Item>
        </Form>
      </Modal>
      <Card title="按数据集预览" style={{ marginTop: 16 }}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="10 个一键更新数据集已按业务对象分组"
          description="股票页合并 stock_basic、daily、adj_factor、suspend_d、stk_limit；其余数据集分别按交易日历、指数、期货和期权预览。"
        />
        <Tabs
          destroyOnHidden={false}
          items={[
            {
              key: "stocks",
              label: "股票 Preview",
              children: <MarketDataDownloader unboundedPreview showLimitInput={false} />
            },
            {
              key: "calendar",
              label: "交易日历 Preview",
              children: <DatasetPreviewPanel datasets={[
                { key: "trade_cal", label: "交易日历 · trade_cal", keywordPlaceholder: "可按市场或来源筛选" }
              ]} />
            },
            {
              key: "indices",
              label: "指数 Preview",
              children: <DatasetPreviewPanel datasets={[
                { key: "index_basic", label: "指数资料 · index_basic", keywordPlaceholder: "指数代码、名称、发布机构" },
                { key: "index_daily", label: "指数日线 · index_daily", keywordPlaceholder: "指数代码，例如 000300.SH" }
              ]} />
            },
            {
              key: "futures",
              label: "期货 Preview",
              children: <DatasetPreviewPanel datasets={[
                { key: "fut_basic", label: "期货合约 · fut_basic", keywordPlaceholder: "合约代码、名称或品种" }
              ]} />
            },
            {
              key: "options",
              label: "期权 Preview",
              children: <DatasetPreviewPanel datasets={[
                { key: "opt_basic", label: "期权合约 · opt_basic", keywordPlaceholder: "期权代码、名称或标的" }
              ]} />
            }
          ]}
        />
      </Card>
      <Card
        title="Import CSV"
        style={{ marginTop: 16 }}
        extra={<Button icon={<FileTextOutlined />} href="/api/data/import-csv/template">下载 CSV 模板</Button>}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="请使用标准日线 OHLCV 模板"
          description="必需字段：timestamp, open, high, low, close, volume。日期使用 YYYY-MM-DD；价格必须大于0；high 不得低于 open/close，low 不得高于 open/close；volume 必须为非负数。股票代码在下方单独选择，不要写入 CSV。"
        />
        <Form form={csvForm} layout="vertical" onFinish={importCsv} initialValues={{ assetClass: "equity", market: "china" }}>
          <FormGrid>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={csvAssetClass} market={csvMarket} /></Form.Item>
            <Form.Item name="assetClass" label="Asset Class"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          </FormGrid>
          <Space wrap>
            <Form.Item name="file" label="CSV 文件" rules={[{ required: true, message: "请选择 CSV 文件" }]}>
              <Upload
                accept=".csv,text/csv"
                beforeUpload={(file) => {
                  if (!file.name.toLowerCase().endsWith(".csv")) {
                    message.error("只支持 .csv 文件");
                    return Upload.LIST_IGNORE;
                  }
                  return false;
                }}
                maxCount={1}
              >
                <Button>选择 CSV</Button>
              </Upload>
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={csvImporting}>校验并导入</Button>
          </Space>
        </Form>
      </Card>
    </>
  );
}

type BacktestHistoryFilters = {
  name?: string;
  status?: string;
  market?: string;
  projectId?: string;
  symbol?: string;
};

function backtestHistoryFiltersFromSearch(searchParams: URLSearchParams): BacktestHistoryFilters {
  const filters: BacktestHistoryFilters = {};
  (["name", "status", "market", "projectId", "symbol"] as const).forEach((key) => {
    const value = searchParams.get(key)?.trim();
    if (value) filters[key] = value;
  });
  return filters;
}

export function BacktestsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const settings = useAsyncData<AppSettings>(api.settings, defaultSettings);
  const [filters, setFilters] = useState<BacktestHistoryFilters>(() => backtestHistoryFiltersFromSearch(searchParams));
  const loadRuns = useCallback(() => api.backtests(filters), [filters]);
  const runsCacheKey = useMemo(() => `backtests:${JSON.stringify(filters)}`, [filters]);
  const runs = useAsyncData(loadRuns, [], true, runsCacheKey);
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
  const [preflight, setPreflight] = useState<BacktestPreflight>();
  const [batchPreset, setBatchPreset] = useState<{
    example: WorkflowExample;
    project: Project;
    defaults: Record<string, unknown>;
  }>();
  const activeView = searchParams.get("view") === "history" ? "history" : "run";
  const runScope = searchParams.get("scope") === "batch" ? "batch" : "single";
  const searchParamsKey = searchParams.toString();

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
    let active = true;
    api.symbols(market, assetClass, venue, resolution, dataType)
      .then((result) => {
        if (active) setSymbols(result.symbols);
      })
      .catch((error) => {
        if (active) message.error((error as Error).message);
      });
    return () => {
      active = false;
    };
  }, [assetClass, dataType, market, resolution, venue]);

  useEffect(() => {
    const nextFilters = backtestHistoryFiltersFromSearch(searchParams);
    setFilters((current) => (
      JSON.stringify(current) === JSON.stringify(nextFilters) ? current : nextFilters
    ));
    if (searchParams.get("view") === "history") {
      historyForm.resetFields();
      historyForm.setFieldsValue(nextFilters);
    }
  }, [historyForm, searchParamsKey]);

  function selectView(view: string) {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set("view", view);
    setSearchParams(nextSearchParams);
  }

  function selectRunScope(scope: "single" | "batch") {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.set("view", "run");
    nextSearchParams.set("scope", scope);
    setSearchParams(nextSearchParams);
  }

  function applyExample(project: Project, example: WorkflowExample) {
    void projects.reload();
    const defaults = example.defaults || {};
    const isBatch = example.mode !== "independent"
      || Boolean(defaults.universeCode)
      || example.tags.includes("批量")
      || ["symbol-strategies", "strategy-symbol-matrix"].includes(example.key);
    if (isBatch) {
      setBatchPreset({ example, project, defaults });
      selectRunScope("batch");
      return;
    }
    const nextMarket = String(defaults.market || projectMarket(project));
    const nextAssetClass = projectAssetClass(project);
    const nextVenue = projectVenue(project);
    const nextResolution = projectResolution(project);
    const nextDataType = projectDataType(project);
    setSelectedProjectId(project.id);
    setAssetClass(nextAssetClass);
    setMarket(nextMarket);
    setVenue(nextVenue);
    setResolution(nextResolution);
    setDataType(nextDataType);
    form.setFieldsValue({
      projectId: project.id,
      name: example.name,
      symbol: defaults.symbol || (nextMarket === "china" ? "000001" : nextMarket === "hongkong" ? "00700" : "AAPL"),
      assetClass: nextAssetClass,
      market: nextMarket,
      venue: nextVenue,
      resolution: nextResolution,
      dataType: nextDataType,
      benchmarkSymbol: defaultBenchmark(nextMarket),
      source: defaultBacktestSource(nextMarket),
      parameters: defaults.parameters || templateDefaults(projectTemplate(project, templates.data))
    });
    setPreflight(undefined);
    selectRunScope("single");
  }

  function applyHistoryFilters(values: BacktestHistoryFilters) {
    const nextFilters = Object.fromEntries(
      Object.entries(values).filter(([, value]) => String(value ?? "").trim())
    ) as BacktestHistoryFilters;
    setFilters(nextFilters);
    const nextSearchParams = new URLSearchParams();
    nextSearchParams.set("view", "history");
    Object.entries(nextFilters).forEach(([key, value]) => nextSearchParams.set(key, String(value)));
    setSearchParams(nextSearchParams, { replace: true });
  }

  async function submit(values: any) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const payload = buildBacktestRequest({
        ...values,
      }, { assetClass, market, venue, resolution, dataType, projectId: values.projectId });
      const readiness = await api.preflightBacktest(payload);
      setPreflight(readiness);
      const run = await api.createBacktest(payload);
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
      <Tabs
        activeKey={activeView}
        onChange={selectView}
        items={[
          {
            key: "run",
            label: "Run Backtest",
            children: (
              <>
                <ExampleGallery kind="backtest" onCreated={applyExample} />
                <Card
                  size="small"
                  title="Run configuration"
                  style={{ marginTop: 16 }}
                  extra={(
                    <Select
                      aria-label="Backtest run scope"
                      value={runScope}
                      style={{ width: 180 }}
                      onChange={selectRunScope}
                      options={[
                        { value: "single", label: "单次回测" },
                        { value: "batch", label: "批量回测" }
                      ]}
                    />
                  )}
                >
                  <Alert
                    showIcon
                    type="info"
                    message={runScope === "single" ? "提交一个回测运行" : "按配置展开批次"}
                    description={runScope === "single"
                      ? "使用一个项目、一个标的和一个时间窗口，提交前执行同一套 preflight。"
                      : "项目、标的/PIT 股票池、窗口和参数共同决定工作单元数；每个子回测仍执行同一套 preflight。"}
                  />
                </Card>
                {runScope === "single" ? (
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
            benchmarkSymbol: defaultBenchmark(settings.data.defaultMarket),
            feeModel: "default",
            slippageModel: "default",
            source: defaultBacktestSource(settings.data.defaultMarket),
            allowResearchSource: false,
            dockerImage: settings.data.dockerImage,
            parameters: templateDefaults(selectedTemplate)
          }}
        >
          <FormSection title="Strategy" description="Select the project snapshot and give this run a recognizable name.">
          <FormGrid>
            <Form.Item className="form-field--wide" name="projectId" label="Project" rules={[{ required: true, message: "Project strategy is required" }]}><Select data-testid="backtest-project-select" virtual={false} showSearch optionFilterProp="label" allowClear onChange={(value) => { setSelectedProjectId(value); setPreflight(undefined); const project = projects.data.find((item) => item.id === value); if (project) { const nextMarket = projectMarket(project); const next = { assetClass: projectAssetClass(project), market: nextMarket, venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), benchmarkSymbol: defaultBenchmark(nextMarket), source: defaultBacktestSource(nextMarket), parameters: templateDefaults(projectTemplate(project, templates.data)) }; setAssetClass(next.assetClass); setMarket(next.market); setVenue(next.venue); setResolution(next.resolution); setDataType(next.dataType); form.setFieldsValue(next); } }} options={projects.data.map((project) => ({ value: project.id, label: project.display_name || project.name }))} /></Form.Item>
            <Form.Item className="form-field--wide" name="name" label="Backtest Name" rules={[{ required: true, message: "Backtest name is required" }]}><Input data-testid="backtest-name-input" /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormSection title="Instrument & data">
          <FormGrid>
            <Form.Item name="assetClass" label="Asset"><Select data-testid="backtest-asset-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { const nextVenue = defaultVenueFor(value, assetClasses.data, market); setAssetClass(value); setVenue(nextVenue); form.setFieldsValue({ venue: nextVenue }); }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select data-testid="backtest-market-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { setMarket(value); if (assetClass === "equity") { setVenue(value); form.setFieldValue("venue", value); } form.setFieldValue("benchmarkSymbol", defaultBenchmark(value)); form.setFieldValue("source", defaultBacktestSource(value)); }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} onChange={setVenue} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select data-testid="backtest-resolution-select" virtual={false} showSearch optionFilterProp="label" onChange={setResolution} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select data-testid="backtest-data-type-select" virtual={false} showSearch optionFilterProp="label" onChange={setDataType} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item className="form-field--wide" name="symbol" label="Symbol" rules={[{ required: true, message: "Symbol is required" }]}><SecuritySearch data-testid="backtest-symbol-input" assetClass={assetClass} market={market} localSymbols={symbols} /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormSection title="Period">
          <FormGrid>
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
          </FormGrid>
          </FormSection>
          <FormSection title="Execution configuration">
          <FormGrid>
            <Form.Item name="feeModel" label="Fee Model"><Select data-testid="backtest-fee-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default A-share costs" }, { value: "zero", label: "Zero Fees (research only)" }]} /></Form.Item>
            <Form.Item name="slippageModel" label="Slippage Model"><Select data-testid="backtest-slippage-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Slippage" }]} /></Form.Item>
            <Form.Item className="form-field--wide" name="source" label="Data Source">
              {market === "china" ? (
                <Select data-testid="backtest-source-select" virtual={false} showSearch optionFilterProp="label" options={A_SHARE_BACKTEST_SOURCE_OPTIONS} />
              ) : (
                <Input data-testid="backtest-source-input" placeholder="optional provider source" />
              )}
            </Form.Item>
            <Form.Item
              className="form-field--wide"
              name="allowResearchSource"
              valuePropName="checked"
              label="Research data override"
            >
              <Checkbox data-testid="backtest-allow-research-source">
                Allow explicitly selected unverified/research data for this research run
              </Checkbox>
            </Form.Item>
          </FormGrid>
          </FormSection>
          {selectedTemplate && <FormSection title="Strategy parameters"><FormGrid>{strategyFields(selectedTemplate)}</FormGrid></FormSection>}
          <AdvancedFields label="Runtime environment">
            <FormGrid><Form.Item className="form-field--wide" name="dockerImage" label="Docker Image"><Input /></Form.Item></FormGrid>
          </AdvancedFields>
          {preflight?.ready && (
            <Alert
              type={preflight.repaired.length > 0 ? "warning" : "success"}
              showIcon
              style={{ marginBottom: 16 }}
              message={preflight.repaired.length > 0
                ? `Data repaired and ready: ${preflight.repaired.join(", ")}`
                : `Data ready from ${preflight.effectiveSource || "the selected source"}.`}
            />
          )}
          <FormActions><Button data-testid="run-backtest-button" type="primary" icon={<PlayCircleOutlined />} htmlType="submit" loading={submitting} disabled={submitting}>Run Backtest</Button></FormActions>
        </Form>
      </Card>
                ) : (
                  <BatchWorkbench kind="backtest" projects={projects.data} preset={batchPreset} />
                )}
              </>
            )
          },
          {
            key: "history",
            label: `History (${runs.data.length})`,
            children: (
              <Card title="Backtest History">
        <p className="muted">All backtest records are managed here. Use project and run filters to narrow the canonical history.</p>
        <Form form={historyForm} layout="inline" style={{ marginBottom: 12 }} initialValues={filters} onFinish={applyHistoryFilters}>
          <Form.Item name="name" label="Name"><Input placeholder="Name" style={{ width: 180 }} /></Form.Item>
          <Form.Item name="status" label="Status"><Select data-testid="history-status-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Status" style={{ width: 150 }} options={["created", "queued", "running", "success", "failed", "cancelled"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="market" label="Market"><Select data-testid="history-market-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Market" style={{ width: 150 }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          <Form.Item name="projectId" label="Project"><Select data-testid="history-project-select" virtual={false} showSearch optionFilterProp="label" allowClear placeholder="Project" style={{ width: 220 }} options={projects.data.map((project) => ({ value: project.id, label: project.display_name || project.name }))} /></Form.Item>
          <Form.Item name="symbol" label="Symbol"><SecuritySearch market="all" placeholder="代码 / 公司" style={{ width: 180 }} /></Form.Item>
          <Button htmlType="submit">Filter</Button>
          <Button onClick={() => { historyForm.resetFields(); applyHistoryFilters({}); }}>Clear</Button>
        </Form>
        <RunsTable runs={runsForDisplay} onOpen={(id) => navigate(`/runs/${id}`)} onDelete={async (run) => { await api.deleteBacktest(run.id); await runs.reload(); }} />
              </Card>
            )
          }
        ]}
      />
    </>
  );
}

function recordRows(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function stableRecordKey(row: Record<string, unknown>, prefix: string) {
  const identity = row.id
    ?? row.orderId
    ?? row.order_id
    ?? row.tradeId
    ?? row.trade_id
    ?? [row.symbol, row.entry_time, row.exit_time].filter((item) => item != null).join("-");
  if (identity !== "") return `${prefix}-${String(identity)}`;
  try {
    return `${prefix}-${JSON.stringify(row)}`;
  } catch {
    return `${prefix}-${shortValue(row, 240)}`;
  }
}

export function RunDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [run, setRun] = useState<BacktestRun>();
  const [chart, setChart] = useState<ChartData>();
  const [chartError, setChartError] = useState<string>();
  const [result, setResult] = useState<BacktestResult>();
  const [trust, setTrust] = useState<BacktestValidationResponse>();
  const [admission, setAdmission] = useState<BacktestAdmissionResponse>();
  const [logs, setLogs] = useState("");
  const [metricQuery, setMetricQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>();
  const reloadInFlight = useRef<{ id: string; promise: Promise<void> } | undefined>(undefined);
  const currentRunId = useRef(id);
  currentRunId.current = id;
  const active = run ? ["created", "queued", "checking", "running"].includes(run.status) : false;
  const reload = useCallback(() => {
    if (!id) return Promise.resolve();
    if (reloadInFlight.current?.id === id) return reloadInFlight.current.promise;

    const requestedId = id;
    const load = async () => {
      const [next, nextLogs, nextTrust, nextAdmission] = await Promise.all([
        api.backtest(requestedId),
        api.logs(requestedId),
        api.backtestValidation(requestedId).catch(() => undefined),
        api.backtestAdmission(requestedId).catch(() => undefined)
      ]);
      if (currentRunId.current !== requestedId) return;
      setRun(next);
      setLogs(nextLogs.logs);
      setTrust(nextTrust);
      setAdmission(nextAdmission);

      if (!next.result_json_path) {
        setChart(undefined);
        setChartError(undefined);
        setResult(undefined);
        setLastUpdated(new Date());
        return;
      }

      const [chartOutcome, resultOutcome] = await Promise.allSettled([
        api.chartData(requestedId),
        api.backtestResult(requestedId)
      ]);
      if (currentRunId.current !== requestedId) return;
      if (chartOutcome.status === "fulfilled") {
        setChart(chartOutcome.value);
        setChartError(undefined);
      } else {
        setChart(undefined);
        setChartError(chartOutcome.reason instanceof Error ? chartOutcome.reason.message : "Chart data could not be loaded.");
      }
      setResult(resultOutcome.status === "fulfilled" ? resultOutcome.value.result : undefined);
      setLastUpdated(new Date());
    };

    const promise = load().finally(() => {
      if (reloadInFlight.current?.promise === promise) {
        reloadInFlight.current = undefined;
      }
    });
    reloadInFlight.current = { id: requestedId, promise };
    return promise;
  }, [id]);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void reload(); }, 1000);
    return () => window.clearInterval(timer);
  }, [active, reload]);
  async function cancelRun() {
    if (!id) return;
    const next = await api.cancelBacktest(id);
    setRun(next);
    message.success("Cancellation requested");
    await reload();
  }
  async function refreshRun() {
    setRefreshing(true);
    try {
      await reload();
    } finally {
      setRefreshing(false);
    }
  }
  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      message.success(`${label} copied`);
    } catch {
      message.error(`${label} could not be copied`);
    }
  }
  if (!run) return <Alert type="info" message="Loading run..." />;
  const parameters = asRecord(run.parameters);
  const performance = asRecord(result?.performance);
  const validationSource = trust?.validation ?? run.validation ?? performance.validation;
  const validationRecord = asRecord(validationSource);
  const validationGates = recordRows(validationRecord.gates).map((gate) => ({
    name: String(gate.name ?? "Unnamed gate"),
    passed: gate.passed === true,
    severity: String(gate.severity ?? (gate.passed === true ? "ok" : "critical")),
    details: isRecord(gate.details) ? gate.details : undefined,
  }));
  const validation = Object.keys(validationRecord).length > 0
    ? { ...validationRecord, gates: validationGates } as unknown as BacktestValidation
    : undefined;
  const experimentRecord = asRecord(trust?.experiment ?? run.experiment ?? performance.experiment);
  const experiment = Object.keys(experimentRecord).length > 0
    ? experimentRecord as BacktestExperiment
    : undefined;
  const fingerprint = trust?.fingerprint ?? run.fingerprint;
  const trustedMetrics = ["success", "succeeded"].includes(run.status) && validation?.passed !== false;
  const summaryMetrics = asRecord(result?.summary_metrics);
  const runStatistics = asRecord(run.statistics);
  const sharpeMetric = summaryMetrics["Recomputed Sharpe"] ?? runStatistics["Sharpe Ratio"];
  const sharpeWarning = metricTruthy(summaryMetrics["Short Window Unstable"]);
  const market = String(parameters.market ?? run.venue ?? "").toLowerCase();
  const currency = market === "china" ? "CNY" : "USD";
  const metricCards = [
    {
      title: "Total Return",
      value: runStatistics["Net Profit"] ?? summaryMetrics["Total Return"],
      kind: "percent" as const,
      featured: true,
    },
    { title: "End Equity", value: runStatistics["End Equity"], kind: "currency" as const },
    { title: "Sharpe Ratio", value: sharpeMetric, kind: "number" as const, warning: sharpeWarning },
    {
      title: "Max Drawdown",
      value: runStatistics["Drawdown"] ?? runStatistics["Max Drawdown"],
      kind: "percent" as const,
    },
    {
      title: "Total Trades",
      value: runStatistics["Total Trades"] ?? runStatistics["Total Orders"] ?? recordRows(result?.orders).length,
      kind: "integer" as const,
    },
    { title: "Information Ratio", value: summaryMetrics["Computed Information Ratio"], kind: "number" as const },
    { title: "VaR 95%", value: summaryMetrics["VaR 95%"], kind: "percent" as const },
    { title: "Tracking Error", value: summaryMetrics["Computed Tracking Error"], kind: "percent" as const },
  ];
  const analysisCards = [
    { title: "Strategy Return", value: performance.strategy_return, kind: "percent" as const },
    { title: "Benchmark Return", value: performance.benchmark_return, kind: "percent" as const },
    { title: "Excess Return", value: performance.excess_return, kind: "percent" as const },
    { title: "Recomputed Sharpe", value: performance.sharpe_recomputed_from_equity, kind: "number" as const },
    { title: "Calmar Ratio", value: performance.calmar, kind: "number" as const },
    { title: "Tracking Error", value: performance.trackingError, kind: "percent" as const },
    { title: "Information Ratio", value: performance.informationRatio, kind: "number" as const },
    { title: "Alpha", value: performance.computed_alpha, kind: "number" as const },
    { title: "Beta", value: performance.computed_beta, kind: "number" as const },
  ];
  const monthlyReturns = recordRows(performance.monthly_returns);
  const yearlyReturns = recordRows(performance.yearly_returns);
  const tradePnl = recordRows(performance.trade_pnl);
  const industryExposure = recordRows(performance.industry_exposure);
  const tradeSummary = asRecord(performance.trade_pnl_summary);
  const tradeSummaryRows = Object.entries(tradeSummary).map(([key, value]) => ({ key, value }));
  const riskRows: Array<Record<string, unknown>> = [
    { key: "VaR 95%", value: performance.var95, kind: "percent" },
    { key: "Expected Shortfall 95%", value: performance.expectedShortfall95, kind: "percent" },
    { key: "Market Correlation", value: performance.marketCorrelation, kind: "number" },
    { key: "Position HHI", value: asRecord(performance.concentration).hhi, kind: "number" },
    { key: "Top Position Weight", value: asRecord(performance.concentration).top1Weight, kind: "percent" },
    { key: "Benchmark Status", value: performance.benchmarkMetricStatus, kind: "text" },
    { key: "Sharpe Status", value: performance.sharpe_recompute_status, kind: "text" },
  ];
  const records = {
    orders: recordRows(result?.orders ?? chart?.orders),
    trades: recordRows(result?.trades),
    holdings: recordRows(result?.holdings)
  };
  function recordColumns(rows: Array<Record<string, unknown>>) {
    const fields = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
    return fields.map((field) => ({
      title: humanizeField(field),
      dataIndex: field,
      key: field,
      width: /time|date/i.test(field) ? 170 : /id|tag|message/i.test(field) ? 190 : 120,
      ellipsis: true,
      render: (value: unknown) => (
        <Tooltip title={typeof value === "object" && value != null ? JSON.stringify(value) : undefined}>
          <span className={typeof value === "number" ? "numeric-cell" : undefined}>{shortValue(value, 48)}</span>
        </Tooltip>
      ),
    }));
  }
  const rawMetricRows = Object.entries(Object.keys(summaryMetrics).length > 0 ? summaryMetrics : runStatistics)
    .filter(([key]) => key.toLowerCase().includes(metricQuery.trim().toLowerCase()))
    .map(([key, value]) => ({ key, value }));
  const passedGates = validation?.gates?.filter((gate) => gate.passed === true).length ?? 0;
  const totalGates = validation?.gates?.length ?? 0;
  const promotionStage = admission?.admission?.current_stage
    ?? (admission?.registrationStatus === "not_registered"
      ? "not enrolled"
      : admission?.registrationStatus === "not_applicable"
        ? "not applicable"
        : "not available");
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts.filter((item): item is string => typeof item === "string") : [];
  const artifactCount = artifacts.length;
  const initialCash = parameters.initialCash ?? parameters.initial_cash ?? parameters.cash;
  function analysisValue(key: unknown, value: unknown) {
    const label = String(key);
    if (/return|drawdown|weight|var|shortfall|tracking error/i.test(label)) return formatPercent(value);
    if (/p&l|pnl|profit|market value|equity/i.test(label)) return formatCurrency(value, currency);
    if (/count|trades|orders|days/i.test(label)) return formatInteger(value);
    return shortValue(value);
  }
  return (
    <div className="run-detail">
      <section className="run-hero">
        <div className="run-hero__main">
          <Button
            className="run-hero__back"
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate("/backtests")}
          >
            Backtests
          </Button>
          <div className="run-hero__eyebrow">
            <span>{shortValue(run.asset_class ?? parameters.assetClass ?? "equity")}</span>
            <span>·</span>
            <span>{String(run.venue ?? parameters.venue ?? parameters.market ?? "unknown").toUpperCase()}</span>
            <span>·</span>
            <span>{shortValue(run.resolution ?? parameters.resolution ?? "daily")}</span>
          </div>
          <h1>{run.name ?? run.id}</h1>
          <div className="run-hero__subtitle">
            <strong>{run.symbol}</strong>
            <span>{shortValue(parameters.start)} — {shortValue(parameters.end)}</span>
            <span>{run.project_id ?? "Standalone strategy"}</span>
          </div>
          <div className="run-hero__badges">
            <span data-testid="run-status"><StatusTag status={run.status} /></span>
            <ValidationStatusTag validation={validation} />
            <Tag>{totalGates ? `${passedGates}/${totalGates} gates` : "no gates"}</Tag>
            <Tag>{artifactCount} files</Tag>
          </div>
        </div>
        <div className="run-hero__actions">
          <Space wrap>
            <Button
              ghost
              icon={<CopyOutlined />}
              onClick={() => copyText(run.id, "Run ID")}
            >
              Copy ID
            </Button>
            {active && <Button danger onClick={cancelRun}>Cancel</Button>}
            <Button ghost loading={refreshing} onClick={refreshRun} icon={<ReloadOutlined />}>Refresh</Button>
          </Space>
          <span className="run-hero__updated">
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Loading latest result"}
          </span>
        </div>
      </section>
      {(run.error_message || run.error) && (
        <Alert
          type="error"
          showIcon
          message={run.failure?.stage ? `${run.failure.stage.toUpperCase()} failed: ${run.failure.code}` : "Backtest failed"}
          description={run.failure?.message || run.error_message || run.error}
          style={{ marginBottom: 16 }}
        />
      )}
      {!trustedMetrics && !active && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="This run is not eligible for strategy evaluation."
          description="Return, Sharpe, drawdown, and other performance values are hidden because execution or validation did not pass. Raw artifacts remain available for diagnosis."
        />
      )}
      {trustedMetrics && sharpeWarning && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="Sharpe is marked unstable because the effective daily return sample is short."
        />
      )}
      {trustedMetrics && (
        <div className="backtest-kpi-grid">
          {metricCards.map((item) => (
            <BacktestMetricCard key={item.title} {...item} currency={currency} />
          ))}
        </div>
      )}
      <Tabs
        className="run-detail-tabs"
        destroyOnHidden
        items={[
          {
            key: "performance",
            label: "Performance",
            children: (
              <RunDetailPanelBoundary panel="Performance" resetKey={`${run.id}:performance`}>
              <div className="run-analysis" data-testid="run-status-panel">
                {chart
                  ? <div className="run-charts"><BacktestCharts chartData={chart} /></div>
                  : <Alert
                      type={chartError ? "error" : "info"}
                      showIcon={Boolean(chartError)}
                      message={chartError ? "Performance charts failed to load." : "Performance charts are generated after the result artifact is ready."}
                      description={chartError}
                    />}
                {trustedMetrics ? (
                  <>
                    <div className="backtest-kpi-grid backtest-kpi-grid--analysis">
                      {analysisCards.map((item) => (
                        <BacktestMetricCard key={item.title} {...item} />
                      ))}
                    </div>
                    <Card title="Risk & Attribution" className="run-section-card">
                      <Table<Record<string, unknown>>
                        size="small"
                        pagination={false}
                        rowKey="key"
                        dataSource={riskRows}
                        columns={[
                          { title: "Metric", dataIndex: "key" },
                          {
                            title: "Value",
                            dataIndex: "value",
                            align: "right",
                            render: (value, row) => <span className="numeric-cell">{formatBacktestMetric(value, String(row.kind) as BacktestMetricKind)}</span>
                          }
                        ]}
                      />
                    </Card>
                    <div className="run-overview-grid run-period-returns">
                      <Card title="Monthly Returns">
                        <Table<Record<string, unknown>> size="small" rowKey={(row) => String(row.period)} dataSource={monthlyReturns} columns={[
                          { title: "Period", dataIndex: "period" },
                          { title: "Return", dataIndex: "return", align: "right", render: (value) => <span className="numeric-cell">{formatPercent(value)}</span> },
                        ]} pagination={{ pageSize: 12, showSizeChanger: false }} />
                      </Card>
                      <Card title="Yearly Returns">
                        <Table<Record<string, unknown>> size="small" pagination={false} rowKey={(row) => String(row.period)} dataSource={yearlyReturns} columns={[
                          { title: "Year", dataIndex: "period" },
                          { title: "Return", dataIndex: "return", align: "right", render: (value) => <span className="numeric-cell">{formatPercent(value)}</span> },
                        ]} />
                      </Card>
                    </div>
                    {industryExposure.length > 0 && (
                      <Card title="Industry Exposure" className="run-section-card">
                        <Table<Record<string, unknown>> size="small" pagination={false} rowKey={(row) => String(row.industry)} dataSource={industryExposure} columns={[
                          { title: "Industry", dataIndex: "industry" },
                          { title: "Market Value", dataIndex: "market_value", align: "right", render: (value) => <span className="numeric-cell">{formatCurrency(value, currency)}</span> },
                          { title: "Weight", dataIndex: "weight", align: "right", render: (value) => <span className="numeric-cell">{formatPercent(value)}</span> },
                        ]} />
                      </Card>
                    )}
                  </>
                ) : <Alert type="warning" showIcon message="Trusted performance analysis is unavailable for this run." style={{ marginTop: 12 }} />}
              </div>
              </RunDetailPanelBoundary>
            )
          },
          {
            key: "trades",
            label: `Trades (${records.trades.length})`,
            children: (
              <RunDetailPanelBoundary panel="Trades" resetKey={`${run.id}:trades`}>
              <div data-testid="records-panel">
                <div className="run-overview-grid">
                  <Card title="Trade Summary">
                    <Table<Record<string, unknown>>
                      size="small"
                      pagination={false}
                      rowKey="key"
                      dataSource={tradeSummaryRows}
                      columns={[
                        { title: "Metric", dataIndex: "key", render: (value) => humanizeField(String(value)) },
                        { title: "Value", dataIndex: "value", align: "right", render: (value, row) => <span className="numeric-cell">{analysisValue(row.key, value)}</span> }
                      ]}
                    />
                  </Card>
                  <Card title="Trade P&L">
                  <Table<Record<string, unknown>> size="small" rowKey={(row) => stableRecordKey(row, "trade-pnl")} dataSource={tradePnl} columns={[
                    { title: "Symbol", dataIndex: "symbol" },
                    { title: "Entry", dataIndex: "entry_time" },
                    { title: "Exit", dataIndex: "exit_time" },
                    { title: "Holding Days", dataIndex: "holding_days", align: "right", render: formatInteger },
                    { title: "Net P&L", dataIndex: "net_pnl", align: "right", render: (value) => <span className="numeric-cell">{formatCurrency(value, currency)}</span> },
                    { title: "Return", dataIndex: "return", align: "right", render: (value) => <span className="numeric-cell">{formatPercent(value)}</span> },
                  ]} scroll={{ x: 760 }} pagination={{ pageSize: 10, showSizeChanger: true }} />
                  </Card>
                </div>
                <Card className="run-records-card">
                  <Tabs
                    type="card"
                    items={[
                      { key: "orders", label: `Orders ${records.orders.length}`, rows: records.orders, testId: "result-orders-table" },
                      { key: "trades", label: `Trades ${records.trades.length}`, rows: records.trades, testId: "result-trades-table" },
                      { key: "holdings", label: `Holdings ${records.holdings.length}`, rows: records.holdings, testId: "result-holdings-table" },
                    ].map((item) => ({
                      key: item.key,
                      label: item.label,
                      children: item.rows.length ? (
                        <Table
                          data-testid={item.testId}
                          className="record-ledger-table"
                          size="small"
                          rowKey={(row) => stableRecordKey(row, item.key)}
                          dataSource={item.rows}
                          columns={recordColumns(item.rows)}
                          scroll={{ x: "max-content" }}
                          pagination={{ pageSize: 10, showSizeChanger: true, pageSizeOptions: [10, 25, 50], showTotal: (total) => `${total} records` }}
                        />
                      ) : <Alert type="info" message={`No ${item.key} were parsed for this run.`} />
                    }))}
                  />
                </Card>
              </div>
              </RunDetailPanelBoundary>
            )
          },
          {
            key: "quality",
            label: "Research Quality",
            children: (
              <RunDetailPanelBoundary panel="Research Quality" resetKey={`${run.id}:quality`}>
              <>
                <div className="run-overview-strip run-overview-strip--quality">
                  <div><span>Execution</span><StatusTag status={run.status} /></div>
                  <div><span>Validation</span><ValidationStatusTag validation={validation} /></div>
                  <div><span>Promotion</span><strong>{humanizeField(String(promotionStage))}</strong></div>
                  <div><span>Validation gates</span><strong>{totalGates ? `${passedGates}/${totalGates}` : "not available"}</strong></div>
                </div>
                <Tabs
                  className="run-subtabs"
                  type="card"
                  items={[
                    {
                      key: "validation",
                      label: totalGates ? `Validation (${passedGates}/${totalGates})` : "Validation",
                      children: <div className="run-trust-panel"><BacktestTrustPanel validation={validation} experiment={experiment} fingerprint={fingerprint} /></div>
                    },
                    {
                      key: "promotion",
                      label: "Strategy Promotion",
                      children: <StrategyAdmissionPanel value={admission} />
                    }
                  ]}
                />
              </>
              </RunDetailPanelBoundary>
            )
          },
          {
            key: "details",
            label: "Run Details",
            children: (
              <RunDetailPanelBoundary panel="Run Details" resetKey={`${run.id}:details`}>
              <Tabs
                className="run-subtabs"
                type="card"
                items={[
                  {
                    key: "overview",
                    label: "Overview",
                    children: (
                      <>
                        <div className="run-overview-grid">
                          <Card title="Run Profile">
                            <Descriptions size="small" bordered column={2}>
                              <Descriptions.Item label="Run ID" span={2}><span className="copyable-value">{run.id}</span></Descriptions.Item>
                              <Descriptions.Item label="Symbol">{run.symbol}</Descriptions.Item>
                              <Descriptions.Item label="Market">{String(parameters.market ?? run.venue ?? "-").toUpperCase()}</Descriptions.Item>
                              <Descriptions.Item label="Asset">{shortValue(run.asset_class ?? parameters.assetClass ?? "equity")}</Descriptions.Item>
                              <Descriptions.Item label="Resolution">{shortValue(run.resolution ?? parameters.resolution ?? "-")}</Descriptions.Item>
                              <Descriptions.Item label="Start">{shortValue(parameters.start)}</Descriptions.Item>
                              <Descriptions.Item label="End">{shortValue(parameters.end)}</Descriptions.Item>
                              <Descriptions.Item label="Initial capital">{formatCurrency(initialCash, currency)}</Descriptions.Item>
                              <Descriptions.Item label="Project">{run.project_id ?? "Standalone"}</Descriptions.Item>
                            </Descriptions>
                          </Card>
                          <Card title="Execution Lifecycle">
                            <Descriptions size="small" bordered column={1}>
                              <Descriptions.Item label="Created">{formatDateTime(run.created_at)}</Descriptions.Item>
                              <Descriptions.Item label="Queued">{formatDateTime(run.queued_at)}</Descriptions.Item>
                              <Descriptions.Item label="Started">{formatDateTime(run.started_at)}</Descriptions.Item>
                              <Descriptions.Item label="Finished">{formatDateTime(run.finished_at)}</Descriptions.Item>
                              <Descriptions.Item label="Duration">{formatDuration(run.duration_seconds)}</Descriptions.Item>
                              <Descriptions.Item label="Exit code">{run.exit_code ?? "—"}</Descriptions.Item>
                            </Descriptions>
                          </Card>
                        </div>
                        <Card title="Runtime" className="run-section-card">
                          <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
                            <Descriptions.Item label="Docker image">{run.docker_image || "—"}</Descriptions.Item>
                            <Descriptions.Item label="Container">{run.container_name || "—"}</Descriptions.Item>
                            <Descriptions.Item label="Result directory">{run.results_dir || "—"}</Descriptions.Item>
                          </Descriptions>
                        </Card>
                      </>
                    )
                  },
                  {
                    key: "config",
                    label: "Configuration",
                    children: (
                      <Card title="Strategy Parameters" className="run-section-card">
                        <Descriptions size="small" bordered column={{ xs: 1, sm: 2, lg: 3 }}>
                          {Object.entries(parameters).map(([key, value]) => (
                            <Descriptions.Item key={key} label={humanizeField(key)}>
                              <span className={typeof value === "number" ? "numeric-cell" : undefined}>{shortValue(value, 96)}</span>
                            </Descriptions.Item>
                          ))}
                        </Descriptions>
                      </Card>
                    )
                  },
                  {
                    key: "metrics",
                    label: `Raw Metrics (${rawMetricRows.length})`,
                    children: (
                      <Card
                        title="Metric Ledger"
                        data-testid="metrics-table"
                        className="run-section-card"
                        extra={<Space wrap>
                          <Input allowClear value={metricQuery} onChange={(event) => setMetricQuery(event.target.value)} placeholder="Filter metrics" style={{ width: 220 }} />
                          <Button icon={<CopyOutlined />} onClick={() => copyText(JSON.stringify(Object.keys(summaryMetrics).length > 0 ? summaryMetrics : runStatistics, null, 2), "Metrics JSON")}>Copy JSON</Button>
                        </Space>}
                      >
                        <Table size="small" pagination={false} rowKey="key" dataSource={rawMetricRows} columns={[
                          { title: "Metric", dataIndex: "key", width: "52%" },
                          { title: "Value", dataIndex: "value", align: "right", render: (value) => <span className="numeric-cell">{shortValue(value)}</span> }
                        ]} />
                      </Card>
                    )
                  },
                  {
                    key: "files",
                    label: `Files (${artifactCount})`,
                    children: (
                      <Card title="Result Artifacts" className="run-section-card">
                        {artifactCount ? (
                          <div className="artifact-grid">
                            {artifacts.map((name) => {
                              const extension = name.includes(".") ? name.split(".").pop()?.toUpperCase() : "FILE";
                              const artifactPath = name.split("/").map((part) => encodeURIComponent(part)).join("/");
                              const href = `/api/backtests/${run.id}/artifacts/${artifactPath}`;
                              return (
                                <div className="artifact-item" key={name}>
                                  <div className="artifact-icon"><FileTextOutlined /></div>
                                  <div className="artifact-info"><strong title={name}>{name}</strong><span>{extension} artifact</span></div>
                                  <Button type="text" icon={<DownloadOutlined />} href={href} target="_blank" aria-label={`Open ${name}`} />
                                </div>
                              );
                            })}
                          </div>
                        ) : <Alert type="info" message="No result artifacts are available for this run." />}
                      </Card>
                    )
                  },
                  {
                    key: "logs",
                    label: "Logs",
                    children: (
                      <Card title="Execution Log" className="run-section-card" extra={<Button icon={<CopyOutlined />} onClick={() => copyText(logs, "Logs")} disabled={!logs}>Copy logs</Button>}>
                        <pre data-testid="backtest-logs" className="log-view">{logs || "No logs yet."}</pre>
                      </Card>
                    )
                  }
                ]}
              />
              </RunDetailPanelBoundary>
            )
          }
        ]}
      />
    </div>
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
      <ExampleGallery kind="optimization" onCreated={() => projects.reload()} />
      <BatchWorkbench kind="optimization" projects={projects.data} />
      <Tabs
        items={[
          {
            key: "grid",
            label: "Parameter Grid",
            children: (
              <>
                <Card title="Parameter Grid">
                  <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "china", venue: "china", resolution: "daily", dataType: "trade", symbol: "000001", start: "2024-01-01", end: "2026-07-13", cash: 300000, maxCandidates: 50, dockerImage: defaultSettings.dockerImage }}>
                    <FormSection title="Strategy and market">
                    <FormGrid>
                      <Form.Item className="form-field--wide" name="projectId" label="Project" rules={[{ required: true }]}><Select onChange={(value) => { const project = projects.data.find((item) => item.id === value); if (project) { const template = projectTemplate(project, templates.data); form.setFieldsValue({ assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), parameterGrid: Object.fromEntries((template?.parameters ?? []).map((parameter) => [parameter.key, String(parameter.default ?? "")])) }); } }} options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
                      <Form.Item name="assetClass" label="Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
                      <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
                      <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
                      <Form.Item className="form-field--wide" name="symbol" label="Symbol"><SecuritySearch assetClass={assetClass} market={market} /></Form.Item>
                    </FormGrid>
                    </FormSection>
                    <FormSection title="Period and search">
                    <FormGrid>
                      <Form.Item name="start" label="Start"><DateStringPicker /></Form.Item>
                      <Form.Item name="end" label="End"><DateStringPicker /></Form.Item>
                      <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="maxCandidates" label="Max Candidates"><InputNumber min={1} max={200} style={{ width: "100%" }} /></Form.Item>
                    </FormGrid>
                    </FormSection>
                    <FormSection title="Parameter grid">
                    <FormGrid>
                      {(selectedTemplate?.parameters ?? []).map((parameter) => (
                        <Form.Item key={parameter.key} name={["parameterGrid", parameter.key]} label={`${parameter.label} Grid`}>
                          <Input placeholder={String(parameter.default ?? "")} />
                        </Form.Item>
                      ))}
                    </FormGrid>
                    </FormSection>
                    <AdvancedFields label="Advanced optimization settings">
                      <FormGrid>
                        <Form.Item className="form-field--wide" name="dockerImage" label="Docker Image"><Input /></Form.Item>
                        <Form.Item className="form-field--full" name="parameterGridJson" label="Custom Parameter Grid JSON">
                          <Input.TextArea rows={3} placeholder='{"period":[10,20,30],"threshold":[0.1,0.2]}' />
                        </Form.Item>
                        <Form.Item className="form-field--full" name="parametersJson" label="Fixed Parameters JSON">
                          <Input.TextArea rows={3} placeholder='{"benchmarkSymbol":"SPY"}' />
                        </Form.Item>
                      </FormGrid>
                    </AdvancedFields>
                    <FormActions><Button type="primary" icon={<SlidersOutlined />} htmlType="submit">Queue Optimization</Button></FormActions>
                  </Form>
                </Card>
                <Card title="Optimization Runs" style={{ marginTop: 16 }}>
                  <Table<OptimizationRun> rowKey="id" dataSource={optimizations.data} size="small" columns={[
                    { title: "Optimization", render: (_, run) => <div className="table-primary-cell"><strong>{String(run.parameters?.ticker ?? run.parameters?.symbol ?? "Optimization")}</strong><span className="muted copyable-id">{run.id}</span></div> },
                    { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
                    { title: "Candidates", render: (_, run) => run.result?.candidateCount ?? run.result?.candidates?.length ?? "-" },
                    { title: "Best", render: (_, run) => shortValue(bestCandidate(run)?.overrides ?? "-") },
                    { title: "Created", dataIndex: "created_at" },
                    { title: "Actions", render: (_, run) => <Popconfirm title="Delete this optimization?" description="Candidate results and managed runtime files will be removed." okText="Delete" okButtonProps={{ danger: true }} disabled={["created", "queued", "running"].includes(run.status)} onConfirm={async () => { try { await api.deleteOptimization(run.id); message.success("Optimization deleted"); await optimizations.reload(); } catch (error) { message.error((error as Error).message); } }}><Button size="small" danger disabled={["created", "queued", "running"].includes(run.status)}>Delete</Button></Popconfirm> }
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
                    <Form.Item className="form-field--full" name="runIds" label="Run IDs" rules={[{ required: true }]}>
                      <Input.TextArea rows={4} placeholder="run-id-1, run-id-2" />
                    </Form.Item>
                    <FormGrid>
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
                    </FormGrid>
                    <FormActions><Button type="primary" htmlType="submit" loading={portfolioSubmitting}>Optimize Weights</Button></FormActions>
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
