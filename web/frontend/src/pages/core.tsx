import {
  Alert,
  AutoComplete,
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
  CodeOutlined,
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
import Editor from "@monaco-editor/react";
import { useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";

import { api } from "../api";
import type {
  AppSettings,
  AssetClassInfo,
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
  Project,
  ProjectFile,
  ReportRecord,
  ResearchSession,
  StrategyTemplate,
  Task,
} from "../api";
import { BacktestCharts, RunsTable, StatusTag } from "../components";
import { BacktestTrustPanel, ValidationStatusTag } from "../components/backtests/BacktestTrustPanel";
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

const CRYPTO_DEMO_SYMBOLS = ["BTCUSDT", "ETHUSDT"] as const;

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
  forcedDataType
}: {
  compact?: boolean;
  forcedAssetClass?: string;
  forcedMarket?: string;
  forcedVenue?: string;
  forcedResolution?: string;
  forcedDataType?: string;
}) {
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const markets = useAsyncData<MarketInfo[]>(api.markets, []);
  const providers = useAsyncData<DataProvider[]>(api.dataProviders, []);
  const [symbolsText, setSymbolsText] = useState("");
  const [form] = Form.useForm();
  const selectedAssetClass = forcedAssetClass ?? (Form.useWatch("assetClass", form) || "equity");
  const selectedMarket = forcedMarket ?? (Form.useWatch("market", form) || "usa");
  const selectedVenue = forcedVenue ?? (Form.useWatch("venue", form) || defaultVenueFor(selectedAssetClass, assetClasses.data, selectedMarket));
  const selectedResolution = forcedResolution ?? (Form.useWatch("resolution", form) || "daily");
  const selectedDataType = forcedDataType ?? (Form.useWatch("dataType", form) || "trade");
  const selectedProvider = Form.useWatch("provider", form) || markets.data.find((item) => item.key === selectedMarket)?.defaultProvider || "yahoo";
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === selectedAssetClass);

  useEffect(() => {
    form.setFieldValue("assetClass", forcedAssetClass ?? form.getFieldValue("assetClass") ?? "equity");
    form.setFieldValue("market", forcedMarket ?? form.getFieldValue("market") ?? "usa");
    form.setFieldValue("venue", forcedVenue ?? form.getFieldValue("venue") ?? defaultVenueFor(selectedAssetClass, assetClasses.data, selectedMarket));
    form.setFieldValue("resolution", forcedResolution ?? form.getFieldValue("resolution") ?? "daily");
    form.setFieldValue("dataType", forcedDataType ?? form.getFieldValue("dataType") ?? "trade");
  }, [assetClasses.data, forcedAssetClass, forcedDataType, forcedMarket, forcedResolution, forcedVenue, form, selectedAssetClass, selectedMarket]);

  useEffect(() => {
    const market = markets.data.find((item) => item.key === selectedMarket);
    const compatible = providers.data.filter((provider) => (
      provider.assetClasses?.includes(selectedAssetClass) ||
      (selectedAssetClass === "equity" && provider.markets.includes(selectedMarket))
    ));
    if (compatible.length > 0 && !compatible.some((provider) => provider.key === selectedProvider)) {
      form.setFieldValue("provider", compatible[0].key);
    } else if (market && selectedAssetClass === "equity" && !market.providers.includes(selectedProvider)) {
      form.setFieldValue("provider", market.defaultProvider);
    }
  }, [selectedAssetClass, selectedDataType, selectedMarket, selectedProvider, selectedResolution, selectedVenue, markets.data, providers.data, form]);

  async function submit(values: any) {
    const symbols = Array.from(new Set(symbolsText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)));
    if (symbols.length === 0) {
      message.error("Select or enter at least one symbol");
      return;
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
      outputsize: values.outputsize,
      startDate: values.startDate,
      endDate: values.endDate,
      adjust: values.adjust,
      overwrite: Boolean(values.overwrite)
    });
    message.success(`Data fetch queued: ${task.id}`);
    setSymbolsText("");
  }

  const marketProviders = providers.data.filter((provider) => (
    provider.assetClasses?.includes(selectedAssetClass) ||
    (selectedAssetClass === "equity" && provider.markets.includes(selectedMarket))
  ));
  const venueOptions = selectedAssetInfo?.venues.map((venue) => ({ value: venue, label: venue })) ?? [];
  const resolutionOptions = ["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }));
  const dataTypeOptions = (selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }));

  return (
    <Card title={compact ? "Market Data" : "Market Data Download"}>
      <Form
        form={form}
        layout="vertical"
        onFinish={submit}
        initialValues={{
          assetClass: forcedAssetClass ?? "equity",
          market: forcedMarket ?? "usa",
          venue: forcedVenue ?? "usa",
          resolution: forcedResolution ?? "daily",
          dataType: forcedDataType ?? "trade",
          provider: "yahoo",
          outputsize: "compact",
          adjust: "",
          overwrite: false
        }}
      >
        <div className="field-grid six">
          <Form.Item name="assetClass" label="Asset Class">
            <Select
              disabled={Boolean(forcedAssetClass)}
              options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))}
              onChange={(value) => {
                const nextVenue = defaultVenueFor(value, assetClasses.data, selectedMarket);
                form.setFieldValue("venue", nextVenue);
                form.setFieldValue("provider", value === "crypto" ? "binance" : markets.data.find((item) => item.key === selectedMarket)?.defaultProvider ?? "yahoo");
              }}
            />
          </Form.Item>
          <Form.Item name="market" label="Market">
            <Select disabled={Boolean(forcedMarket)} options={markets.data.map((item) => ({ value: item.key, label: item.name }))} />
          </Form.Item>
          <Form.Item name="venue" label="Venue">
            <Select disabled={Boolean(forcedVenue) || selectedAssetClass === "equity"} options={venueOptions} />
          </Form.Item>
          <Form.Item name="resolution" label="Resolution">
            <Select disabled={Boolean(forcedResolution)} options={resolutionOptions} />
          </Form.Item>
          <Form.Item name="dataType" label="Data Type">
            <Select disabled={Boolean(forcedDataType)} options={dataTypeOptions} />
          </Form.Item>
          <Form.Item name="provider" label="Provider">
            <Select options={marketProviders.map((provider) => ({ value: provider.key, label: provider.name }))} />
          </Form.Item>
          <Form.Item name="adjust" label="Adjust">
            <Select options={[{ value: "", label: "Raw" }, { value: "qfq", label: "QFQ" }, { value: "hfq", label: "HFQ" }]} />
          </Form.Item>
          <Form.Item name="startDate" label="Start"><Input type="date" /></Form.Item>
          <Form.Item name="endDate" label="End"><Input type="date" /></Form.Item>
          <Form.Item name="outputsize" label="Output Size">
            <Select disabled={selectedProvider !== "alpha_vantage"} options={[{ value: "compact" }, { value: "full" }]} />
          </Form.Item>
          {(selectedProvider === "alpha_vantage") && (
            <Form.Item name="apiKey" label="API Key"><Input.Password placeholder="or environment variable" /></Form.Item>
          )}
          <Form.Item name="overwrite" valuePropName="checked" label=" "><Checkbox>Overwrite local files</Checkbox></Form.Item>
        </div>
        <Space.Compact style={{ width: "100%", marginBottom: 12 }}>
          <Input
            value={symbolsText}
            onChange={(event) => setSymbolsText(event.target.value)}
            placeholder={selectedAssetClass === "crypto" ? "BTCUSDT, ETHUSDT" : selectedAssetClass === "future" ? "GC, ES" : selectedMarket === "china" ? "600519, 000001" : selectedMarket === "hongkong" ? "00700, 00941" : "AAPL, MSFT"}
          />
          <Button type="primary" icon={<CloudDownloadOutlined />} htmlType="submit">Fetch</Button>
        </Space.Compact>
      </Form>
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
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const markets = useAsyncData<MarketInfo[]>(api.markets, []);
  const [form] = Form.useForm();
  const selectedAssetClass = Form.useWatch("assetClass", form) || "equity";
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === selectedAssetClass);

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
    form.resetFields();
    await projects.reload();
    navigate(`/workspace/${project.id}`);
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

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Projects</h1>
        <Button icon={<ReloadOutlined />} onClick={projects.reload}>Refresh</Button>
      </div>
      <Card title="Create Project">
        <Form form={form} layout="vertical" onFinish={createProject} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", templateKey: "ema_cross" }}>
          <div className="field-grid">
            <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="A Share RSI Strategy" /></Form.Item>
            <Form.Item name="assetClass" label="Asset Class">
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
                  <Button size="small" type="primary" onClick={() => navigate(`/workspace/${project.id}`)}>Workspace</Button>
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

export function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const [selectedId, setSelectedId] = useState<string | undefined>(projectId);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [activeFile, setActiveFile] = useState<string>();
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);

  const project = projects.data.find((item) => item.id === selectedId);
  const template = projectTemplate(project, templates.data);
  const assetClass = projectAssetClass(project);
  const market = projectMarket(project);
  const venue = projectVenue(project);
  const resolution = projectResolution(project);
  const dataType = projectDataType(project);

  useEffect(() => {
    if (projectId) setSelectedId(projectId);
    else if (!selectedId && projects.data.length > 0) setSelectedId(projects.data[0].id);
  }, [projectId, projects.data, selectedId]);

  const loadProjectFile = useCallback(async (target: Project, path?: string) => {
    const tree = await api.projectFiles(target.id);
    setFiles(tree);
    const fileItems = tree.filter((item) => item.type === "file");
    const requestedFile = path ?? target.main_file;
    const nextFile = fileItems.some((item) => item.path === requestedFile) ? requestedFile : fileItems[0]?.path;
    setActiveFile(nextFile);
    if (!nextFile) {
      setContent("");
      setDirty(false);
      return;
    }
    setContent((await api.readProjectFile(target.id, nextFile)).content);
    setDirty(false);
  }, []);

  useEffect(() => {
    if (project) loadProjectFile(project).catch((error) => message.error((error as Error).message));
  }, [project?.id, loadProjectFile]);

  useEffect(() => {
    api.symbols(market, assetClass, venue, resolution, dataType).then((result) => setSymbols(result.symbols)).catch((error) => message.error((error as Error).message));
  }, [assetClass, dataType, market, resolution, venue]);

  async function saveFile() {
    if (!project || !activeFile) return;
    await api.writeProjectFile(project.id, activeFile, content);
    setDirty(false);
    message.success("Saved");
  }

  async function submitBacktest(values: any) {
    if (!project) return;
    const run = await api.createBacktest({
      ...values,
      projectId: project.id,
      assetClass,
      market,
      venue,
      resolution,
      dataType,
      parameters: values.parameters ?? {}
    });
    message.success("Backtest queued");
    navigate(`/runs/${run.id}`);
  }

  const projectRuns = runs.data.filter((run) => run.project_id === project?.id);
  const projectTasks = tasks.data.filter((task) => task.project_id === project?.id);
  const backtestInitial = {
    symbol: symbols[0] ?? (assetClass === "crypto" ? "BTCUSDT" : market === "china" ? "600519" : market === "hongkong" ? "00700" : "AAPL"),
    start: "2018-01-01",
    end: "2024-12-31",
    cash: 100000,
    dockerImage: "quantconnect/lean:latest",
    assetClass,
    market,
    venue,
    resolution,
    dataType,
    parameters: templateDefaults(template)
  };

  async function runCryptoDemoBacktest(symbol: string) {
    if (!project || assetClass !== "crypto") {
      message.info("Select a crypto project first to run BTC/ETH demo.");
      return;
    }
    if (!symbols.includes(symbol)) {
      message.warning("Please fetch symbol data in the Data tab first (Binance BTCUSDT/ETHUSDT).");
      return;
    }
    await api.createBacktest({
      ...backtestInitial,
      symbol,
      projectId: project.id,
      assetClass,
      market,
      venue,
      resolution,
      dataType,
      parameters: backtestInitial.parameters,
    });
    message.success(`Backtest queued: ${symbol}`);
    runs.reload();
  }

  async function runCryptoDemoSuite() {
    await Promise.all(CRYPTO_DEMO_SYMBOLS.map(runCryptoDemoBacktest));
    runs.reload();
  }

  return (
    <>
      <div className="toolbar">
        <div>
          <h1 className="page-title">Project Workspace</h1>
          {project && <span className="muted">{project.name} / {assetClass} / {venue} / {resolution} / {template?.name}</span>}
        </div>
        <Space wrap>
          <Select style={{ width: 280 }} value={selectedId} onChange={(value) => setSelectedId(value)} options={projects.data.map((item) => ({ value: item.id, label: item.name }))} />
          <Button icon={<ReloadOutlined />} onClick={() => { projects.reload(); runs.reload(); tasks.reload(); }}>Refresh</Button>
        </Space>
      </div>
      {!project ? <Alert type="info" message="Create or select a project first." /> : (
        <Tabs items={[
          { key: "overview", label: "Overview", children: <div className="grid"><Card><Statistic title="Backtests" value={projectRuns.length} /></Card><Card><Statistic title="Tasks" value={projectTasks.length} /></Card><Card><Statistic title="Asset" value={assetClass} /></Card><Card><Statistic title="Local Symbols" value={symbols.length} /></Card></div> },
          { key: "code", label: "Code", children: <Card title={`${activeFile ?? "No file selected"}${dirty ? " *" : ""}`}><Space wrap style={{ marginBottom: 8 }}>{files.filter((item) => item.type === "file").map((file) => <Tag key={file.path} color={file.path === activeFile ? "blue" : "default"} onClick={() => loadProjectFile(project, file.path)}>{file.path}</Tag>)}</Space>{!activeFile && <Alert type="warning" showIcon message="No project files found." style={{ marginBottom: 12 }} />}<Editor height="540px" language={activeFile?.endsWith(".cs") ? "csharp" : "python"} value={content} onChange={(value) => { setContent(value ?? ""); setDirty(true); }} theme="vs-dark" /><Button type="primary" style={{ marginTop: 12 }} icon={<CodeOutlined />} disabled={!dirty || !activeFile} onClick={saveFile}>Save</Button></Card> },
          { key: "data", label: "Data", children: <MarketDataDownloader compact forcedAssetClass={assetClass} forcedMarket={market} forcedVenue={venue} forcedResolution={resolution} forcedDataType={dataType} /> },
          { key: "backtest", label: "Backtest", children: <Card title="Run Backtest"><Form key={`${project.id}-${symbols.length}`} layout="vertical" onFinish={submitBacktest} initialValues={backtestInitial}><div className="field-grid six"><Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.map((symbol) => ({ value: symbol, label: symbol }))} /></Form.Item><Form.Item name="start" label="Start" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item name="end" label="End" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item><Form.Item name="dockerImage" label="Image"><Input /></Form.Item>{strategyFields(template)}</div><Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit">Run</Button>{assetClass === "crypto" && <Space wrap style={{ marginTop: 12 }}><Button onClick={() => runCryptoDemoBacktest("BTCUSDT")}>Run BTCUSDT Demo</Button><Button onClick={() => runCryptoDemoBacktest("ETHUSDT")}>Run ETHUSDT Demo</Button><Button type="primary" onClick={runCryptoDemoSuite}>Run BTCUSDT + ETHUSDT</Button></Space>}</Form></Card> },
          { key: "results", label: "Results", children: <Card title="Project Backtests"><RunsTable runs={projectRuns} onOpen={(id) => navigate(`/runs/${id}`)} /></Card> },
          { key: "logs", label: "Logs", children: <Card title="Project Tasks"><Table<Task> rowKey="id" dataSource={projectTasks} size="small" columns={[{ title: "Kind", dataIndex: "kind" }, { title: "Title", dataIndex: "title" }, { title: "Status", dataIndex: "status", render: (status) => <StatusTag status={status} /> }, { title: "Created", dataIndex: "created_at" }]} /></Card> }
        ]} />
      )}
    </>
  );
}

export function DataPage() {
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const [csvForm] = Form.useForm();
  const [queryForm] = Form.useForm();
  const [queryResult, setQueryResult] = useState<DataQueryResult>();
  const querySymbol = Form.useWatch("symbol", queryForm) || defaultBarPreviewValues.symbol;
  const chartOption = useMemo(() => candlestickOption(queryResult?.items ?? [], querySymbol), [queryResult?.items, querySymbol]);

  useEffect(() => {
    api.queryData(defaultBarPreviewValues)
      .then(setQueryResult)
      .catch((error) => message.error((error as Error).message));
  }, []);

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

  async function queryMarketData(values: any) {
    const result = await api.queryData({
      ...values,
      limit: values.limit ?? 200
    });
    setQueryResult(result);
    if (!result.enabled) {
      message.warning(values.source === "clickhouse" ? "ClickHouse is not enabled or not reachable." : "Database query is unavailable.");
    }
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Data Library</h1><Button icon={<ReloadOutlined />} onClick={() => queryMarketData(queryForm.getFieldsValue())}>Refresh Preview</Button></div>
      <Card title="Bar Data Preview" style={{ marginTop: 0 }}>
        <Form
          form={queryForm}
          layout="inline"
          onFinish={queryMarketData}
          initialValues={defaultBarPreviewValues}
        >
          <Form.Item name="source">
            <Select
              style={{ width: 170 }}
              options={[
                { value: "database", label: "MySQL Database" },
                { value: "clickhouse", label: "ClickHouse" }
              ]}
            />
          </Form.Item>
          <Form.Item name="assetClass" rules={[{ required: true }]}><Select style={{ width: 140 }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
          <Form.Item name="symbol" rules={[{ required: true }]}><Input style={{ width: 140 }} placeholder="AAPL" /></Form.Item>
          <Form.Item name="market"><Select style={{ width: 140 }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          <Form.Item name="venue"><Input style={{ width: 120 }} placeholder="venue" /></Form.Item>
          <Form.Item name="resolution"><Select style={{ width: 120 }} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="dataType"><Select style={{ width: 120 }} options={["trade", "quote", "open_interest"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="limit"><InputNumber min={1} max={5000} style={{ width: 110 }} /></Form.Item>
          <Button type="primary" htmlType="submit">Query</Button>
        </Form>
        {queryResult && !queryResult.enabled && <Alert style={{ marginTop: 12 }} type="warning" showIcon message={queryResult.error ?? "Selected data source is unavailable."} />}
        {queryResult?.enabled && queryResult.message && <Alert style={{ marginTop: 12 }} type="info" showIcon message={queryResult.message} />}
        {queryResult?.enabled && queryResult.items.length === 0 && <Alert style={{ marginTop: 12 }} type="info" showIcon message="No bars matched the selected filters." />}
        {queryResult?.enabled && queryResult.items.length > 0 && (
          <>
            <Space wrap style={{ marginTop: 12 }}>
              <Tag color="blue">{queryResult.source ?? "data"}</Tag>
              <Tag>{queryResult.count} bars</Tag>
              <Tag>{`${queryResult.items[0].timestamp.slice(0, 10)} -> ${queryResult.items[queryResult.items.length - 1].timestamp.slice(0, 10)}`}</Tag>
              <Tag>{queryResult.items[0].source}</Tag>
            </Space>
            <ReactECharts style={{ height: 540, marginTop: 8 }} option={chartOption} />
          </>
        )}
      </Card>
      <Card title="Import CSV" style={{ marginTop: 16 }}>
        <Form form={csvForm} layout="vertical" onFinish={importCsv} initialValues={{ assetClass: "equity", market: "usa" }}>
          <div className="field-grid three">
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="assetClass" label="Asset Class"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          </div>
          <Space wrap>
            <Form.Item name="file" label="CSV" rules={[{ required: true }]}><Upload beforeUpload={() => false} maxCount={1}><Button>Choose CSV</Button></Upload></Form.Item>
            <Button type="primary" htmlType="submit">Import</Button>
          </Space>
        </Form>
      </Card>
      <MarketDataDownloader />
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
  const runs = useAsyncData(() => api.backtests(filters), []);
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
            name: `Backtest ${symbols[0] ?? "AAPL"}`,
            assetClass: settings.data.defaultAssetClass,
            market: settings.data.defaultMarket,
            venue: settings.data.defaultVenue,
            resolution: settings.data.defaultResolution,
            dataType: settings.data.defaultDataType,
            symbol: symbols[0] ?? "AAPL",
            start: settings.data.defaultStart,
            end: settings.data.defaultEnd,
            cash: settings.data.defaultCash,
            benchmarkSymbol: settings.data.defaultMarket === "china" ? "000300" : "SPY",
            feeModel: "default",
            slippageModel: "default",
            source: settings.data.defaultMarket === "china" ? "jqdata" : "",
            dockerImage: settings.data.dockerImage,
            parameters: templateDefaults(selectedTemplate)
          }}
        >
          <div className="field-grid six">
            <Form.Item name="projectId" label="Project" rules={[{ required: true, message: "Project strategy is required" }]}><Select data-testid="backtest-project-select" virtual={false} showSearch optionFilterProp="label" allowClear onChange={(value) => { setSelectedProjectId(value); const project = projects.data.find((item) => item.id === value); if (project) { const next = { assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), parameters: templateDefaults(projectTemplate(project, templates.data)) }; setAssetClass(next.assetClass); setMarket(next.market); setVenue(next.venue); setResolution(next.resolution); setDataType(next.dataType); form.setFieldsValue(next); } }} options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
            <Form.Item name="name" label="Backtest Name" rules={[{ required: true, message: "Backtest name is required" }]}><Input data-testid="backtest-name-input" /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select data-testid="backtest-asset-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { const nextVenue = defaultVenueFor(value, assetClasses.data, market); setAssetClass(value); setVenue(nextVenue); form.setFieldsValue({ venue: nextVenue }); }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select data-testid="backtest-market-select" virtual={false} showSearch optionFilterProp="label" onChange={(value) => { setMarket(value); if (assetClass === "equity") { setVenue(value); form.setFieldValue("venue", value); } form.setFieldValue("benchmarkSymbol", value === "china" ? "000300" : "SPY"); form.setFieldValue("source", value === "china" ? "jqdata" : ""); }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} onChange={setVenue} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select data-testid="backtest-resolution-select" virtual={false} showSearch optionFilterProp="label" onChange={setResolution} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select data-testid="backtest-data-type-select" virtual={false} showSearch optionFilterProp="label" onChange={setDataType} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true, message: "Symbol is required" }]}><AutoComplete data-testid="backtest-symbol-input" options={symbols.map((symbol) => ({ value: symbol, label: symbol }))} filterOption={(input, option) => String(option?.value ?? "").toLowerCase().includes(input.toLowerCase())} /></Form.Item>
            <Form.Item name="start" label="Start" rules={[{ required: true, message: "Start date is required" }]}><Input type="date" data-testid="backtest-start-input" /></Form.Item>
            <Form.Item
              name="end"
              label="End"
              rules={[
                { required: true, message: "End date is required" },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const start = getFieldValue("start");
                    if (!value || !start || value >= start) return Promise.resolve();
                    return Promise.reject(new Error("End date must be on or after start date"));
                  }
                })
              ]}
            >
              <Input type="date" data-testid="backtest-end-input" />
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
            <Form.Item name="feeModel" label="Fee Model"><Select data-testid="backtest-fee-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Fees" }]} /></Form.Item>
            <Form.Item name="slippageModel" label="Slippage Model"><Select data-testid="backtest-slippage-model-select" virtual={false} showSearch optionFilterProp="label" options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero Slippage" }]} /></Form.Item>
            <Form.Item name="source" label="Data Source"><Input placeholder="jqdata for A-share" /></Form.Item>
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
          <Form.Item name="symbol" label="Symbol"><Input placeholder="Symbol" style={{ width: 130 }} /></Form.Item>
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
  ];
  const records = {
    orders: result?.orders ?? chart?.orders ?? [],
    trades: result?.trades ?? [],
    holdings: result?.holdings ?? []
  };
  const recordColumns = [
    { title: "Field", dataIndex: "field" },
    { title: "Value", dataIndex: "value", render: (value: unknown) => shortValue(value) }
  ];
  function recordRows(row: Record<string, unknown>, index: number) {
    return Object.entries(row).map(([field, value]) => ({ id: `${index}-${field}`, field, value }));
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
          { key: "charts", label: "Charts", children: chart ? <BacktestCharts chartData={chart} /> : <Alert type="info" message="Charts are available after a successful run." /> },
          {
            key: "records",
            label: "Records",
            children: (
              <div data-testid="records-panel">
                <Card title={`Orders (${records.orders.length})`}>
                  {records.orders.length > 0 ? (
                    <Table data-testid="result-orders-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.orders[0] as Record<string, unknown>, 0)} columns={recordColumns} />
                  ) : <Alert type="info" message="No orders were parsed for this run." />}
                </Card>
                <Card title={`Trades (${records.trades.length})`} style={{ marginTop: 16 }}>
                  {records.trades.length > 0 ? (
                    <Table data-testid="result-trades-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.trades[0] as Record<string, unknown>, 0)} columns={recordColumns} />
                  ) : <Alert type="info" message="No trades were parsed for this run." />}
                </Card>
                <Card title={`Holdings (${records.holdings.length})`} style={{ marginTop: 16 }}>
                  {records.holdings.length > 0 ? (
                    <Table data-testid="result-holdings-table" size="small" pagination={{ pageSize: 5 }} rowKey="id" dataSource={recordRows(records.holdings[0] as Record<string, unknown>, 0)} columns={recordColumns} />
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
  const assetClass = Form.useWatch("assetClass", form) || "equity";
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
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Optimization</h1><Button icon={<ReloadOutlined />} onClick={optimizations.reload}>Refresh</Button></div>
      <Card title="Parameter Grid">
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", symbol: "AAPL", start: "2018-01-01", end: "2024-12-31", cash: 100000, maxCandidates: 50, dockerImage: "quantconnect/lean:latest" }}>
          <div className="field-grid">
            <Form.Item name="projectId" label="Project" rules={[{ required: true }]}><Select onChange={(value) => { const project = projects.data.find((item) => item.id === value); if (project) { const template = projectTemplate(project, templates.data); form.setFieldsValue({ assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), parameterGrid: Object.fromEntries((template?.parameters ?? []).map((parameter) => [parameter.key, String(parameter.default ?? "")])) }); } }} options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol"><Input /></Form.Item>
            <Form.Item name="start" label="Start"><Input type="date" /></Form.Item>
            <Form.Item name="end" label="End"><Input type="date" /></Form.Item>
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
  );
}

export function ResearchPage() {
  const projects = useAsyncData(api.projects, []);
  const sessions = useAsyncData(api.researchSessions, []);
  async function submit(values: any) {
    await api.startResearch(values);
    message.success("Research task queued");
    sessions.reload();
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Research</h1><Button icon={<ReloadOutlined />} onClick={sessions.reload}>Refresh</Button></div>
      <Card title="Start Research">
        <Form layout="inline" onFinish={submit} initialValues={{ port: 8888 }}>
          <Form.Item name="projectId" rules={[{ required: true }]}><Select style={{ width: 240 }} placeholder="Project" options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
          <Form.Item name="port"><InputNumber min={1024} max={65535} /></Form.Item>
          <Button type="primary" icon={<ExperimentOutlined />} htmlType="submit">Start</Button>
        </Form>
      </Card>
      <Card title="Sessions" style={{ marginTop: 16 }}>
        <Table<ResearchSession> rowKey="id" dataSource={sessions.data} size="small" columns={[{ title: "ID", dataIndex: "id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> }, { title: "URL", render: (_, session) => session.url ? <a href={session.url} target="_blank">{session.url}</a> : "-" }, { title: "Action", render: (_, session) => <Button size="small" onClick={() => api.stopResearch(session.id).then(sessions.reload)}>Stop</Button> }]} />
      </Card>
    </>
  );
}
