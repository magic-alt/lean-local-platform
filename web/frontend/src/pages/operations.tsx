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
  OptimizationRun,
  PaperDailyReport,
  PaperBacktestCandidate,
  PaperSession,
  PaperWalkforwardRun,
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

export function PaperPage() {
  const sessions = useAsyncData(api.paperSessions, []);
  const projects = useAsyncData(api.projects, []);
  const [form] = Form.useForm();
  const projectId = Form.useWatch("projectId", form);
  const sourceBacktestId = Form.useWatch("sourceBacktestId", form);
  const paperMode = Form.useWatch("mode", form) || "lean_walkforward";
  const [candidates, setCandidates] = useState<PaperBacktestCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selectedSession, setSelectedSession] = useState<PaperSession | null>(null);
  const [paperReports, setPaperReports] = useState<PaperDailyReport[]>([]);
  const [paperRuns, setPaperRuns] = useState<PaperWalkforwardRun[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [runDate, setRunDate] = useState("");

  useEffect(() => {
    if (paperMode !== "lean_walkforward") {
      setCandidates([]);
      return;
    }
    if (!projectId) {
      setCandidates([]);
      form.setFieldValue("sourceBacktestId", undefined);
      return;
    }
    let active = true;
    setCandidatesLoading(true);
    api.paperCandidates(projectId)
      .then((items) => {
        if (active) setCandidates(items);
      })
      .catch((error) => {
        if (active) message.error((error as Error).message);
      })
      .finally(() => {
        if (active) setCandidatesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [form, paperMode, projectId]);

  async function submit(values: any) {
    if (creating) return;
    setCreating(true);
    try {
      await api.createPaperSession({
        mode: values.mode,
        name: values.name,
        projectId: values.mode === "lean_walkforward" ? values.projectId : undefined,
        sourceBacktestId: values.mode === "lean_walkforward" ? values.sourceBacktestId : undefined,
        symbol: values.mode === "lean_walkforward"
          ? candidates.find((item) => item.id === values.sourceBacktestId)?.symbol || ""
          : values.symbol,
        market: values.market,
        venue: values.market,
        cash: values.cash,
        resolution: "daily",
        startDate: values.startDate || undefined,
        autoAdvance: values.autoAdvance !== false,
        parameters: { source: "tushare" }
      });
      message.success(values.mode === "lean_walkforward"
        ? "LEAN Paper session created from the frozen backtest snapshot"
        : "Signal simulation session created");
      form.resetFields();
      setCandidates([]);
      await sessions.reload();
    } catch (error) {
      message.error(`创建 Paper 失败：${(error as Error).message}`);
    } finally {
      setCreating(false);
    }
  }

  async function status(session: PaperSession, nextStatus: string) {
    await api.updatePaperSessionStatus(session.id, nextStatus);
    await sessions.reload();
  }

  async function loadDetail(session: PaperSession) {
    setSelectedSession(session);
    setRunDate(session.next_trade_date || session.start_date || "");
    setDetailLoading(true);
    try {
      const [detail, reports, runs] = await Promise.all([
        api.paperSession(session.id),
        api.paperReports(session.id),
        session.mode === "lean_walkforward" ? api.paperRuns(session.id) : Promise.resolve([])
      ]);
      setSelectedSession(detail);
      setRunDate(detail.next_trade_date || detail.start_date || "");
      setPaperReports(reports);
      setPaperRuns(runs);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDetailLoading(false);
    }
  }

  async function runDay() {
    if (!selectedSession || !runDate) return;
    const isSimulation = selectedSession.mode === "signal_simulation";
    await api.runPaperDay(selectedSession.id, runDate, isSimulation);
    message.success(isSimulation ? `Signal simulation ${runDate} 已完成` : `LEAN Paper ${runDate} 已进入执行队列`);
    await Promise.all([sessions.reload(), loadDetail(selectedSession)]);
  }

  const selectedCandidate = candidates.find((item) => item.id === sourceBacktestId);
  const equityPoints = paperReports
    .map((item) => [item.tradeDate || item.trade_date, item.NAV])
    .filter((item) => item[0] && typeof item[1] === "number");

  return (
    <>
      <div className="toolbar"><h1 className="page-title">LEAN Paper</h1><Button icon={<ReloadOutlined />} onClick={sessions.reload}>Refresh</Button></div>
      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="Projects 管理策略源码；Backtests 验证一个冻结版本；LEAN Paper 每个交易日用同一冻结版本运行到当日。"
        description="LEAN Walk-forward 支持 A 股与港股日线冻结策略；Signal Simulation 用统一本地行情快速验证信号。两者都不是实时行情或券商委托。"
      />
      <Card title="Create Paper Session">
        <Form
          form={form}
          layout="vertical"
          onFinish={submit}
          onFinishFailed={() => message.warning("请先选择 Project 和验证通过的 Backtest")}
          initialValues={{ autoAdvance: true, mode: "lean_walkforward", market: "china", cash: 100000 }}
        >
          <FormSection title="Session setup">
          <FormGrid>
            <Form.Item name="mode" label="Mode" rules={[{ required: true }]}>
              <Select options={[
                { value: "lean_walkforward", label: "LEAN Walk-forward" },
                { value: "signal_simulation", label: "Signal Simulation" }
              ]} />
            </Form.Item>
            <Form.Item className="form-field--wide" name="name" label="Name"><Input placeholder="600460 MACD daily paper" /></Form.Item>
            {paperMode === "lean_walkforward" ? <>
              <Form.Item className="form-field--wide" name="projectId" label="Project" rules={[{ required: true }]}>
                <Select allowClear options={projects.data.map((project) => ({ value: project.id, label: project.display_name || project.name }))} />
              </Form.Item>
              <Form.Item className="form-field--wide" name="sourceBacktestId" label="Trusted Backtest" rules={[{ required: true }]}>
                <Select
                  loading={candidatesLoading}
                  disabled={!projectId}
                  placeholder={projectId ? "Select a validation-passed run" : "Select Project first"}
                  options={candidates.map((item) => ({
                    value: item.id,
                    label: `${item.name || item.symbol} · ${item.start} → ${item.end}`
                  }))}
                />
              </Form.Item>
            </> : <>
              <Form.Item name="market" label="Market" rules={[{ required: true }]}>
                <Select options={[{ value: "china", label: "China A-share" }, { value: "hongkong", label: "Hong Kong" }]} />
              </Form.Item>
              <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><Input placeholder="600460 / 00700" /></Form.Item>
              <Form.Item name="cash" label="Initial Cash" rules={[{ required: true }]}><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
            </>}
            <Form.Item name="startDate" label="First Paper Date">
              <DateStringPicker placeholder="Default: next trading day after backtest" />
            </Form.Item>
            <Form.Item name="autoAdvance" valuePropName="checked"><Checkbox>工作日收盘后自动推进</Checkbox></Form.Item>
          </FormGrid>
          </FormSection>
          {paperMode === "lean_walkforward" && projectId && !candidatesLoading && candidates.length === 0 && (
            <Alert
              type="warning"
              showIcon
              message="该 Project 暂无可用于 Paper 的 Backtest。"
              description="需要状态成功、执行验证通过、数据未截断、结果账本存在，并保留冻结策略快照。"
              style={{ marginBottom: 16 }}
            />
          )}
          {selectedCandidate && (
            <Alert
              type="success"
              showIcon
              message={`冻结 ${selectedCandidate.symbol} · ${selectedCandidate.start} → ${selectedCandidate.end} · ¥${selectedCandidate.cash}`}
              description={`Strategy version: ${selectedCandidate.strategyVersionId || "-"} · Parameter fingerprint: ${(selectedCandidate.parameterHash || "-").slice(0, 16)} · Admission: ${selectedCandidate.admissionStage || "not registered（仅警告）"}`}
              style={{ marginBottom: 16 }}
            />
          )}
          <FormActions><Button data-testid="create-paper-button" type="primary" htmlType="submit" loading={creating} disabled={creating || (paperMode === "lean_walkforward" && (candidatesLoading || !selectedCandidate))}>Create</Button></FormActions>
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
            { title: "Mode", render: (_, session) => session.mode === "lean_walkforward" ? <Tag color="blue">LEAN Walk-forward</Tag> : session.mode === "signal_simulation" ? <Tag color="green">Signal Simulation</Tag> : <Tag>Legacy / 只读</Tag> },
            { title: "Last Date", dataIndex: "last_processed_date", render: (value) => value || "-" },
            { title: "Status", dataIndex: "status", render: (value) => <StatusTag status={value} /> },
            { title: "Equity", dataIndex: "equity" },
            { title: "Created", dataIndex: "created_at" },
            { title: "Actions", render: (_, session) => <Space>
              {!session.legacy_read_only && <Button size="small" onClick={() => status(session, "running")}>Enable</Button>}
              {!session.legacy_read_only && <Button size="small" onClick={() => status(session, "paused")}>Pause</Button>}
              {!session.legacy_read_only && <Button size="small" danger onClick={() => status(session, "stopped")}>Stop</Button>}
              <Button size="small" onClick={() => loadDetail(session)}>Details</Button>
              <Popconfirm
                title="Delete this Paper session?"
                description="Signals, orders, positions, snapshots, daily reports and walk-forward runs will be removed."
                okText="Delete"
                okButtonProps={{ danger: true }}
                disabled={["created", "queued", "running"].includes(session.status)}
                onConfirm={async () => {
                  try {
                    await api.deletePaperSession(session.id);
                    if (selectedSession?.id === session.id) setSelectedSession(null);
                    message.success("Paper session deleted");
                    await sessions.reload();
                  } catch (error) {
                    message.error((error as Error).message);
                  }
                }}
              >
                <Button size="small" danger disabled={["created", "queued", "running"].includes(session.status)}>Delete</Button>
              </Popconfirm>
            </Space> }
          ]}
        />
      </Card>
      {selectedSession && (
        <Card title={`${selectedSession.name} · ${selectedSession.mode === "lean_walkforward" ? "LEAN Paper" : selectedSession.mode === "signal_simulation" ? "Signal Simulation" : "Legacy Replay"}`} loading={detailLoading} style={{ marginTop: 16 }} extra={<Button icon={<ReloadOutlined />} onClick={() => loadDetail(selectedSession)}>Refresh</Button>}>
          {selectedSession.failure && <Alert type="error" showIcon message={selectedSession.failure.code || "Paper failed"} description={selectedSession.failure.message} style={{ marginBottom: 16 }} />}
          {selectedSession.mode === "lean_walkforward" && !selectedSession.legacy_read_only && (
            <Space style={{ marginBottom: 16 }}>
              <Input value={runDate} onChange={(event) => setRunDate(event.target.value)} placeholder="YYYY-MM-DD next eligible trading date" style={{ width: 260 }} />
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={runDay}>Run Trading Day</Button>
              <Tag>source {selectedSession.source_backtest_id}</Tag>
              <Tag>strategy {(selectedSession.strategy_version_id || "-").slice(0, 12)}</Tag>
            </Space>
          )}
          {selectedSession.mode === "signal_simulation" && !selectedSession.legacy_read_only && (
            <Space style={{ marginBottom: 16 }}>
              <Input value={runDate} onChange={(event) => setRunDate(event.target.value)} placeholder="YYYY-MM-DD trading date" style={{ width: 260 }} />
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={runDay}>Simulate Trading Day</Button>
            </Space>
          )}
          {equityPoints.length > 0 && <ReactECharts style={{ height: 280 }} option={{
            tooltip: { trigger: "axis" },
            xAxis: { type: "category", data: equityPoints.map((item) => item[0]) },
            yAxis: { type: "value", scale: true },
            series: [{ name: "Equity", type: "line", showSymbol: false, data: equityPoints.map((item) => item[1]) }]
          }} />}
          <Tabs items={[
            {
              key: "runs",
              label: "Daily Runs",
              children: <Table<PaperWalkforwardRun> rowKey="id" size="small" dataSource={paperRuns} columns={[
                { title: "Date", dataIndex: "trade_date" },
                { title: "Status", dataIndex: "status", render: (value) => <StatusTag status={value} /> },
                { title: "Backtest", dataIndex: "backtest_run_id", render: (value) => value || "-" },
                { title: "Reconciliation", render: (_, item) => item.reconciliation ? <Tag color={item.reconciliation.passed ? "green" : "red"}>{item.reconciliation.passed ? "pass" : "failed"}</Tag> : "-" },
                { title: "Fingerprint", render: (_, item) => item.order_fingerprint?.slice(0, 12) || "-" },
                { title: "Error", render: (_, item) => item.failure?.message || "-" }
              ]} />
            },
            {
              key: "reports",
              label: "Daily Reports",
              children: <Table<PaperDailyReport> rowKey="id" dataSource={paperReports} size="small" columns={[
                { title: "Date", render: (_, report) => report.tradeDate || report.trade_date },
                { title: "NAV", dataIndex: "NAV" },
                { title: "QA", render: (_, report) => <Tag color={report.qa?.passed === false ? "red" : "green"}>{report.qa?.severity || "ok"}</Tag> },
                { title: "Fingerprint", render: (_, report) => report.fingerprint?.slice(0, 12) || "-" }
              ]} />
            },
            {
              key: "orders",
              label: `Orders (${selectedSession.orders?.length || 0})`,
              children: <pre style={{ maxHeight: 420, overflow: "auto" }}>{JSON.stringify(selectedSession.orders || [], null, 2)}</pre>
            },
            {
              key: "positions",
              label: `Positions (${selectedSession.positions?.length || 0})`,
              children: <pre style={{ maxHeight: 420, overflow: "auto" }}>{JSON.stringify(selectedSession.positions || [], null, 2)}</pre>
            }
          ]} />
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
    status: "degraded",
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
