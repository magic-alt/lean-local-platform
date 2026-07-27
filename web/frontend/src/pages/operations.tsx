import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
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
  OptimizationRun,
  PaperBacktestCandidate,
  Project,
  ProjectFile,
  ReportRecord,
  ResearchSession,
  StrategyTemplate,
  Task,
  Universe,
  WorkflowSummary
} from "../api";
import { BacktestCharts, RunsTable, StatusTag } from "../components";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { BacktestTrustPanel, ValidationStatusTag } from "../components/backtests/BacktestTrustPanel";
import { AdvancedFields, FormActions, FormGrid, FormSection } from "../components/forms/FormLayout";
import { candlestickOption } from "../charts/candlestick";
import { defaultBarPreviewValues, defaultSettings } from "../config/defaults";
import { useAsyncData } from "../hooks";
import { detailText, shortValue } from "../utils/display";
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

const loadFailedWorkflows = () => api.workflows("failed", 50);

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
      <Alert
        type="info"
        showIcon
        message="Structured market insights are available in the Insights workspace."
        action={<Button size="small" href="#/insights">Open Insights</Button>}
        style={{ marginBottom: 16 }}
      />
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
            {
              title: "Report",
              render: (_, report) => <div className="table-primary-cell">
                <strong>{report.source === "backtest_run" ? "Backtest report" : "Generated report"}</strong>
                <span className="muted copyable-id">{report.id}</span>
              </div>
            },
            { title: "Run", dataIndex: "run_id" },
            { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
            { title: "Trust", render: (_, report) => <ValidationStatusTag validation={report.validation ?? report.result?.performance?.validation} /> },
            { title: "Benchmark", dataIndex: "benchmark", render: (value) => shortValue(value) },
            {
              title: "Export",
              render: (_, report) => (
                <Tooltip title="点击在新页面预览；右键可将链接另存为文件">
                  <Space>
                    <a href={api.reportExportUrl(report.id, "html")} target="_blank" rel="noreferrer">HTML</a>
                    <a href={api.reportExportUrl(report.id, "markdown")} target="_blank" rel="noreferrer">MD</a>
                    <a href={api.reportExportUrl(report.id, "pdf")} target="_blank" rel="noreferrer">PDF</a>
                    <a href={api.reportExportUrl(report.id, "csv")} target="_blank" rel="noreferrer">CSV</a>
                    <a href={api.reportExportUrl(report.id, "json")} target="_blank" rel="noreferrer">JSON</a>
                  </Space>
                </Tooltip>
              )
            },
            {
              title: "Actions",
              render: (_, report) => report.source === "generated_report" ? (
                <Popconfirm
                  title="Delete this generated report?"
                  description="The report record and managed report file will be removed. The source backtest remains."
                  okText="Delete"
                  okButtonProps={{ danger: true }}
                  disabled={["created", "queued", "running"].includes(report.status)}
                  onConfirm={async () => {
                    try {
                      await api.deleteReport(report.id);
                      message.success("Report deleted");
                      await reports.reload();
                    } catch (error) {
                      message.error((error as Error).message);
                    }
                  }}
                >
                  <Button size="small" danger disabled={["created", "queued", "running"].includes(report.status)}>Delete</Button>
                </Popconfirm>
              ) : <Tooltip title="Delete this item from Backtests; its report is part of the run."><span className="muted">Managed by backtest</span></Tooltip>
            }
          ]}
        />
      </Card>
    </>
  );
}

export function TasksPage() {
  const tasks = useAsyncData(api.tasks, []);
  const [selected, setSelected] = useState<Task>();
  const [logs, setLogs] = useState("");
  const [deletingTaskId, setDeletingTaskId] = useState<string>();

  async function open(task: Task) {
    setSelected(task);
    setLogs((await api.taskLogs(task.id)).logs);
  }
  async function remove(task: Task) {
    setDeletingTaskId(task.id);
    try {
      await api.deleteTask(task.id);
      message.success("Task deleted");
      if (selected?.id === task.id) {
        setSelected(undefined);
        setLogs("");
      }
      tasks.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDeletingTaskId(undefined);
    }
  }
  return (
    <>
      <div className="toolbar"><h1 className="page-title">Tasks</h1><Button icon={<ReloadOutlined />} onClick={tasks.reload}>Refresh</Button></div>
      <Card title="Queue">
        <Table<Task> rowKey="id" dataSource={tasks.data} size="small" columns={[
          { title: "Kind", dataIndex: "kind" },
          { title: "Title", dataIndex: "title" },
          { title: "Status", dataIndex: "status", render: (s) => <StatusTag status={s} /> },
          { title: "Created", dataIndex: "created_at" },
          {
            title: "Actions",
            render: (_, task) => (
              <Space>
                <a onClick={() => open(task)}>Logs</a>
                <Popconfirm
                  title="Delete task?"
                  description="Only terminal tasks can be deleted. Cancel active work first."
                  okText="Delete"
                  okButtonProps={{ danger: true, loading: deletingTaskId === task.id }}
                  disabled={["created", "queued", "running"].includes(task.status)}
                  onConfirm={() => remove(task)}
                >
                  <Button size="small" danger disabled={["created", "queued", "running"].includes(task.status)} loading={deletingTaskId === task.id}>Delete</Button>
                </Popconfirm>
              </Space>
            )
          }
        ]} />
      </Card>
      {selected && <Card title={`${selected.kind} / ${selected.id}`} style={{ marginTop: 16 }}><pre className="log-view">{logs}</pre></Card>}
    </>
  );
}

export function MonitoringPage() {
  const health = useAsyncData<DependencyHealth>(api.dependencyHealth, {
    status: "ok",
    executionStatus: "ok",
    dependencies: [],
    urls: {
      prometheus: "http://127.0.0.1:9090",
      grafana: "http://127.0.0.1:3000"
    }
  });
  const up = health.data.dependencies.filter((item) => item.ok).length;
  const down = Math.max(0, health.data.dependencies.length - up);
  const workflowFailures = useAsyncData<WorkflowSummary[]>(loadFailedWorkflows, []);
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
      <Card title="Recent Workflow Failures" style={{ marginTop: 16 }}>
        <Table<WorkflowSummary>
          data-testid="workflow-failures-table"
          rowKey="workflow_id"
          size="small"
          loading={workflowFailures.loading}
          dataSource={workflowFailures.data}
          columns={[
            { title: "Workflow", dataIndex: "workflow_id", ellipsis: true },
            { title: "Events", dataIndex: "event_count" },
            { title: "Failures", dataIndex: "failure_count" },
            { title: "Updated", dataIndex: "updated_at" }
          ]}
        />
      </Card>
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
          <FormSection title="Market defaults">
          <FormGrid>
            <Form.Item name="defaultAssetClass" label="Default Asset"><Select options={assetClasses.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultMarket" label="Default Market"><Select options={markets.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultVenue" label="Default Venue"><Select options={(selectedAssetInfo?.venues ?? ["usa"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultResolution" label="Default Resolution"><Select options={["daily", "hour", "minute", "second", "tick"].map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultDataType" label="Default Data Type"><Select options={(selectedAssetInfo?.dataTypes ?? ["trade"]).map((value) => ({ value, label: value }))} /></Form.Item>
            <Form.Item name="defaultProvider" label="Default Provider"><Select options={providers.data.map((item) => ({ value: item.key, label: item.disabledByDefault || item.enabledByDefault === false ? `${item.name} (disabled)` : item.name, disabled: item.disabledByDefault || item.enabledByDefault === false }))} /></Form.Item>
            <Form.Item name="defaultAdjust" label="Default Adjust"><Select options={[{ value: "", label: "Raw" }, { value: "qfq", label: "QFQ" }, { value: "hfq", label: "HFQ" }]} /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormSection title="Backtest defaults">
          <FormGrid>
            <Form.Item name="defaultStrategyTemplate" label="Default Strategy"><Select options={templates.data.map((item) => ({ value: item.key, label: item.name }))} /></Form.Item>
            <Form.Item name="defaultStart" label="Default Start"><DateStringPicker /></Form.Item>
            <Form.Item name="defaultEnd" label="Default End"><DateStringPicker /></Form.Item>
            <Form.Item name="defaultCash" label="Default Cash"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="chartPointLimit" label="Chart Point Limit"><InputNumber min={1000} style={{ width: "100%" }} /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormSection title="Task capacity">
          <FormGrid>
            <Form.Item name="maxConcurrentJobs" label="Max Concurrent Jobs"><InputNumber min={1} max={8} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="maxBatchRuns" label="Max Batch Runs"><InputNumber min={1} max={50000} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="jobTimeoutSeconds" label="Job Timeout Seconds"><InputNumber min={60} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="logLevel" label="Log Level"><Select options={["DEBUG", "INFO", "WARNING", "ERROR"].map((value) => ({ value, label: value }))} /></Form.Item>
          </FormGrid>
          </FormSection>
          <AdvancedFields label="Runtime environment">
            <FormGrid>
              <Form.Item className="form-field--wide" name="dockerImage" label="Docker Image"><Input /></Form.Item>
              <Form.Item className="form-field--wide" name="researchImage" label="Research Image"><Input /></Form.Item>
            </FormGrid>
          </AdvancedFields>
          <FormActions><Button type="primary" htmlType="submit">Save Settings</Button></FormActions>
        </Form>
      </Card>
    </>
  );
}
