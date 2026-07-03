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
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Upload,
  message
} from "antd";
import {
  AppstoreOutlined,
  CloudDownloadOutlined,
  CodeOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SlidersOutlined,
  ToolOutlined,
  UnorderedListOutlined
} from "@ant-design/icons";
import Editor from "@monaco-editor/react";
import { HashRouter, Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  BacktestRun,
  Capability,
  ChartData,
  DataAsset,
  DataProvider,
  ObjectStoreItem,
  OptimizationRun,
  Project,
  ProjectFile,
  ReportRecord,
  ResearchSession,
  Task,
  Universe
} from "./api";
import { BacktestCharts, RunsTable, StatusTag } from "./components";

const { Content, Header, Sider } = Layout;

function useAsyncData<T>(loader: () => Promise<T>, initial: T) {
  const [data, setData] = useState<T>(initial);
  const [loading, setLoading] = useState(false);
  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }, [loader]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, loading, reload, setData };
}

function Dashboard() {
  const navigate = useNavigate();
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const latest = runs.data[0];
  const activeTasks = tasks.data.filter((task) => task.status === "queued" || task.status === "running").length;
  async function createDjiaProject() {
    const project = await api.createProject({ name: "DJIA EMA Strategy", language: "Python", algorithmClass: "DjiaEmaAlgorithm" });
    message.success("DJIA project created");
    navigate(`/workspace/${project.id}`);
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Dashboard</h1><Button icon={<ReloadOutlined />} onClick={() => { runs.reload(); tasks.reload(); }}>Refresh</Button></div>
      <Card className="workflow-card" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button type="primary" icon={<FolderOpenOutlined />} onClick={createDjiaProject}>New DJIA Project</Button>
          <Button icon={<DatabaseOutlined />} onClick={() => navigate("/data")}>Fetch DJIA Data</Button>
          <Button icon={<PlayCircleOutlined />} onClick={() => navigate("/backtests")}>Run Backtest</Button>
          <Button icon={<FileTextOutlined />} onClick={() => navigate("/reports")}>Reports</Button>
        </Space>
      </Card>
      <div className="grid">
        <Card><Statistic title="Backtests" value={runs.data.length} /></Card>
        <Card><Statistic title="Active Tasks" value={activeTasks} /></Card>
        <Card><Statistic title="Latest Net Profit" value={latest?.statistics?.["Net Profit"] ?? "N/A"} /></Card>
        <Card><Statistic title="Latest Sharpe" value={latest?.statistics?.["Sharpe Ratio"] ?? "N/A"} /></Card>
      </div>
      <Card title="Recent Backtests"><RunsTable runs={runs.data} onOpen={(id) => navigate(`/runs/${id}`)} /></Card>
    </>
  );
}

function CapabilitiesPage() {
  const capabilities = useAsyncData(api.capabilities, []);
  const colors: Record<Capability["status"], string> = {
    enabled: "success",
    experimental: "warning",
    disabled: "default"
  };
  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">LEAN Capabilities</h1>
        <Button icon={<ReloadOutlined />} onClick={capabilities.reload}>Refresh</Button>
      </div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="This platform exposes the local open-source Docker workflow in the browser. QuantConnect cloud sync and live trading remain separate, account-backed flows."
      />
      <Card title="Feature Matrix">
        <Table<Capability>
          rowKey="key"
          dataSource={capabilities.data}
          loading={capabilities.loading}
          pagination={false}
          columns={[
            { title: "Group", dataIndex: "group", width: 150 },
            { title: "Feature", dataIndex: "name", width: 190 },
            { title: "Status", dataIndex: "status", width: 130, render: (status: Capability["status"]) => <Tag color={colors[status]}>{status}</Tag> },
            { title: "Surface", dataIndex: "surface", width: 220 },
            { title: "Notes", dataIndex: "notes" }
          ]}
        />
      </Card>
    </>
  );
}

function DjiaDataDownloader({ compact = false }: { compact?: boolean }) {
  const universe = useAsyncData<Universe>(api.djiaUniverse, { key: "djia", name: "Dow Jones Industrial Average", asOf: "", source: "", components: [] });
  const providers = useAsyncData<DataProvider[]>(api.dataProviders, []);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [form] = Form.useForm();

  async function submit(values: any) {
    if (selectedSymbols.length === 0) {
      message.error("Select at least one symbol");
      return;
    }
    const task = await api.fetchBatchData({
      symbols: selectedSymbols,
      provider: values.provider,
      apiKey: values.apiKey,
      outputsize: values.outputsize,
      overwrite: Boolean(values.overwrite)
    });
    message.success(`Data fetch queued: ${task.id}`);
  }

  const missingSymbols = universe.data.components.filter((item) => !item.hasLocalData).map((item) => item.symbol);
  const selectedProvider = Form.useWatch("provider", form) ?? "yahoo";

  return (
    <Card title={compact ? "DJIA Data" : `Current DJIA Components (${universe.data.components.length})`}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`Universe as of ${universe.data.asOf || "loading"}: ${universe.data.source || "loading"}`}
      />
      <Form
        form={form}
        layout="vertical"
        onFinish={submit}
        initialValues={{ provider: "yahoo", outputsize: "compact", overwrite: false }}
      >
        <div className="field-grid">
          <Form.Item name="provider" label="Provider">
            <Select options={providers.data.map((provider) => ({ value: provider.key, label: provider.name }))} />
          </Form.Item>
          <Form.Item name="outputsize" label="Output Size">
            <Select disabled={selectedProvider !== "alpha_vantage"} options={[{ value: "compact" }, { value: "full" }]} />
          </Form.Item>
          {selectedProvider === "alpha_vantage" && (
            <Form.Item name="apiKey" label="API Key"><Input.Password placeholder="or ALPHAVANTAGE_API_KEY" /></Form.Item>
          )}
          <Form.Item name="overwrite" valuePropName="checked" label=" "><Checkbox>Overwrite local files</Checkbox></Form.Item>
        </div>
        <Space wrap style={{ marginBottom: 12 }}>
          <Button onClick={() => setSelectedSymbols(missingSymbols)}>Select Missing</Button>
          <Button onClick={() => setSelectedSymbols(universe.data.components.map((item) => item.symbol))}>Select All</Button>
          <Button onClick={() => setSelectedSymbols([])}>Clear</Button>
          <Button type="primary" htmlType="submit" icon={<CloudDownloadOutlined />}>Fetch Selected</Button>
        </Space>
      </Form>
      <Table
        rowKey="symbol"
        size="small"
        dataSource={universe.data.components}
        loading={universe.loading}
        pagination={compact ? { pageSize: 8 } : false}
        rowSelection={{
          selectedRowKeys: selectedSymbols,
          onChange: (keys) => setSelectedSymbols(keys.map(String))
        }}
        columns={[
          { title: "Symbol", dataIndex: "symbol", width: 90 },
          { title: "Company", dataIndex: "name", ellipsis: true },
          { title: "Sector", dataIndex: "sector", ellipsis: true },
          { title: "Local", dataIndex: "hasLocalData", width: 90, render: (value: boolean) => <Tag color={value ? "success" : "warning"}>{value ? "ready" : "missing"}</Tag> }
        ]}
      />
    </Card>
  );
}

function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const [selected, setSelected] = useState<Project>();
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [activeFile, setActiveFile] = useState<string>();
  const [content, setContent] = useState("");
  const [form] = Form.useForm();

  async function selectProject(project: Project) {
    setSelected(project);
    const tree = await api.projectFiles(project.id);
    setFiles(tree);
    const main = project.main_file;
    setActiveFile(main);
    setContent((await api.readProjectFile(project.id, main)).content);
  }

  async function createProject(values: { name: string; language: "Python" | "CSharp"; algorithmClass?: string }) {
    const project = await api.createProject(values);
    message.success("Project created");
    form.resetFields();
    await projects.reload();
    await selectProject(project);
  }

  async function createDjiaProject() {
    const project = await api.createProject({ name: "DJIA EMA Strategy", language: "Python", algorithmClass: "DjiaEmaAlgorithm" });
    message.success("DJIA project created");
    await projects.reload();
    navigate(`/workspace/${project.id}`);
  }

  async function openFile(path: string) {
    if (!selected) return;
    setActiveFile(path);
    setContent((await api.readProjectFile(selected.id, path)).content);
  }

  async function saveFile() {
    if (!selected || !activeFile) return;
    await api.writeProjectFile(selected.id, activeFile, content);
    message.success("Saved");
    projects.reload();
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Projects</h1>
        <Space>
          <Button icon={<FolderOpenOutlined />} onClick={createDjiaProject}>New DJIA Project</Button>
          <Button icon={<ReloadOutlined />} onClick={projects.reload}>Refresh</Button>
        </Space>
      </div>
      <div className="two-column wide-left">
        <Card title="Project List">
          <Form form={form} layout="vertical" onFinish={createProject} initialValues={{ language: "Python" }}>
            <Space.Compact style={{ width: "100%" }}>
              <Form.Item name="name" noStyle rules={[{ required: true }]}><Input placeholder="Project name" /></Form.Item>
              <Form.Item name="language" noStyle><Select style={{ width: 110 }} options={[{ value: "Python" }, { value: "CSharp" }]} /></Form.Item>
              <Button type="primary" htmlType="submit">Create</Button>
            </Space.Compact>
          </Form>
          <Table
            style={{ marginTop: 12 }}
            rowKey="id"
            size="small"
            dataSource={projects.data}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: "Name", dataIndex: "name" },
              { title: "Lang", dataIndex: "language" },
              { title: "Class", dataIndex: "algorithm_class", ellipsis: true },
              { title: "Open", render: (_, project) => <Space><a onClick={() => selectProject(project)}>Edit</a><a onClick={() => navigate(`/workspace/${project.id}`)}>Workspace</a></Space> }
            ]}
          />
        </Card>
        <Card title={selected ? `${selected.name} / ${activeFile ?? ""}` : "Editor"}>
          {!selected ? <Alert type="info" message="Create or select a project." /> : (
            <>
              <Space wrap style={{ marginBottom: 8 }}>
                {files.filter((item) => item.type === "file").map((file) => (
                  <Tag key={file.path} color={file.path === activeFile ? "blue" : "default"} onClick={() => openFile(file.path)}>{file.path}</Tag>
                ))}
              </Space>
              <Editor
                height="520px"
                language={activeFile?.endsWith(".cs") ? "csharp" : "python"}
                value={content}
                onChange={(value) => setContent(value ?? "")}
                theme="vs-dark"
              />
              <Button type="primary" style={{ marginTop: 12 }} icon={<CodeOutlined />} onClick={saveFile}>Save</Button>
            </>
          )}
        </Card>
      </div>
    </>
  );
}

function ProjectWorkspacePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const symbols = useAsyncData(api.symbols, { symbols: [], count: 0 });
  const runs = useAsyncData(api.backtests, []);
  const tasks = useAsyncData(api.tasks, []);
  const [selectedId, setSelectedId] = useState<string | undefined>(projectId);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [activeFile, setActiveFile] = useState<string>();
  const [content, setContent] = useState("");

  const project = projects.data.find((item) => item.id === selectedId);

  useEffect(() => {
    if (projectId) {
      setSelectedId(projectId);
    } else if (!selectedId && projects.data.length > 0) {
      setSelectedId(projects.data[0].id);
    }
  }, [projectId, projects.data, selectedId]);

  const loadProjectFile = useCallback(async (target: Project, path?: string) => {
    const tree = await api.projectFiles(target.id);
    setFiles(tree);
    const nextFile = path ?? target.main_file;
    setActiveFile(nextFile);
    setContent((await api.readProjectFile(target.id, nextFile)).content);
  }, []);

  useEffect(() => {
    if (project) {
      loadProjectFile(project).catch((error) => message.error((error as Error).message));
    }
  }, [project?.id, loadProjectFile]);

  async function saveFile() {
    if (!project || !activeFile) return;
    await api.writeProjectFile(project.id, activeFile, content);
    message.success("Saved");
  }

  async function submitBacktest(values: any) {
    if (!project) return;
    const run = await api.createBacktest({ ...values, projectId: project.id });
    message.success("Backtest queued");
    navigate(`/runs/${run.id}`);
  }

  const projectRuns = runs.data.filter((run) => run.project_id === project?.id);
  const projectTasks = tasks.data.filter((task) => task.project_id === project?.id);

  return (
    <>
      <div className="toolbar">
        <div>
          <h1 className="page-title">Project Workspace</h1>
          {project && <span className="muted">{project.name} / {project.algorithm_class}</span>}
        </div>
        <Space wrap>
          <Select
            style={{ width: 280 }}
            placeholder="Select project"
            value={selectedId}
            onChange={(value) => setSelectedId(value)}
            options={projects.data.map((item) => ({ value: item.id, label: item.name }))}
          />
          <Button icon={<ReloadOutlined />} onClick={() => { projects.reload(); symbols.reload(); runs.reload(); tasks.reload(); }}>Refresh</Button>
        </Space>
      </div>
      {!project ? <Alert type="info" message="Create or select a project first." /> : (
        <Tabs
          items={[
            {
              key: "overview",
              label: "Overview",
              children: (
                <div className="grid">
                  <Card><Statistic title="Backtests" value={projectRuns.length} /></Card>
                  <Card><Statistic title="Tasks" value={projectTasks.length} /></Card>
                  <Card><Statistic title="Language" value={project.language} /></Card>
                  <Card><Statistic title="Local Symbols" value={symbols.data.count} /></Card>
                </div>
              )
            },
            {
              key: "code",
              label: "Code",
              children: (
                <Card title={activeFile ?? project.main_file}>
                  <Space wrap style={{ marginBottom: 8 }}>
                    {files.filter((item) => item.type === "file").map((file) => (
                      <Tag key={file.path} color={file.path === activeFile ? "blue" : "default"} onClick={() => loadProjectFile(project, file.path)}>{file.path}</Tag>
                    ))}
                  </Space>
                  <Editor
                    height="540px"
                    language={activeFile?.endsWith(".cs") ? "csharp" : "python"}
                    value={content}
                    onChange={(value) => setContent(value ?? "")}
                    theme="vs-dark"
                  />
                  <Button type="primary" style={{ marginTop: 12 }} icon={<CodeOutlined />} onClick={saveFile}>Save</Button>
                </Card>
              )
            },
            {
              key: "data",
              label: "Data",
              children: <DjiaDataDownloader compact />
            },
            {
              key: "backtest",
              label: "Backtest",
              children: (
                <Card title="Run Backtest">
                  <Form layout="vertical" onFinish={submitBacktest} initialValues={{ symbol: "AAPL", start: "2018-01-01", end: "2024-12-31", fast: 10, slow: 30, cash: 100000, dockerImage: "quantconnect/lean:latest" }}>
                    <div className="field-grid six">
                      <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.data.symbols.map((symbol) => ({ value: symbol, label: symbol }))} /></Form.Item>
                      <Form.Item name="start" label="Start" rules={[{ required: true }]}><Input type="date" /></Form.Item>
                      <Form.Item name="end" label="End" rules={[{ required: true }]}><Input type="date" /></Form.Item>
                      <Form.Item name="fast" label="Fast"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="slow" label="Slow"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
                    </div>
                    <Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit">Run</Button>
                  </Form>
                </Card>
              )
            },
            {
              key: "results",
              label: "Results",
              children: <Card title="Project Backtests"><RunsTable runs={projectRuns} onOpen={(id) => navigate(`/runs/${id}`)} /></Card>
            },
            {
              key: "logs",
              label: "Logs",
              children: (
                <Card title="Project Tasks">
                  <Table<Task> rowKey="id" dataSource={projectTasks} size="small" columns={[
                    { title: "Kind", dataIndex: "kind" },
                    { title: "Title", dataIndex: "title" },
                    { title: "Status", dataIndex: "status", render: (status) => <StatusTag status={status} /> },
                    { title: "Created", dataIndex: "created_at" }
                  ]} />
                </Card>
              )
            }
          ]}
        />
      )}
    </>
  );
}

function DataPage() {
  const symbols = useAsyncData(api.symbols, { symbols: [], count: 0 });
  const assets = useAsyncData(api.dataAssets, []);
  const [csvForm] = Form.useForm();
  const [alphaForm] = Form.useForm();

  async function refresh() {
    await Promise.all([symbols.reload(), assets.reload()]);
  }

  async function importCsv(values: any) {
    const file = values.file?.fileList?.[0]?.originFileObj;
    if (!file) return message.error("请选择 CSV 文件");
    const formData = new FormData();
    ["symbol", "dateCol", "openCol", "highCol", "lowCol", "closeCol", "volumeCol"].forEach((key) => formData.append(key, values[key]));
    formData.append("overwrite", String(Boolean(values.overwrite)));
    formData.append("file", file);
    await api.importCsv(formData);
    message.success("CSV imported");
    csvForm.resetFields();
    refresh();
  }

  async function fetchAlpha(values: any) {
    await api.fetchAlphaVantage({ symbol: values.symbol, apiKey: values.apiKey, outputsize: values.outputsize, overwrite: Boolean(values.overwrite) });
    message.success("Alpha Vantage data imported");
    alphaForm.resetFields();
    refresh();
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Data</h1><Button icon={<ReloadOutlined />} onClick={refresh}>Refresh</Button></div>
      <Alert type="info" showIcon style={{ marginBottom: 16 }} message="US equity daily raw bars are supported in v1. For production research, use licensed data with corporate actions and delisting coverage." />
      <DjiaDataDownloader />
      <div className="two-column">
        <Card title="Import CSV">
          <Form form={csvForm} layout="vertical" onFinish={importCsv} initialValues={{ dateCol: "timestamp", openCol: "open", highCol: "high", lowCol: "low", closeCol: "close", volumeCol: "volume" }}>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Input placeholder="MSFT" /></Form.Item>
            <div className="field-grid">
              {["dateCol", "openCol", "highCol", "lowCol", "closeCol", "volumeCol"].map((name) => <Form.Item key={name} name={name} label={name}><Input /></Form.Item>)}
            </div>
            <Form.Item name="file" label="CSV" rules={[{ required: true }]}><Upload beforeUpload={() => false} maxCount={1}><Button>Choose CSV</Button></Upload></Form.Item>
            <Form.Item name="overwrite" valuePropName="checked"><Checkbox>Overwrite existing</Checkbox></Form.Item>
            <Button type="primary" htmlType="submit">Import</Button>
          </Form>
        </Card>
        <Card title="Fetch Alpha Vantage">
          <Form form={alphaForm} layout="vertical" onFinish={fetchAlpha} initialValues={{ outputsize: "compact" }}>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Input placeholder="IBM" /></Form.Item>
            <Form.Item name="apiKey" label="API Key"><Input.Password placeholder="or ALPHAVANTAGE_API_KEY" /></Form.Item>
            <Form.Item name="outputsize" label="Output Size"><Select options={[{ value: "compact" }, { value: "full" }]} /></Form.Item>
            <Form.Item name="overwrite" valuePropName="checked"><Checkbox>Overwrite existing</Checkbox></Form.Item>
            <Button type="primary" icon={<CloudDownloadOutlined />} htmlType="submit">Fetch</Button>
          </Form>
        </Card>
      </div>
      <div className="two-column wide-right">
        <Card title={`Local Symbols (${symbols.data.count})`}><div className="tag-list">{symbols.data.symbols.map((symbol) => <Tag key={symbol}>{symbol}</Tag>)}</div></Card>
        <Card title="Imported Assets">
          <Table<DataAsset> rowKey="id" size="small" dataSource={assets.data} columns={[
            { title: "Symbol", dataIndex: "symbol" }, { title: "Source", dataIndex: "source" }, { title: "Rows", dataIndex: "rows" },
            { title: "First", dataIndex: "first_date" }, { title: "Last", dataIndex: "last_date" }, { title: "File", dataIndex: "lean_file", ellipsis: true }
          ]} />
        </Card>
      </div>
    </>
  );
}

function BacktestsPage() {
  const navigate = useNavigate();
  const projects = useAsyncData(api.projects, []);
  const symbols = useAsyncData(api.symbols, { symbols: [], count: 0 });
  const runs = useAsyncData(api.backtests, []);
  async function submit(values: any) {
    const run = await api.createBacktest(values);
    message.success("Backtest queued");
    navigate(`/runs/${run.id}`);
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Backtests</h1><Button icon={<ReloadOutlined />} onClick={runs.reload}>Refresh</Button></div>
      <Card title="New Backtest">
        <Form layout="vertical" onFinish={submit} initialValues={{ symbol: "AAPL", start: "2018-01-01", end: "2024-12-31", fast: 10, slow: 30, cash: 100000, dockerImage: "quantconnect/lean:latest" }}>
          <div className="field-grid six">
            <Form.Item name="projectId" label="Project"><Select allowClear options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Select showSearch options={symbols.data.symbols.map((s) => ({ value: s, label: s }))} /></Form.Item>
            <Form.Item name="start" label="Start" rules={[{ required: true }]}><Input type="date" /></Form.Item>
            <Form.Item name="end" label="End" rules={[{ required: true }]}><Input type="date" /></Form.Item>
            <Form.Item name="fast" label="Fast"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="slow" label="Slow"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="cash" label="Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="dockerImage" label="Image"><Input /></Form.Item>
          </div>
          <Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit">Run</Button>
        </Form>
      </Card>
      <Card title="History" style={{ marginTop: 16 }}><RunsTable runs={runs.data} onOpen={(id) => navigate(`/runs/${id}`)} /></Card>
    </>
  );
}

function RunDetailPage() {
  const { id } = useParams();
  const [run, setRun] = useState<BacktestRun>();
  const [chart, setChart] = useState<ChartData>();
  const [logs, setLogs] = useState("");
  const active = run?.status === "queued" || run?.status === "running";
  const reload = useCallback(async () => {
    if (!id) return;
    const next = await api.backtest(id);
    setRun(next);
    setLogs((await api.logs(id)).logs);
    if (next.result_json_path) setChart(await api.chartData(id));
  }, [id]);
  useEffect(() => { reload(); }, [reload]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(reload, 1000);
    return () => window.clearInterval(timer);
  }, [active, reload]);
  if (!run) return <Alert type="info" message="Loading run..." />;
  return (
    <>
      <div className="toolbar"><h1 className="page-title">{run.id}</h1><Space><StatusTag status={run.status} /><Button onClick={reload} icon={<ReloadOutlined />}>Refresh</Button></Space></div>
      {run.error && <Alert type="error" showIcon message={run.error} style={{ marginBottom: 16 }} />}
      <div className="grid">
        {["End Equity", "Net Profit", "Sharpe Ratio", "Drawdown"].map((key) => <Card key={key}><Statistic title={key} value={run.statistics?.[key] ?? "N/A"} /></Card>)}
      </div>
      <Card title="Parameters"><Space wrap>{Object.entries(run.parameters).map(([key, value]) => <Tag key={key}>{key}: {String(value)}</Tag>)}</Space></Card>
      {chart && <BacktestCharts chartData={chart} />}
      <Card title="Artifacts" style={{ marginTop: 16 }}>{(run.artifacts ?? []).map((name) => <a className="artifact-link" key={name} target="_blank" href={`/api/backtests/${run.id}/artifacts/${name}`}>{name}</a>)}</Card>
      <Card title="Logs" style={{ marginTop: 16 }}><pre className="log-view">{logs || "No logs yet."}</pre></Card>
    </>
  );
}

function OptimizationPage() {
  const projects = useAsyncData(api.projects, []);
  const optimizations = useAsyncData(api.optimizations, []);
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
        <Form layout="vertical" onFinish={submit} initialValues={{ symbol: "AAPL", start: "2018-01-01", end: "2024-12-31", cash: 100000, fastValues: "5,10,15", slowValues: "20,30,50", dockerImage: "quantconnect/lean:latest" }}>
          <div className="field-grid">
            <Form.Item name="projectId" label="Project" rules={[{ required: true }]}><Select options={projects.data.map((p) => ({ value: p.id, label: p.name }))} /></Form.Item>
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
        <Table<OptimizationRun> rowKey="id" dataSource={optimizations.data} size="small" columns={[
          { title: "ID", dataIndex: "id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> }, { title: "Created", dataIndex: "created_at" }
        ]} />
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
        <Table<ResearchSession> rowKey="id" dataSource={sessions.data} size="small" columns={[
          { title: "ID", dataIndex: "id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
          { title: "URL", render: (_, s) => s.url ? <a href={s.url} target="_blank">{s.url}</a> : "-" },
          { title: "Action", render: (_, s) => <Button size="small" onClick={() => api.stopResearch(s.id).then(sessions.reload)}>Stop</Button> }
        ]} />
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
        <Table<ReportRecord> rowKey="id" dataSource={reports.data} size="small" columns={[
          { title: "ID", dataIndex: "id", ellipsis: true }, { title: "Run", dataIndex: "run_id", ellipsis: true }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
          { title: "Open", render: (_, r) => r.report_path ? <a href={`/api/reports/${r.id}/file`} target="_blank">HTML</a> : "-" }
        ]} />
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
        <Table<ObjectStoreItem> rowKey="key" dataSource={items.data} size="small" columns={[
          { title: "Key", dataIndex: "key" }, { title: "Size", dataIndex: "size" }, { title: "Updated", dataIndex: "updated_at" },
          { title: "Actions", render: (_, item) => <Space><a href={`/api/object-store/${item.key}`} target="_blank">Download</a><a onClick={() => api.deleteObjectStoreItem(item.key).then(items.reload)}>Delete</a></Space> }
        ]} />
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
        <Table<Task> rowKey="id" dataSource={tasks.data} size="small" columns={[
          { title: "Kind", dataIndex: "kind" }, { title: "Title", dataIndex: "title" }, { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
          { title: "Created", dataIndex: "created_at" }, { title: "Open", render: (_, task) => <a onClick={() => open(task)}>Logs</a> }
        ]} />
      </Card>
      {selected && <Card title={`${selected.kind} / ${selected.id}`} style={{ marginTop: 16 }}><pre className="log-view">{logs}</pre></Card>}
    </>
  );
}

function AppShell() {
  const menuItems = [
    { key: "/", icon: <AppstoreOutlined />, label: <Link to="/">Dashboard</Link> },
    { key: "/capabilities", icon: <ToolOutlined />, label: <Link to="/capabilities">Capabilities</Link> },
    { key: "/workspace", icon: <CodeOutlined />, label: <Link to="/workspace">Workspace</Link> },
    { key: "/projects", icon: <FolderOpenOutlined />, label: <Link to="/projects">Projects</Link> },
    { key: "/data", icon: <DatabaseOutlined />, label: <Link to="/data">Data</Link> },
    { key: "/backtests", icon: <PlayCircleOutlined />, label: <Link to="/backtests">Backtests</Link> },
    { key: "/optimization", icon: <SlidersOutlined />, label: <Link to="/optimization">Optimization</Link> },
    { key: "/research", icon: <ExperimentOutlined />, label: <Link to="/research">Research</Link> },
    { key: "/reports", icon: <FileTextOutlined />, label: <Link to="/reports">Reports</Link> },
    { key: "/object-store", icon: <DatabaseOutlined />, label: <Link to="/object-store">Object Store</Link> },
    { key: "/tasks", icon: <UnorderedListOutlined />, label: <Link to="/tasks">Tasks</Link> }
  ];
  return (
    <Layout className="app-layout">
      <Sider breakpoint="lg" collapsedWidth="0"><div className="app-logo">LEAN Local</div><Menu theme="dark" mode="inline" items={menuItems} /></Sider>
      <Layout>
        <Header className="app-header"><Space><strong>QuantConnect LEAN Local Workbench</strong><Tag color="blue">docker</Tag></Space></Header>
        <Content className="app-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/capabilities" element={<CapabilitiesPage />} />
            <Route path="/workspace" element={<ProjectWorkspacePage />} />
            <Route path="/workspace/:projectId" element={<ProjectWorkspacePage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/data" element={<DataPage />} />
            <Route path="/backtests" element={<BacktestsPage />} />
            <Route path="/runs/:id" element={<RunDetailPage />} />
            <Route path="/optimization" element={<OptimizationPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/object-store" element={<ObjectStorePage />} />
            <Route path="/tasks" element={<TasksPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return <HashRouter><AppShell /></HashRouter>;
}
