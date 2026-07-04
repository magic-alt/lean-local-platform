import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
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
  AppstoreOutlined,
  CloudDownloadOutlined,
  CodeOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
  SlidersOutlined,
  UnorderedListOutlined
} from "@ant-design/icons";
import Editor from "@monaco-editor/react";
import { HashRouter, Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  AppSettings,
  AssetClassInfo,
  BacktestResult,
  BacktestRun,
  ChartData,
  DataAsset,
  DataQueryResult,
  DataProvider,
  DependencyHealth,
  LocalDataFile,
  MarketInfo,
  ObjectStoreItem,
  OptimizationRun,
  PaperSession,
  Project,
  ProjectFile,
  ReportRecord,
  ResearchSession,
  StrategyTemplate,
  Task,
  Universe
} from "./api";
import { BacktestCharts, RunsTable, StatusTag } from "./components";
import { useAsyncData } from "./hooks";

const { Content, Header, Sider } = Layout;

const defaultSettings: AppSettings = {
  defaultAssetClass: "equity",
  defaultMarket: "usa",
  defaultVenue: "usa",
  defaultResolution: "daily",
  defaultDataType: "trade",
  defaultProvider: "yahoo",
  defaultAdjust: "",
  defaultStrategyTemplate: "ema_cross",
  defaultCash: 100000,
  defaultStart: "2018-01-01",
  defaultEnd: "2024-12-31",
  dockerImage: "quantconnect/lean:latest",
  researchImage: "quantconnect/research:latest",
  chartPointLimit: 1000000,
  maxConcurrentJobs: 1,
  jobTimeoutSeconds: 7200,
  logLevel: "INFO"
};

function templateDefaults(template?: StrategyTemplate) {
  return Object.fromEntries((template?.parameters ?? []).map((item) => [item.key, item.default ?? ""]));
}

function strategyFields(template?: StrategyTemplate) {
  return (template?.parameters ?? []).map((parameter) => (
    <Form.Item key={parameter.key} name={["parameters", parameter.key]} label={parameter.label}>
      {parameter.type === "number" ? (
        <InputNumber min={parameter.min ?? 0} style={{ width: "100%" }} />
      ) : (
        <Input />
      )}
    </Form.Item>
  ));
}

function projectTemplate(project?: Project, templates: StrategyTemplate[] = []) {
  const key = String(project?.config?.templateKey ?? "ema_cross");
  return templates.find((item) => item.key === key) ?? templates[0];
}

function projectMarket(project?: Project) {
  return String(project?.config?.market ?? "usa");
}

function projectAssetClass(project?: Project) {
  return String(project?.config?.assetClass ?? "equity");
}

function projectVenue(project?: Project) {
  return String(project?.config?.venue ?? projectMarket(project));
}

function projectResolution(project?: Project) {
  return String(project?.config?.resolution ?? "daily");
}

function projectDataType(project?: Project) {
  return String(project?.config?.dataType ?? "trade");
}

function defaultVenueFor(assetClass: string, assets: AssetClassInfo[], market = "usa") {
  return assetClass === "equity"
    ? market
    : assets.find((item) => item.key === assetClass)?.defaultVenue ?? market;
}

function defaultTemplateFor(assetClass: string) {
  if (assetClass === "crypto") return "crypto_momentum";
  if (assetClass === "future") return "future_trend";
  return "ema_cross";
}

function Dashboard() {
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
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Dashboard</h1>
        <Button icon={<ReloadOutlined />} onClick={() => { runs.reload(); tasks.reload(); }}>Refresh</Button>
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
  const universe = useAsyncData<Universe>(api.djiaUniverse, { key: "djia", name: "Dow Jones Industrial Average", asOf: "", source: "", components: [] });
  const [symbolsText, setSymbolsText] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [localSymbols, setLocalSymbols] = useState<string[]>([]);
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
    api.symbols(selectedMarket, selectedAssetClass, selectedVenue, selectedResolution, selectedDataType)
      .then((result) => setLocalSymbols(result.symbols))
      .catch((error) => message.error((error as Error).message));
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

  function addTypedSymbols() {
    const typed = symbolsText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean);
    setSelectedSymbols(Array.from(new Set([...selectedSymbols, ...typed])));
    setSymbolsText("");
  }

  async function submit(values: any) {
    const symbols = Array.from(new Set([...selectedSymbols, ...symbolsText.split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter(Boolean)]));
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
  }

  const marketProviders = providers.data.filter((provider) => (
    provider.assetClasses?.includes(selectedAssetClass) ||
    (selectedAssetClass === "equity" && provider.markets.includes(selectedMarket))
  ));
  const djiaReady = selectedAssetClass === "equity" && selectedMarket === "usa";
  const localRows = localSymbols.map((symbol) => ({ symbol, hasLocalData: true }));
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
          <Button onClick={addTypedSymbols}>Add</Button>
          <Button type="primary" icon={<CloudDownloadOutlined />} htmlType="submit">Fetch</Button>
        </Space.Compact>
      </Form>
      <Space wrap style={{ marginBottom: 12 }}>
        {djiaReady && <Button onClick={() => setSelectedSymbols(universe.data.components.filter((item) => item.hasLocalData).map((item) => item.symbol))}>Use Ready DJIA</Button>}
        {djiaReady && <Button onClick={() => setSelectedSymbols(universe.data.components.map((item) => item.symbol))}>Use All DJIA</Button>}
        <Button onClick={() => setSelectedSymbols(localSymbols.slice(0, 20))}>Use Local Sample</Button>
        <Button onClick={() => setSelectedSymbols([])}>Clear</Button>
        {selectedSymbols.map((symbol) => <Tag key={symbol} closable onClose={() => setSelectedSymbols(selectedSymbols.filter((item) => item !== symbol))}>{symbol}</Tag>)}
      </Space>
      {selectedAssetClass !== "equity" && selectedProvider !== "binance" && (
        <Alert style={{ marginBottom: 12 }} type="warning" showIcon message="This asset class currently uses local LEAN files or CSV import unless Binance crypto daily is selected." />
      )}
      <Table
        rowKey="symbol"
        size="small"
        dataSource={djiaReady && !compact ? universe.data.components : localRows}
        loading={universe.loading}
        pagination={compact ? { pageSize: 8 } : { pageSize: 10 }}
        rowSelection={{
          selectedRowKeys: selectedSymbols,
          onChange: (keys) => setSelectedSymbols(keys.map(String))
        }}
        columns={[
          { title: "Symbol", dataIndex: "symbol", width: 100 },
          { title: "Name", dataIndex: "name", ellipsis: true, render: (value) => value ?? "-" },
          { title: "Asset", render: () => selectedAssetClass },
          { title: "Venue", render: () => selectedAssetClass === "equity" ? selectedMarket : selectedVenue },
          { title: "Local", dataIndex: "hasLocalData", width: 90, render: (value: boolean) => <Tag color={value ? "success" : "warning"}>{value ? "ready" : "missing"}</Tag> }
        ]}
      />
      <Alert
        style={{ marginTop: 12 }}
        type="info"
        showIcon
        message="Public data sources may throttle or change. Equity A/HK support is daily-bar only; crypto import is daily Binance spot in this version; futures should use local LEAN files or CSV import with verified contract metadata."
      />
    </Card>
  );
}

function ProjectsPage() {
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
                options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))}
                onChange={(value) => {
                  form.setFieldValue("templateKey", defaultTemplateFor(value));
                  form.setFieldValue("venue", defaultVenueFor(value, assetClasses.data, form.getFieldValue("market") || "usa"));
                }}
              />
            </Form.Item>
            <Form.Item name="market" label="Market"><Select options={markets.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={selectedAssetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="templateKey" label="Strategy"><Select options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
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

function ProjectWorkspacePage() {
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
    const nextFile = path ?? target.main_file;
    setActiveFile(nextFile);
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
    symbol: symbols[0] ?? (market === "china" ? "600519" : market === "hongkong" ? "00700" : "AAPL"),
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
          { key: "code", label: "Code", children: <Card title={`${activeFile ?? project.main_file}${dirty ? " *" : ""}`}><Space wrap style={{ marginBottom: 8 }}>{files.filter((item) => item.type === "file").map((file) => <Tag key={file.path} color={file.path === activeFile ? "blue" : "default"} onClick={() => loadProjectFile(project, file.path)}>{file.path}</Tag>)}</Space><Editor height="540px" language={activeFile?.endsWith(".cs") ? "csharp" : "python"} value={content} onChange={(value) => { setContent(value ?? ""); setDirty(true); }} theme="vs-dark" /><Button type="primary" style={{ marginTop: 12 }} icon={<CodeOutlined />} disabled={!dirty} onClick={saveFile}>Save</Button></Card> },
          { key: "data", label: "Data", children: <MarketDataDownloader compact forcedAssetClass={assetClass} forcedMarket={market} forcedVenue={venue} forcedResolution={resolution} forcedDataType={dataType} /> },
          { key: "backtest", label: "Backtest", children: <Card title="Run Backtest"><Form key={`${project.id}-${symbols.length}`} layout="vertical" onFinish={submitBacktest} initialValues={backtestInitial}><div className="field-grid six"><Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.map((symbol) => ({ value: symbol, label: symbol }))} /></Form.Item><Form.Item name="start" label="Start" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item name="end" label="End" rules={[{ required: true }]}><Input type="date" /></Form.Item><Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item><Form.Item name="dockerImage" label="Image"><Input /></Form.Item>{strategyFields(template)}</div><Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit">Run</Button></Form></Card> },
          { key: "results", label: "Results", children: <Card title="Project Backtests"><RunsTable runs={projectRuns} onOpen={(id) => navigate(`/runs/${id}`)} /></Card> },
          { key: "logs", label: "Logs", children: <Card title="Project Tasks"><Table<Task> rowKey="id" dataSource={projectTasks} size="small" columns={[{ title: "Kind", dataIndex: "kind" }, { title: "Title", dataIndex: "title" }, { title: "Status", dataIndex: "status", render: (status) => <StatusTag status={status} /> }, { title: "Created", dataIndex: "created_at" }]} /></Card> }
        ]} />
      )}
    </>
  );
}

function DataPage() {
  const assets = useAsyncData(api.dataAssets, []);
  const dataFiles = useAsyncData(() => api.dataFiles(), { items: [], count: 0 });
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const [csvForm] = Form.useForm();
  const [queryForm] = Form.useForm();
  const [queryResult, setQueryResult] = useState<DataQueryResult>();
  const csvAssetClass = Form.useWatch("assetClass", csvForm) || "equity";
  const csvAssetInfo = assetClasses.data.find((item) => item.key === csvAssetClass);

  async function importCsv(values: any) {
    const file = values.file?.fileList?.[0]?.originFileObj;
    if (!file) return message.error("Choose a CSV file");
    const formData = new FormData();
    ["symbol", "assetClass", "market", "venue", "dataType", "dateCol", "openCol", "highCol", "lowCol", "closeCol", "volumeCol"].forEach((key) => formData.append(key, values[key] ?? ""));
    formData.append("overwrite", String(Boolean(values.overwrite)));
    formData.append("file", file);
    await api.importCsv(formData);
    message.success("CSV imported");
    csvForm.resetFields();
    assets.reload();
    dataFiles.reload();
  }

  async function queryMarketData(values: any) {
    const result = await api.queryData({
      ...values,
      limit: values.limit ?? 200
    });
    setQueryResult(result);
    if (!result.enabled) {
      message.warning("ClickHouse is not enabled or not reachable.");
    }
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Data Library</h1><Button icon={<ReloadOutlined />} onClick={() => { assets.reload(); dataFiles.reload(); }}>Refresh</Button></div>
      <MarketDataDownloader />
      <div className="two-column" style={{ marginTop: 16 }}>
        <Card title="Import CSV">
          <Form form={csvForm} layout="vertical" onFinish={importCsv} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", dataType: "trade", dateCol: "timestamp", openCol: "open", highCol: "high", lowCol: "low", closeCol: "close", volumeCol: "volume" }}>
            <div className="field-grid">
              <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="assetClass" label="Asset Class"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
              <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
              <Form.Item name="venue" label="Venue"><Select disabled={csvAssetClass === "equity"} options={(csvAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
              <Form.Item name="dataType" label="Data Type"><Select options={(csvAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            </div>
            <div className="field-grid">{["dateCol", "openCol", "highCol", "lowCol", "closeCol", "volumeCol"].map((name) => <Form.Item key={name} name={name} label={name}><Input /></Form.Item>)}</div>
            <Form.Item name="file" label="CSV" rules={[{ required: true }]}><Upload beforeUpload={() => false} maxCount={1}><Button>Choose CSV</Button></Upload></Form.Item>
            <Form.Item name="overwrite" valuePropName="checked"><Checkbox>Overwrite existing</Checkbox></Form.Item>
            <Button type="primary" htmlType="submit">Import</Button>
          </Form>
        </Card>
        <Card title="Imported Assets">
          <Table<DataAsset> rowKey="id" size="small" dataSource={assets.data} columns={[
            { title: "Symbol", dataIndex: "symbol" },
            { title: "Asset", render: (_, asset) => asset.asset_class ?? String(asset.metadata?.asset_class ?? "equity") },
            { title: "Venue", render: (_, asset) => asset.venue ?? String(asset.metadata?.venue ?? asset.metadata?.market ?? "-") },
            { title: "Source", dataIndex: "source" },
            { title: "Rows", dataIndex: "rows" },
            { title: "Range", render: (_, asset) => `${asset.first_date} -> ${asset.last_date}` },
            { title: "File", dataIndex: "lean_file", ellipsis: true }
          ]} />
        </Card>
      </div>
      <Card title="Local LEAN Data Files" style={{ marginTop: 16 }}>
        <Table<LocalDataFile>
          rowKey={(row) => row.file}
          size="small"
          dataSource={dataFiles.data.items}
          pagination={{ pageSize: 12 }}
          columns={[
            { title: "Asset", dataIndex: "assetClass" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "Venue", dataIndex: "venue" },
            { title: "Resolution", dataIndex: "resolution" },
            { title: "Type", dataIndex: "dataType" },
            { title: "Rows", dataIndex: "rows", render: (value) => value ?? "-" },
            { title: "File", dataIndex: "file", ellipsis: true }
          ]}
        />
      </Card>
      <Card title="ClickHouse Bar Query" style={{ marginTop: 16 }}>
        <Form
          form={queryForm}
          layout="inline"
          onFinish={queryMarketData}
          initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", limit: 200 }}
        >
          <Form.Item name="assetClass" rules={[{ required: true }]}><Select style={{ width: 140 }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
          <Form.Item name="symbol" rules={[{ required: true }]}><Input style={{ width: 140 }} placeholder="AAPL" /></Form.Item>
          <Form.Item name="market"><Select style={{ width: 140 }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
          <Form.Item name="venue"><Input style={{ width: 120 }} placeholder="venue" /></Form.Item>
          <Form.Item name="resolution"><Select style={{ width: 120 }} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="dataType"><Select style={{ width: 120 }} options={["trade", "quote", "open_interest"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="limit"><InputNumber min={1} max={5000} style={{ width: 110 }} /></Form.Item>
          <Button type="primary" htmlType="submit">Query</Button>
        </Form>
        {queryResult && !queryResult.enabled && <Alert style={{ marginTop: 12 }} type="warning" showIcon message="ClickHouse mirror is unavailable. Start the Compose stack or install backend dependencies to enable this preview." />}
        {queryResult?.enabled && (
          <Table
            style={{ marginTop: 12 }}
            rowKey="timestamp"
            size="small"
            dataSource={queryResult.items}
            pagination={{ pageSize: 10 }}
            columns={[
              { title: "Time", dataIndex: "timestamp" },
              { title: "Open", dataIndex: "open" },
              { title: "High", dataIndex: "high" },
              { title: "Low", dataIndex: "low" },
              { title: "Close", dataIndex: "close" },
              { title: "Volume", dataIndex: "volume" },
              { title: "Source", dataIndex: "source" }
            ]}
          />
        )}
      </Card>
    </>
  );
}

function BacktestsPage() {
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const settings = useAsyncData<AppSettings>(api.settings, defaultSettings);
  const [filters, setFilters] = useState<{ status?: string; projectId?: string; symbol?: string }>({});
  const runs = useAsyncData(() => api.backtests(filters), []);
  const [form] = Form.useForm();
  const [assetClass, setAssetClass] = useState("equity");
  const [market, setMarket] = useState("usa");
  const [venue, setVenue] = useState("usa");
  const [resolution, setResolution] = useState("daily");
  const [dataType, setDataType] = useState("trade");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>();

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
    const run = await api.createBacktest({
      ...values,
      assetClass,
      market,
      venue,
      resolution,
      dataType,
      projectId: values.projectId,
      parameters: values.parameters ?? {}
    });
    message.success("Backtest queued");
    navigate(`/runs/${run.id}`);
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Backtests</h1><Button icon={<ReloadOutlined />} onClick={runs.reload}>Refresh</Button></div>
      <Card title="New Backtest">
        <Form
          form={form}
          key={`${market}-${selectedProjectId ?? "none"}-${templates.data.length}`}
          layout="vertical"
          onFinish={submit}
          initialValues={{ assetClass: settings.data.defaultAssetClass, market: settings.data.defaultMarket, venue: settings.data.defaultVenue, resolution: settings.data.defaultResolution, dataType: settings.data.defaultDataType, symbol: symbols[0] ?? "AAPL", start: settings.data.defaultStart, end: settings.data.defaultEnd, cash: settings.data.defaultCash, dockerImage: settings.data.dockerImage, parameters: templateDefaults(selectedTemplate) }}
        >
          <div className="field-grid six">
            <Form.Item name="projectId" label="Project"><Select allowClear onChange={(value) => { setSelectedProjectId(value); const project = projects.data.find((item) => item.id === value); if (project) { const next = { assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project), parameters: templateDefaults(projectTemplate(project, templates.data)) }; setAssetClass(next.assetClass); setMarket(next.market); setVenue(next.venue); setResolution(next.resolution); setDataType(next.dataType); form.setFieldsValue(next); } }} options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select onChange={(value) => { const nextVenue = defaultVenueFor(value, assetClasses.data, market); setAssetClass(value); setVenue(nextVenue); form.setFieldsValue({ venue: nextVenue }); }} options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select onChange={(value) => { setMarket(value); if (assetClass === "equity") { setVenue(value); form.setFieldValue("venue", value); } }} options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} onChange={setVenue} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select onChange={setResolution} options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select onChange={setDataType} options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.map((symbol) => ({ value: symbol, label: symbol }))} /></Form.Item>
            <Form.Item name="start" label="Start" rules={[{ required: true }]}><Input type="date" /></Form.Item>
            <Form.Item name="end" label="End" rules={[{ required: true }]}><Input type="date" /></Form.Item>
            <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
            {strategyFields(selectedTemplate)}
          </div>
          <Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit">Run</Button>
        </Form>
      </Card>
      <Card title="History" style={{ marginTop: 16 }}>
        <Form layout="inline" style={{ marginBottom: 12 }} onFinish={(values) => setFilters(values)}>
          <Form.Item name="status"><Select allowClear placeholder="Status" style={{ width: 150 }} options={["created", "queued", "running", "success", "failed", "cancelled"].map((value) => ({ value, label: value }))} /></Form.Item>
          <Form.Item name="projectId"><Select allowClear placeholder="Project" style={{ width: 220 }} options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
          <Form.Item name="symbol"><Input placeholder="Symbol" style={{ width: 130 }} /></Form.Item>
          <Button htmlType="submit">Filter</Button>
          <Button onClick={() => setFilters({})}>Clear</Button>
        </Form>
        <RunsTable runs={runs.data} onOpen={(id) => navigate(`/runs/${id}`)} />
      </Card>
    </>
  );
}

function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<BacktestRun>();
  const [chart, setChart] = useState<ChartData>();
  const [result, setResult] = useState<BacktestResult>();
  const [logs, setLogs] = useState("");
  const active = run ? ["created", "queued", "running"].includes(run.status) : false;
  const reload = useCallback(async () => {
    if (!id) return;
    const next = await api.backtest(id);
    setRun(next);
    setLogs((await api.logs(id)).logs);
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
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">{run.name ?? run.id}</h1>
        <Space>
          <StatusTag status={run.status} />
          {active && <Button danger onClick={cancelRun}>Cancel</Button>}
          <Button onClick={reload} icon={<ReloadOutlined />}>Refresh</Button>
        </Space>
      </div>
      {(run.error_message || run.error) && <Alert type="error" showIcon message={run.error_message ?? run.error} style={{ marginBottom: 16 }} />}
      <div className="grid">{["End Equity", "Net Profit", "Sharpe Ratio", "Drawdown"].map((key) => <Card key={key}><Statistic title={key} value={run.statistics?.[key] ?? "N/A"} /></Card>)}</div>
      <Tabs
        items={[
          {
            key: "status",
            label: "Status",
            children: (
              <Card>
                <Space wrap>
                  <Tag>job_id: {run.id}</Tag>
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
              <Card title="Summary">
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
          { key: "charts", label: "Charts", children: chart ? <BacktestCharts chartData={chart} /> : <Alert type="info" message="Charts are available after a successful run." /> },
          {
            key: "raw",
            label: "Raw Files",
            children: <Card title="Artifacts">{(run.artifacts ?? []).map((name) => <a className="artifact-link" key={name} target="_blank" href={`/api/backtests/${run.id}/artifacts/${name}`}>{name}</a>)}</Card>
          },
          { key: "logs", label: "Logs", children: <Card><pre className="log-view">{logs || "No logs yet."}</pre></Card> }
        ]}
      />
    </>
  );
}

function OptimizationPage() {
  const projects = useAsyncData(api.projects, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const optimizations = useAsyncData(api.optimizations, []);
  const [form] = Form.useForm();
  const assetClass = Form.useWatch("assetClass", form) || "equity";
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === assetClass);
  async function submit(values: any) {
    await api.createOptimization({
      ...values,
      fastValues: String(values.fastValues).split(",").map((x) => Number(x.trim())).filter(Boolean),
      slowValues: String(values.slowValues).split(",").map((x) => Number(x.trim())).filter(Boolean)
    });
    message.success("Optimization queued");
    optimizations.reload();
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Optimization</h1><Button icon={<ReloadOutlined />} onClick={optimizations.reload}>Refresh</Button></div>
      <Card title="Parameter Grid">
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", symbol: "AAPL", start: "2018-01-01", end: "2024-12-31", cash: 100000, fastValues: "5,10,15", slowValues: "20,30,50", dockerImage: "quantconnect/lean:latest" }}>
          <div className="field-grid">
            <Form.Item name="projectId" label="Project" rules={[{ required: true }]}><Select onChange={(value) => { const project = projects.data.find((item) => item.id === value); if (project) form.setFieldsValue({ assetClass: projectAssetClass(project), market: projectMarket(project), venue: projectVenue(project), resolution: projectResolution(project), dataType: projectDataType(project) }); }} options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol"><Input /></Form.Item>
            <Form.Item name="start" label="Start"><Input type="date" /></Form.Item>
            <Form.Item name="end" label="End"><Input type="date" /></Form.Item>
            <Form.Item name="fastValues" label="Fast Values"><Input /></Form.Item>
            <Form.Item name="slowValues" label="Slow Values"><Input /></Form.Item>
            <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
          </div>
          <Button type="primary" icon={<SlidersOutlined />} htmlType="submit">Queue Optimization</Button>
        </Form>
      </Card>
      <Card title="Optimization Runs" style={{ marginTop: 16 }}>
        <Table<OptimizationRun> rowKey="id" dataSource={optimizations.data} size="small" columns={[{ title: "ID", dataIndex: "id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> }, { title: "Created", dataIndex: "created_at" }]} />
      </Card>
    </>
  );
}

function ResearchPage() {
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

function PaperPage() {
  const sessions = useAsyncData(api.paperSessions, []);
  const projects = useAsyncData(api.projects, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const [form] = Form.useForm();
  const assetClass = Form.useWatch("assetClass", form) || "equity";
  const market = Form.useWatch("market", form) || "usa";
  const venue = Form.useWatch("venue", form) || defaultVenueFor(assetClass, assetClasses.data, market);
  const resolution = Form.useWatch("resolution", form) || "daily";
  const dataType = Form.useWatch("dataType", form) || "trade";
  const [symbols, setSymbols] = useState<string[]>([]);
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === assetClass);

  useEffect(() => {
    api.symbols(market, assetClass, venue, resolution, dataType)
      .then((result) => setSymbols(result.symbols))
      .catch((error) => message.error((error as Error).message));
  }, [assetClass, dataType, market, resolution, venue]);

  async function submit(values: any) {
    await api.createPaperSession({
      ...values,
      venue: assetClass === "equity" ? values.market : values.venue,
      parameters: {}
    });
    message.success("Paper session created");
    form.resetFields();
    sessions.reload();
  }

  async function status(session: PaperSession, nextStatus: string) {
    await api.updatePaperSessionStatus(session.id, nextStatus);
    await sessions.reload();
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Paper Replay</h1><Button icon={<ReloadOutlined />} onClick={sessions.reload}>Refresh</Button></div>
      <Alert style={{ marginBottom: 16 }} type="info" showIcon message="Paper Replay is a local simulated session registry. It does not connect to brokers or place real orders." />
      <Card title="Create Paper Session">
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", cash: 100000 }}>
          <div className="field-grid six">
            <Form.Item name="name" label="Name"><Input placeholder="BTCUSDT paper replay" /></Form.Item>
            <Form.Item name="projectId" label="Project"><Select allowClear options={projects.data.map((project) => ({ value: project.id, label: project.name }))} /></Form.Item>
            <Form.Item name="assetClass" label="Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} onChange={(value) => form.setFieldValue("venue", defaultVenueFor(value, assetClasses.data, market))} /></Form.Item>
            <Form.Item name="market" label="Market"><Select options={[{ value: "usa", label: "US" }, { value: "china", label: "A Share" }, { value: "hongkong", label: "Hong Kong" }]} onChange={(value) => { if (assetClass === "equity") form.setFieldValue("venue", value); }} /></Form.Item>
            <Form.Item name="venue" label="Venue"><Select disabled={assetClass === "equity"} options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="resolution" label="Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dataType" label="Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.map((symbol) => ({ value: symbol, label: symbol }))} /></Form.Item>
            <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
          </div>
          <Button type="primary" htmlType="submit">Create</Button>
        </Form>
      </Card>
      <Card title="Sessions" style={{ marginTop: 16 }}>
        <Table<PaperSession>
          rowKey="id"
          dataSource={sessions.data}
          size="small"
          columns={[
            { title: "Name", dataIndex: "name" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "Asset", dataIndex: "asset_class" },
            { title: "Venue", dataIndex: "venue" },
            { title: "Status", dataIndex: "status", render: (value) => <StatusTag status={value} /> },
            { title: "Equity", dataIndex: "equity" },
            { title: "Created", dataIndex: "created_at" },
            { title: "Actions", render: (_, session) => <Space><Button size="small" onClick={() => status(session, "running")}>Run</Button><Button size="small" onClick={() => status(session, "paused")}>Pause</Button><Button size="small" danger onClick={() => status(session, "stopped")}>Stop</Button></Space> }
          ]}
        />
      </Card>
    </>
  );
}

function ReportsPage() {
  const runs = useAsyncData(api.backtests, []);
  const reports = useAsyncData(api.reports, []);
  async function submit(values: any) {
    await api.createReport(values);
    message.success("Report task queued");
    reports.reload();
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Reports</h1><Button icon={<ReloadOutlined />} onClick={() => { runs.reload(); reports.reload(); }}>Refresh</Button></div>
      <Card title="Generate Report">
        <Form layout="inline" onFinish={submit}>
          <Form.Item name="runId" rules={[{ required: true }]}><Select style={{ width: 420 }} placeholder="Backtest run" options={runs.data.map((run) => ({ value: run.id, label: run.id }))} /></Form.Item>
          <Button type="primary" icon={<FileTextOutlined />} htmlType="submit">Generate</Button>
        </Form>
      </Card>
      <Card title="Reports" style={{ marginTop: 16 }}>
        <Table<ReportRecord> rowKey="id" dataSource={reports.data} size="small" columns={[{ title: "ID", dataIndex: "id", ellipsis: true }, { title: "Run", dataIndex: "run_id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> }, { title: "Open", render: (_, report) => report.report_path ? <a href={`/api/reports/${report.id}/file`} target="_blank">HTML</a> : "-" }]} />
      </Card>
    </>
  );
}

function ObjectStorePage() {
  const items = useAsyncData(api.objectStoreItems, []);
  const [form] = Form.useForm();
  async function submit(values: any) {
    const file = values.file?.fileList?.[0]?.originFileObj;
    if (!file) return message.error("Choose a file");
    const formData = new FormData();
    formData.append("file", file);
    await api.uploadObjectStoreItem(values.key, formData);
    message.success("Uploaded");
    form.resetFields();
    items.reload();
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Object Store</h1><Button icon={<ReloadOutlined />} onClick={items.reload}>Refresh</Button></div>
      <Card title="Upload">
        <Form form={form} layout="inline" onFinish={submit}>
          <Form.Item name="key" rules={[{ required: true }]}><Input placeholder="models/model.json" /></Form.Item>
          <Form.Item name="file" rules={[{ required: true }]}><Upload beforeUpload={() => false} maxCount={1}><Button>Choose</Button></Upload></Form.Item>
          <Button type="primary" htmlType="submit">Upload</Button>
        </Form>
      </Card>
      <Card title="Items" style={{ marginTop: 16 }}>
        <Table<ObjectStoreItem> rowKey="key" dataSource={items.data} size="small" columns={[{ title: "Key", dataIndex: "key" }, { title: "Size", dataIndex: "size" }, { title: "Updated", dataIndex: "updated_at" }, { title: "Actions", render: (_, item) => <Space><a href={`/api/object-store/${item.key}`} target="_blank">Download</a><a onClick={() => api.deleteObjectStoreItem(item.key).then(items.reload)}>Delete</a></Space> }]} />
      </Card>
    </>
  );
}

function TasksPage() {
  const tasks = useAsyncData(api.tasks, []);
  const [selected, setSelected] = useState<Task>();
  const [logs, setLogs] = useState("");
  async function open(task: Task) {
    setSelected(task);
    setLogs((await api.taskLogs(task.id)).logs);
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Tasks</h1><Button icon={<ReloadOutlined />} onClick={tasks.reload}>Refresh</Button></div>
      <Card title="Queue">
        <Table<Task> rowKey="id" dataSource={tasks.data} size="small" columns={[{ title: "Kind", dataIndex: "kind" }, { title: "Title", dataIndex: "title" }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> }, { title: "Created", dataIndex: "created_at" }, { title: "Open", render: (_, task) => <a onClick={() => open(task)}>Logs</a> }]} />
      </Card>
      {selected && <Card title={`${selected.kind} / ${selected.id}`} style={{ marginTop: 16 }}><pre className="log-view">{logs}</pre></Card>}
    </>
  );
}

function MonitoringPage() {
  const health = useAsyncData<DependencyHealth>(api.dependencyHealth, {
    status: "degraded",
    dependencies: [],
    urls: {
      prometheus: "http://127.0.0.1:9090",
      grafana: "http://127.0.0.1:3000"
    }
  });
  const up = health.data.dependencies.filter((item) => item.ok).length;
  const down = Math.max(0, health.data.dependencies.length - up);
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Monitoring</h1>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={health.reload}>Refresh</Button>
          <Button href={health.data.urls.prometheus} target="_blank">Prometheus</Button>
          <Button type="primary" href={health.data.urls.grafana} target="_blank">Grafana</Button>
        </Space>
      </div>
      <div className="grid">
        <Card><Statistic title="Status" value={health.data.status} /></Card>
        <Card><Statistic title="Dependencies Up" value={up} /></Card>
        <Card><Statistic title="Dependencies Down" value={down} /></Card>
        <Card><Statistic title="Metrics Endpoint" value="/metrics" /></Card>
      </div>
      <Card title="Dependency Health">
        <Table
          rowKey="service"
          size="small"
          dataSource={health.data.dependencies}
          loading={health.loading}
          columns={[
            { title: "Service", dataIndex: "service" },
            {
              title: "Status",
              dataIndex: "ok",
              render: (ok: boolean, item) => (
                <Tooltip title={item.detail}>
                  <Tag color={ok ? "success" : "error"}>{ok ? "up" : "down"}</Tag>
                </Tooltip>
              )
            },
            { title: "Latency", dataIndex: "latency_ms", render: (value) => value === undefined ? "-" : `${value} ms` },
            { title: "Detail", dataIndex: "detail", ellipsis: true }
          ]}
        />
      </Card>
      <Alert
        style={{ marginTop: 16 }}
        type="info"
        showIcon
        message="Grafana is intended for internal platform monitoring: API latency, task state, dependency health, data import status, and LEAN runtime behavior."
      />
    </>
  );
}

function SettingsPage() {
  const settings = useAsyncData<AppSettings>(api.settings, defaultSettings);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const assetClasses = useAsyncData<AssetClassInfo[]>(api.assetClasses, []);
  const markets = useAsyncData<MarketInfo[]>(api.markets, []);
  const providers = useAsyncData<DataProvider[]>(api.dataProviders, []);
  const [form] = Form.useForm();
  const selectedAssetClass = Form.useWatch("defaultAssetClass", form) || "equity";
  const selectedAssetInfo = assetClasses.data.find((item) => item.key === selectedAssetClass);

  useEffect(() => {
    form.setFieldsValue(settings.data);
  }, [settings.data, form]);

  async function submit(values: Partial<AppSettings>) {
    await api.updateSettings(values);
    message.success("Settings saved");
    settings.reload();
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Settings</h1><Button icon={<ReloadOutlined />} onClick={settings.reload}>Refresh</Button></div>
      <Card title="Defaults">
        <Form form={form} layout="vertical" onFinish={submit}>
          <div className="field-grid">
            <Form.Item name="defaultAssetClass" label="Default Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultMarket" label="Default Market"><Select options={markets.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultVenue" label="Default Venue"><Select options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultResolution" label="Default Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultDataType" label="Default Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultProvider" label="Default Provider"><Select options={providers.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultAdjust" label="Default Adjust"><Select options={[{ value: "", label: "Raw" }, { value: "qfq", label: "QFQ" }, { value: "hfq", label: "HFQ" }]} /></Form.Item>
            <Form.Item name="defaultStrategyTemplate" label="Default Strategy"><Select options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultStart" label="Default Start"><Input type="date" /></Form.Item>
            <Form.Item name="defaultEnd" label="Default End"><Input type="date" /></Form.Item>
            <Form.Item name="defaultCash" label="Default Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="chartPointLimit" label="Chart Point Limit"><InputNumber min={1000} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="maxConcurrentJobs" label="Max Concurrent Jobs"><InputNumber min={1} max={8} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="jobTimeoutSeconds" label="Job Timeout Seconds"><InputNumber min={60} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="logLevel" label="Log Level"><Select options={["DEBUG", "INFO", "WARNING", "ERROR"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="dockerImage" label="Docker Image"><Input /></Form.Item>
            <Form.Item name="researchImage" label="Research Image"><Input /></Form.Item>
          </div>
          <Button type="primary" htmlType="submit">Save Settings</Button>
        </Form>
      </Card>
    </>
  );
}

function AppShell() {
  const menuItems = useMemo(() => [
    { key: "/", icon: <AppstoreOutlined />, label: <Link to="/">Dashboard</Link> },
    { key: "/workspace", icon: <CodeOutlined />, label: <Link to="/workspace">Workspace</Link> },
    { key: "/projects", icon: <FolderOpenOutlined />, label: <Link to="/projects">Projects</Link> },
    { key: "/data", icon: <DatabaseOutlined />, label: <Link to="/data">Data</Link> },
    { key: "/backtests", icon: <PlayCircleOutlined />, label: <Link to="/backtests">Backtests</Link> },
    { key: "/optimization", icon: <SlidersOutlined />, label: <Link to="/optimization">Optimization</Link> },
    { key: "/paper", icon: <ExperimentOutlined />, label: <Link to="/paper">Paper</Link> },
    { key: "/research", icon: <ExperimentOutlined />, label: <Link to="/research">Research</Link> },
    { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">Reports</Link> },
    { key: "/object-store", icon: <DatabaseOutlined />, label: <Link to="/object-store">Object Store</Link> },
    { key: "/tasks", icon: <UnorderedListOutlined />, label: <Link to="/tasks">Tasks</Link> },
    { key: "/monitoring", icon: <DashboardOutlined />, label: <Link to="/monitoring">Monitoring</Link> },
    { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> }
  ], []);
  return (
    <Layout className="app-layout">
      <Sider breakpoint="lg" collapsedWidth="0"><div className="app-logo">LEAN Local</div><Menu theme="dark" mode="inline" items={menuItems} /></Sider>
      <Layout>
        <Header className="app-header"><Space><strong>LEAN Local Workbench</strong><Tag color="blue">docker</Tag><Tag color="green">multi-asset</Tag><Tag color="purple">paper</Tag></Space></Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/workspace" element={<ProjectWorkspacePage />} />
            <Route path="/workspace/:projectId" element={<ProjectWorkspacePage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/backtests" element={<BacktestsPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route path="/optimization" element={<OptimizationPage />} />
            <Route path="/paper" element={<PaperPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/object-store" element={<ObjectStorePage />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return <HashRouter><AppShell /></HashRouter>;
}
