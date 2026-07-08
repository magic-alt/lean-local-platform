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
  Universe
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

export function PaperPage() {
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
  const [reportSession, setReportSession] = useState<PaperSession | null>(null);
  const [paperReports, setPaperReports] = useState<PaperDailyReport[]>([]);
  const [paperReportsLoading, setPaperReportsLoading] = useState(false);

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

  async function loadReports(session: PaperSession) {
    setReportSession(session);
    setPaperReportsLoading(true);
    try {
      setPaperReports(await api.paperReports(session.id));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setPaperReportsLoading(false);
    }
  }

  return (
    <>
      <div className="toolbar"><h1 className="page-title">Paper Replay</h1><Button icon={<ReloadOutlined />} onClick={sessions.reload}>Refresh</Button></div>
      <Alert style={{ marginBottom: 16 }} type="info" showIcon message="Paper Replay is a local simulated session registry. It does not connect to brokers or place real orders." />
      <Card title="Create Paper Session">
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{ assetClass: "equity", market: "usa", venue: "usa", resolution: "daily", dataType: "trade", cash: 100000, executionPolicy: "next_open", benchmarkSymbol: "000300", maxPositions: 10, maxPositionWeight: 0.2, minCash: 0, allowStBuy: false }}>
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
            <Form.Item name="executionPolicy" label="Execution"><Select options={[{ value: "next_open", label: "Next Open" }, { value: "next_close", label: "Next Close" }, { value: "next_vwap", label: "Next VWAP" }]} /></Form.Item>
            <Form.Item name="benchmarkSymbol" label="Benchmark"><Input /></Form.Item>
            <Form.Item name="maxPositions" label="Max Positions"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="maxPositionWeight" label="Max Weight"><InputNumber min={0} max={1} step={0.05} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="minCash" label="Min Cash"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="blacklist" label="Blacklist"><Input /></Form.Item>
            <Form.Item name="watchlist" label="Watchlist"><Input /></Form.Item>
            <Form.Item name="observeOnlySymbols" label="Observe Only"><Input /></Form.Item>
            <Form.Item name="allowStBuy" valuePropName="checked"><Checkbox>Allow ST Buy</Checkbox></Form.Item>
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
            { title: "Actions", render: (_, session) => <Space><Button size="small" onClick={() => status(session, "running")}>Run</Button><Button size="small" onClick={() => status(session, "paused")}>Pause</Button><Button size="small" danger onClick={() => status(session, "stopped")}>Stop</Button><Button size="small" onClick={() => loadReports(session)}>Reports</Button></Space> }
          ]}
        />
      </Card>
      {reportSession && (
        <Card title={`Daily Reports - ${reportSession.name}`} style={{ marginTop: 16 }} extra={<Button icon={<ReloadOutlined />} onClick={() => loadReports(reportSession)}>Refresh</Button>}>
          <Table<PaperDailyReport>
            rowKey="id"
            dataSource={paperReports}
            loading={paperReportsLoading}
            size="small"
            columns={[
              { title: "Date", render: (_, report) => report.tradeDate || report.trade_date },
              { title: "Execution", dataIndex: "executionPolicy" },
              { title: "NAV", dataIndex: "NAV" },
              { title: "Cash", dataIndex: "cash" },
              { title: "Benchmark", render: (_, report) => report.benchmark?.symbol ? `${report.benchmark.symbol} ${report.benchmark.close ?? "-"}` : "-" },
              { title: "Excess", dataIndex: "excessReturn" },
              { title: "QA", render: (_, report) => <Tag color={report.qa?.passed === false ? "red" : "green"}>{report.qa?.severity || "ok"}</Tag> },
              { title: "Rejects", render: (_, report) => (report.rejectionReasons || []).join(", ") || "-" },
              { title: "Warnings", render: (_, report) => (report.warnings || []).join(", ") || "-" },
              { title: "Fingerprint", render: (_, report) => report.fingerprint ? report.fingerprint.slice(0, 12) : "-" }
            ]}
          />
        </Card>
      )}
    </>
  );
}

export function ReportsPage() {
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
        <Table<ReportRecord>
          rowKey="id"
          dataSource={reports.data}
          size="small"
          columns={[
            { title: "ID", dataIndex: "id", ellipsis: true },
            { title: "Source", dataIndex: "source", render: (value) => value || "reports" },
            { title: "Run", dataIndex: "run_id", ellipsis: true },
            { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
            { title: "Trust", render: (_, report) => <ValidationStatusTag validation={report.validation ?? report.result?.performance?.validation} /> },
            { title: "Benchmark", render: (_, report) => shortValue(asRecord(asRecord(report.validation?.data).benchmark).symbol) },
            { title: "Result", render: (_, report) => report.result_json_path || report.raw_result_object_id ? "available" : "-" },
            { title: "Objects", render: (_, report) => report.storedObjects?.length || 0 },
            {
              title: "Export",
              render: (_, report) => (
                <Space>
                  <a href={api.reportExportUrl(report.id, "html")} target="_blank">HTML</a>
                  <a href={api.reportExportUrl(report.id, "pdf")} target="_blank">PDF</a>
                  <a href={api.reportExportUrl(report.id, "markdown")} target="_blank">MD</a>
                  <a href={api.reportExportUrl(report.id, "csv")} target="_blank">CSV</a>
                  <a href={api.reportExportUrl(report.id, "json")} target="_blank">JSON</a>
                </Space>
              )
            }
          ]}
        />
      </Card>
    </>
  );
}

export function ObjectStorePage() {
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

export function TasksPage() {
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

export function MonitoringPage() {
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
          <Button data-testid="check-system-status-button" icon={<ReloadOutlined />} onClick={health.reload}>Check System Status</Button>
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
          data-testid="dependency-health-table"
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
                <Tooltip title={detailText(item.detail)}>
                  <Tag color={ok ? "success" : "error"}>{ok ? "up" : "down"}</Tag>
                </Tooltip>
              )
            },
            { title: "Latency", dataIndex: "latency_ms", render: (value) => value === undefined ? "-" : `${value} ms` },
            { title: "Detail", dataIndex: "detail", ellipsis: true, render: detailText }
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

export function SettingsPage() {
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
