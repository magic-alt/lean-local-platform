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
import dayjs from "dayjs";

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
import { DateStringPicker } from "../components/DateStringPicker";
import { BacktestTrustPanel, ValidationStatusTag } from "../components/backtests/BacktestTrustPanel";
import { candlestickOption } from "../charts/candlestick";
import { defaultBarPreviewValues, defaultSettings } from "../config/defaults";
import { useAsyncData } from "../hooks";
import { asRecord, shortValue } from "../utils/display";
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

function formatDecimal(value?: number | null, digits = 4) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "-";
}

function formatPercent(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "-";
}

function detailText(detail: string | Record<string, unknown>) {
  return typeof detail === "string" ? detail : JSON.stringify(detail);
}

const A_SHARE_INDEX_OPTIONS = [
  { value: "CSI300", label: "沪深300 / CSI300" },
  { value: "CSI500", label: "中证500 / CSI500" },
  { value: "CSI1000", label: "中证1000 / CSI1000" },
  { value: "SSE50", label: "上证50 / SSE50" },
  { value: "STAR50", label: "科创50 / STAR50" }
];

export function ResearchPage() {
  const projects = useAsyncData(api.projects, []);
  const sessions = useAsyncData(api.researchSessions, []);
  const engines = useAsyncData(api.factorEngines, { available: { python: true }, selected: "python" });
  const evaluations = useAsyncData(api.factorEvaluations, { items: [], count: 0 });
  const databaseHealth = useAsyncData<DatabaseHealth>(api.databaseHealth, {
    service: "database",
    ok: false,
    detail: { engine: "", missingTables: [], counts: {}, csi300MembershipRows: 0 }
  });
  const [factorResult, setFactorResult] = useState<FactorEvaluationResult>();
  const [cbondPool, setCbondPool] = useState<{ asOfDate: string; count: number; items: CBondPoolItem[] }>();
  const [cbondRisk, setCbondRisk] = useState<{ asOfDate: string; count: number; items: CBondRiskItem[] }>();
  const [futuresMonitor, setFuturesMonitor] = useState<{ asOfDate: string; count: number; missing: string[]; items: FuturesMainItem[] }>();
  const [pitMembers, setPitMembers] = useState<IndexMembersResult>();
  const [sessionBusy, setSessionBusy] = useState<string>();
  const [toolBusy, setToolBusy] = useState<string>();
  const [researchLogs, setResearchLogs] = useState("");
  const [logsOpen, setLogsOpen] = useState(false);
  const today = dayjs().format("YYYY-MM-DD");
  const researchStart = dayjs().subtract(2, "year").format("YYYY-MM-DD");

  useEffect(() => {
    if (!sessions.data.some((item) => ["queued", "starting", "running", "success"].includes(item.status))) return;
    const timer = window.setInterval(sessions.reload, 4000);
    return () => window.clearInterval(timer);
  }, [sessions.data, sessions.reload]);

  const databaseDetail = databaseHealth.data.detail;
  const databaseDetailRecord = typeof databaseDetail === "object" && databaseDetail !== null && !Array.isArray(databaseDetail)
    ? databaseDetail as Record<string, unknown>
    : {};
  const databaseCounts = (databaseDetailRecord.counts as Record<string, number>) ?? {};
  const databaseEngine = (databaseDetailRecord.engine as string | undefined) || "unknown engine";
  const databaseName = (databaseDetailRecord.database as string | undefined) || "unknown database";
  const databaseHost = databaseDetailRecord.host as string | undefined;
  const databasePort = databaseDetailRecord.port as number | undefined;
  const missingTables = (databaseDetailRecord.missingTables as string[]) ?? [];
  const csi300MembershipRows = (databaseDetailRecord.csi300MembershipRows as number | undefined) ?? 0;
  const dailyBarsCount = databaseCounts.ashare_daily_bars ?? 0;
  const pitRowsCount = databaseCounts.index_membership_pit ?? 0;

  async function evaluate(values: {
    factorName: string;
    universeCode: string;
    startDate: string;
    endDate: string;
    forwardDays: number;
    quantiles: number;
    engine?: string;
  }) {
    setToolBusy("factor");
    try {
      const result = await api.evaluateFactor({ ...values, persist: true });
      setFactorResult(result);
      evaluations.reload();
      message.success("Factor evaluation saved");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setToolBusy(undefined);
    }
  }

  async function queryCbond(values: { date: string; maxDoubleLow: number; excludeCallRisk: boolean }) {
    setToolBusy("cbond");
    try {
      const [pool, risk] = await Promise.all([
        api.cbondDoubleLow({ ...values, limit: 100 }),
        api.cbondCallRisk(values.date)
      ]);
      setCbondPool(pool);
      setCbondRisk(risk);
      if (!pool.count) message.info("该日期没有符合条件的可转债数据，请先在 Data 页同步 TuShare 数据。");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setToolBusy(undefined);
    }
  }

  async function queryFutures(values: { date: string; products?: string }) {
    setToolBusy("futures");
    try {
      const result = await api.futuresAgriMain(values);
      setFuturesMonitor(result);
      if (!result.count) message.info("该日期没有期货主力数据，请先在 Data 页同步 TuShare 数据。");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setToolBusy(undefined);
    }
  }

  async function queryPit(values: { universeCode: string; asOfDate: string }) {
    setToolBusy("pit");
    try {
      const result = await api.indexMembersFromTushareAsOf(values.universeCode, values.asOfDate);
      setPitMembers(result);
      message.success(`TuShare Pro index members loaded${result.fetchedDate ? `: ${result.fetchedDate}` : ""}`);
    } catch (error) {
      message.warning(`TuShare Pro query failed; showing local PIT data. ${(error as Error).message}`);
      setPitMembers(await api.indexMembersAsOf(values.universeCode, values.asOfDate));
    } finally {
      setToolBusy(undefined);
    }
  }

  async function startResearchSession(values: { projectId: string; port?: number }) {
    setSessionBusy("start");
    try {
      await api.startResearch(values);
      message.success("Research 工作台正在启动，Jupyter 就绪后会显示 Running");
      sessions.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSessionBusy(undefined);
    }
  }

  async function sessionAction(session: ResearchSession, action: "stop" | "restart") {
    setSessionBusy(`${action}:${session.id}`);
    try {
      if (action === "stop") await api.stopResearch(session.id);
      else await api.restartResearch(session.id);
      message.success(action === "stop" ? "Research 已停止" : "Research 正在重新启动");
      sessions.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSessionBusy(undefined);
    }
  }

  async function showLogs(session: ResearchSession) {
    setSessionBusy(`logs:${session.id}`);
    try {
      setResearchLogs((await api.researchLogs(session.id)).logs || "No logs yet.");
      setLogsOpen(true);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSessionBusy(undefined);
    }
  }

  async function checkSession(session: ResearchSession) {
    setSessionBusy(`check:${session.id}`);
    try {
      const result = await api.runResearchChecks(session.id);
      Modal.info({
        title: result.passed ? "Research checks passed" : "Research checks failed",
        width: 860,
        content: <pre style={{ maxHeight: 480, overflow: "auto", whiteSpace: "pre-wrap" }}>{JSON.stringify(result, null, 2)}</pre>
      });
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSessionBusy(undefined);
    }
  }

  function deleteSession(session: ResearchSession) {
    Modal.confirm({
      title: "删除 Research 记录？",
      content: "容器会停止，研究工作区默认保留，方便恢复笔记。",
      okText: "删除记录",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await api.deleteResearch(session.id, false);
          message.success("Research 记录已删除，工作区已保留");
          sessions.reload();
        } catch (error) {
          message.error((error as Error).message);
        }
      }
    });
  }

  return (
    <>
      <div className="toolbar">
        <h1 className="page-title">Research</h1>
        <Button icon={<ReloadOutlined />} onClick={() => { sessions.reload(); engines.reload(); evaluations.reload(); databaseHealth.reload(); }}>Refresh</Button>
      </div>
      <Modal title="Research Logs" open={logsOpen} onCancel={() => setLogsOpen(false)} footer={<Button onClick={() => setLogsOpen(false)}>Close</Button>} width={900}>
        <pre style={{ maxHeight: 520, overflow: "auto", whiteSpace: "pre-wrap" }}>{researchLogs}</pre>
      </Modal>
      <Tabs
        items={[
          {
            key: "sessions",
            label: "Research Sessions",
            children: (
              <>
                <Card title="Start Research">
                  <Form layout="vertical" onFinish={startResearchSession}>
                    <div className="field-grid">
                      <Form.Item name="projectId" label="Project" rules={[{ required: true }]}>
                        <Select placeholder="Project" options={projects.data.map((p) => ({ value: p.id, label: p.name }))} />
                      </Form.Item>
                      <Form.Item name="port" label="Preferred Port (optional)">
                        <InputNumber min={1024} max={65535} style={{ width: "100%" }} />
                      </Form.Item>
                    </div>
                    <Button data-testid="start-research-button" type="primary" icon={<ExperimentOutlined />} htmlType="submit" loading={sessionBusy === "start"}>Start</Button>
                  </Form>
                </Card>
                <Card title="Sessions" style={{ marginTop: 16 }}>
                  <Table<ResearchSession>
                    rowKey="id"
                    dataSource={sessions.data}
                    size="small"
                    columns={[
                      { title: "Project", render: (_, session) => session.project_name || projects.data.find((item) => item.id === session.project_id)?.name || session.project_id },
                      { title: "Status", dataIndex: "status", render: (status) => <StatusTag status={status} /> },
                      { title: "Ready", dataIndex: "readiness_status", render: (status) => <StatusTag status={status || "pending"} /> },
                      { title: "Port", dataIndex: "port" },
                      { title: "URL", render: (_, session) => session.url && session.status === "running" ? <a href={session.url} target="_blank" rel="noreferrer">Open Jupyter</a> : "-" },
                      { title: "Error", dataIndex: "error", ellipsis: true, render: (value) => value || "-" },
                      { title: "Action", render: (_, session) => <Space>
                        {session.status === "running" && <Button size="small" loading={sessionBusy === `stop:${session.id}`} onClick={() => sessionAction(session, "stop")}>Stop</Button>}
                        {["stopped", "failed", "cancelled"].includes(session.status) && <Button size="small" loading={sessionBusy === `restart:${session.id}`} onClick={() => sessionAction(session, "restart")}>Restart</Button>}
                        <Button size="small" loading={sessionBusy === `logs:${session.id}`} onClick={() => showLogs(session)}>Logs</Button>
                        <Button size="small" loading={sessionBusy === `check:${session.id}`} onClick={() => checkSession(session)}>Check</Button>
                        <Button size="small" danger icon={<DeleteOutlined />} onClick={() => deleteSession(session)} />
                      </Space> }
                    ]}
                  />
                </Card>
              </>
            )
          },
          {
            key: "pit",
            label: "CSI300 PIT",
            children: (
              <>
                <div className="grid">
                  <Card><Statistic title="Database" value={databaseHealth.data.ok ? "ready" : "check"} /></Card>
                  <Card><Statistic title="CSI300 Rows" value={csi300MembershipRows} /></Card>
                  <Card><Statistic title="Daily Bars" value={dailyBarsCount} /></Card>
                  <Card><Statistic title="PIT Rows" value={pitRowsCount} /></Card>
                </div>
                <Card title="Database" style={{ marginTop: 16 }}>
                  <Space wrap>
                    <Tag color={databaseHealth.data.ok ? "success" : "error"}>{databaseHealth.data.ok ? "ready" : "not ready"}</Tag>
                    <Tag>{databaseEngine}</Tag>
                    <Tag>{databaseName}</Tag>
                    {databaseHost && <Tag>{databaseHost}:{databasePort}</Tag>}
                    {missingTables.map((table) => <Tag key={table} color="error">{table}</Tag>)}
                  </Space>
                  {Boolean(databaseDetailRecord.error) && (
                    <Alert style={{ marginTop: 12 }} type="warning" showIcon message={String(databaseDetailRecord.error)} />
                  )}
                </Card>
                <Card title="Point-in-Time Constituents" style={{ marginTop: 16 }}>
                  <Form layout="inline" onFinish={queryPit} initialValues={{ universeCode: "CSI300", asOfDate: today }}>
                    <Form.Item name="universeCode" rules={[{ required: true }]}>
                      <Select style={{ width: 220 }} options={A_SHARE_INDEX_OPTIONS} />
                    </Form.Item>
                    <Form.Item name="asOfDate" rules={[{ required: true }]}><DateStringPicker /></Form.Item>
                    <Button type="primary" htmlType="submit" loading={toolBusy === "pit"}>Query</Button>
                  </Form>
                  <Alert
                    style={{ marginTop: 12 }}
                    type="info"
                    showIcon
                    message="Default query source is TuShare Pro index_weight. Results are saved into the local PIT table, then displayed from local storage. If TuShare is unavailable, existing local PIT data is shown."
                  />
                </Card>
                <div className="grid" style={{ marginTop: 16 }}>
                  <Card><Statistic title="Universe" value={pitMembers?.universe ?? "CSI300"} /></Card>
                  <Card><Statistic title="As Of" value={pitMembers?.asOfDate ?? "-"} /></Card>
                  <Card><Statistic title="Members" value={pitMembers?.count ?? 0} /></Card>
                  <Card><Statistic title="Coverage" value={pitMembers && pitMembers.count === 0 ? "none" : "partial"} /></Card>
                </div>
                <Card title="Members" style={{ marginTop: 16 }}>
                  <Table<IndexMember>
                    size="small"
                    rowKey={(row) => `${row.universe_code}-${row.symbol}-${row.start_date}`}
                    dataSource={pitMembers?.items ?? []}
                    pagination={{ pageSize: 20 }}
                    columns={[
                      { title: "Symbol", dataIndex: "symbol", width: 100 },
                      { title: "Name", dataIndex: "name", ellipsis: true },
                      { title: "Start", dataIndex: "start_date" },
                      { title: "End", dataIndex: "end_date", render: (value) => value ?? "-" },
                      { title: "Exchange", dataIndex: "exchange" },
                      { title: "Listed", dataIndex: "listed_date", render: (value) => value ?? "-" },
                      { title: "Status", dataIndex: "status" },
                      { title: "ST", dataIndex: "is_st", render: (value) => <Tag color={value ? "warning" : "success"}>{value ? "yes" : "no"}</Tag> }
                    ]}
                  />
                </Card>
              </>
            )
          },
          {
            key: "factors",
            label: "Factors",
            children: (
              <>
                <Card title="Factor Evaluation">
                  <Form layout="vertical" onFinish={evaluate} initialValues={{ factorName: "momentum", universeCode: "ALL_A", startDate: researchStart, endDate: today, forwardDays: 1, quantiles: 5, engine: engines.data.selected }}>
                    <div className="field-grid six">
                      <Form.Item name="factorName" label="Factor" rules={[{ required: true }]}><Input /></Form.Item>
                      <Form.Item name="universeCode" label="Universe" rules={[{ required: true }]}><Input /></Form.Item>
                      <Form.Item name="startDate" label="Start" rules={[{ required: true }]}><DateStringPicker /></Form.Item>
                      <Form.Item name="endDate" label="End" rules={[{ required: true }]}><DateStringPicker /></Form.Item>
                      <Form.Item name="forwardDays" label="Forward Days"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="quantiles" label="Quantiles"><InputNumber min={2} max={20} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="engine" label="Engine">
                        <Select
                          options={Object.entries(engines.data.available).map(([key, available]) => ({
                            value: key,
                            label: available ? key : `${key} unavailable`,
                            disabled: !available
                          }))}
                        />
                      </Form.Item>
                    </div>
                    <Button type="primary" icon={<ExperimentOutlined />} htmlType="submit" loading={toolBusy === "factor"}>Evaluate</Button>
                  </Form>
                </Card>
                {factorResult && (
                  <>
                    <div className="grid" style={{ marginTop: 16 }}>
                      <Card><Statistic title="Observations" value={factorResult.observations} /></Card>
                      <Card><Statistic title="Mean IC" value={formatDecimal(factorResult.mean_ic)} /></Card>
                      <Card><Statistic title="Mean Rank IC" value={formatDecimal(factorResult.mean_rank_ic)} /></Card>
                      <Card><Statistic title="Engine" value={factorResult.engine} /></Card>
                    </div>
                    <Card title="Quantile Returns" style={{ marginBottom: 16 }}>
                      <Table
                        size="small"
                        pagination={false}
                        rowKey="quantile"
                        dataSource={factorResult.quantile_returns}
                        columns={[
                          { title: "Quantile", dataIndex: "quantile" },
                          { title: "Mean Return", dataIndex: "mean_return", render: (value: number | null) => formatPercent(value) },
                          { title: "Count", dataIndex: "count" }
                        ]}
                      />
                    </Card>
                  </>
                )}
                <Card title="Saved Evaluations">
                  <Table
                    size="small"
                    rowKey="id"
                    dataSource={evaluations.data.items}
                    columns={[
                      { title: "Factor", dataIndex: "factor_name" },
                      { title: "Universe", dataIndex: "universe_code" },
                      { title: "Observations", render: (_, row) => row.result?.observations ?? "-" },
                      { title: "Mean IC", render: (_, row) => formatDecimal(row.result?.mean_ic) },
                      { title: "Created", dataIndex: "created_at" }
                    ]}
                  />
                </Card>
              </>
            )
          },
          {
            key: "cbond",
            label: "Convertible Bonds",
            children: (
              <>
                <Card title="Double-Low Pool">
                  <Form layout="inline" onFinish={queryCbond} initialValues={{ date: today, maxDoubleLow: 130, excludeCallRisk: true }}>
                    <Form.Item name="date" rules={[{ required: true }]}><DateStringPicker /></Form.Item>
                    <Form.Item name="maxDoubleLow"><InputNumber min={0} /></Form.Item>
                    <Form.Item name="excludeCallRisk" valuePropName="checked"><Checkbox>Exclude Call Risk</Checkbox></Form.Item>
                    <Button type="primary" htmlType="submit" loading={toolBusy === "cbond"}>Query</Button>
                  </Form>
                </Card>
                <Card title="Pool" style={{ marginTop: 16 }}>
                  <Table<CBondPoolItem>
                    size="small"
                    rowKey="bond_code"
                    dataSource={cbondPool?.items ?? []}
                    columns={[
                      { title: "Bond", dataIndex: "bond_code" },
                      { title: "Name", dataIndex: "bond_name" },
                      { title: "Stock", dataIndex: "stock_symbol" },
                      { title: "Date", dataIndex: "trade_date" },
                      { title: "Close", dataIndex: "close" },
                      { title: "Premium", dataIndex: "premium_rate", render: (value) => formatPercent(value) },
                      { title: "Double Low", dataIndex: "double_low", render: (value) => formatDecimal(value, 2) },
                      { title: "Remaining", dataIndex: "current_remaining_size" }
                    ]}
                  />
                </Card>
                <Card title="Call Risk" style={{ marginTop: 16 }}>
                  <Table<CBondRiskItem>
                    size="small"
                    rowKey="id"
                    dataSource={cbondRisk?.items ?? []}
                    columns={[
                      { title: "Bond", dataIndex: "bond_code" },
                      { title: "Name", dataIndex: "bond_name" },
                      { title: "Announce", dataIndex: "announce_date" },
                      { title: "Status", dataIndex: "status" },
                      { title: "Last Trade", dataIndex: "last_trade_date" }
                    ]}
                  />
                </Card>
              </>
            )
          },
          {
            key: "futures",
            label: "Futures",
            children: (
              <>
                <Card title="Agricultural Main Contracts">
                  <Form layout="inline" onFinish={queryFutures} initialValues={{ date: today, products: "A,M,Y,P,C,CS,JD,LH,SR,CF,RM,OI,AP,CJ,PK" }}>
                    <Form.Item name="date" rules={[{ required: true }]}><DateStringPicker /></Form.Item>
                    <Form.Item name="products"><Input style={{ width: 360 }} /></Form.Item>
                    <Button type="primary" htmlType="submit" loading={toolBusy === "futures"}>Query</Button>
                  </Form>
                </Card>
                <div className="grid" style={{ marginTop: 16 }}>
                  <Card><Statistic title="Matched" value={futuresMonitor?.count ?? 0} /></Card>
                  <Card><Statistic title="Missing" value={futuresMonitor?.missing.length ?? 0} /></Card>
                </div>
                <Card title="Main Contracts">
                  <Table<FuturesMainItem>
                    size="small"
                    rowKey="contract_code"
                    dataSource={futuresMonitor?.items ?? []}
                    columns={[
                      { title: "Product", dataIndex: "product" },
                      { title: "Contract", dataIndex: "contract_code" },
                      { title: "Exchange", dataIndex: "exchange" },
                      { title: "Bar Date", dataIndex: "bar_date" },
                      { title: "Close", dataIndex: "close" },
                      { title: "Volume", dataIndex: "volume" },
                      { title: "Open Interest", dataIndex: "open_interest" },
                      { title: "Days To Expiry", dataIndex: "daysToExpiry" }
                    ]}
                  />
                </Card>
              </>
            )
          }
        ]}
      />
    </>
  );
}
