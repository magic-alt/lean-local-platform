import { Alert, Button, Card, Checkbox, Col, Descriptions, Divider, Form, Input, Modal, Popconfirm, Row, Select, Space, Statistic, Steps, Switch, Table, Tabs, Tag, Typography, message } from "antd";
import { ApiOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { AshareTechAgentRun, AshareTechEvaluationItem, AshareTechEvaluationSummary, AshareTechGroupSummary, AshareTechMarketEnvironmentItem, AshareTechModelDiagnostic, AshareTechReport, AshareTechRuleTag, AshareTechStockRow, AshareTechWatchlistItem } from "../api";
import { ApiError } from "../api/client";
import { LeanChart } from "../charts/LeanChart";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { FormActions, FormGrid } from "../components/forms/FormLayout";
import { useAsyncData } from "../hooks";

const emptyList = { items: [], count: 0, limit: 50, offset: 0 };
const emptyWatchlist = { items: [], count: 0, enabledCount: 0, maxSize: 60, groups: [], fingerprint: "" };
const emptyEvaluationSummary: AshareTechEvaluationSummary = {
  sampleSize: 0, pending: 0, sampleSufficient: false, byHorizon: []
};
const ruleTagOptions = [
  { value: "strong_ai", label: "强势AI" },
  { value: "storage", label: "存储" }
];

function statusColor(status: string) {
  if (status === "success") return "green";
  if (status === "failed" || status === "cancelled") return "red";
  if (status === "waiting_data") return "orange";
  return "blue";
}

function labelColor(label: string) {
  if (["低吸观察", "小仓试错前置"].includes(label)) return "green";
  if (["风险较高", "不追高"].includes(label)) return "red";
  if (label === "重点观察") return "blue";
  return "default";
}

function agentStatusColor(status?: string | null) {
  if (status === "success" || status === "ok") return "green";
  if (status === "degraded" || status === "fallback" || status === "unconfigured") return "orange";
  if (status === "failed" || status === "error") return "red";
  return "blue";
}

function directionTag(direction?: string | null) {
  if (!direction) return <Tag>-</Tag>;
  const labels: Record<string, string> = { bullish: "看多", neutral: "中性", bearish: "看空" };
  return <Tag color={direction === "bullish" ? "red" : direction === "bearish" ? "green" : "default"}>{labels[direction] || direction}</Tag>;
}

const number = (value?: number | null) => value == null ? "-" : value.toFixed(2);
const ratio = (value?: number | null) => value == null ? "-" : `${value.toFixed(2)}×`;
const amountYi = (value?: number | null) => value == null ? "-" : `${(value / 100_000_000).toFixed(2)}亿`;

function changeValue(value?: number | null) {
  if (value == null) return <span>-</span>;
  return <span style={{ color: value > 0 ? "#cf1322" : value < 0 ? "#389e0d" : undefined, fontWeight: 600 }}>
    {value > 0 ? "+" : ""}{value.toFixed(2)}%
  </span>;
}

function energyState(item: AshareTechMarketEnvironmentItem) {
  const level = Math.max(item.volumeRatio20 || 0, item.amountRatio20 || 0);
  if (level >= 2) return <Tag color="red">强放量</Tag>;
  if (level >= 1.5) return <Tag color="orange">明显放量</Tag>;
  if (level <= 0.7 && level > 0) return <Tag color="blue">明显缩量</Tag>;
  return <Tag>量能平稳</Tag>;
}

const marketColumns = [
  { title: "市场", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => <div className="table-primary-cell"><strong>{item.name}</strong><span className="muted">{item.code}</span></div> },
  { title: "日期", dataIndex: "date", width: 110 },
  { title: "行情", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => <div className="table-primary-cell"><span>收盘 {number(item.close)}</span>{changeValue(item.changePct)}</div> },
  { title: "量能", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => <div className="table-primary-cell"><span>量比 {ratio(item.volumeRatio20)}</span><span>额比 {ratio(item.amountRatio20)}</span></div> },
  { title: "量能判断", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => energyState(item), width: 110 },
  { title: "来源", dataIndex: "source" }
];

const sectorColumns = [
  { title: "主题 / 板块", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => <div className="table-primary-cell"><strong>{item.keyword}</strong><span>{item.matchedName || item.name} · {item.code}</span>{item.matchRule === "alias" ? <Tag color="blue">别名：{item.matchedKeyword}</Tag> : <Tag>精确</Tag>}</div> },
  { title: "涨跌幅", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => changeValue(item.changePct), width: 100 },
  { title: "流动性", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => <div className="table-primary-cell"><span>量比 {ratio(item.volumeRatio20)} · 额比 {ratio(item.amountRatio20)}</span><span>换手 {item.turnoverRate == null ? "-" : `${item.turnoverRate.toFixed(2)}%`}</span></div> },
  { title: "连续回调", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => `${item.pullbackDays || 0}日`, width: 100 },
  { title: "量能判断", render: (_: unknown, item: AshareTechMarketEnvironmentItem) => energyState(item), width: 110 },
  { title: "来源", dataIndex: "source" }
];

const groupColumns = [
  { title: "观察池分组", dataIndex: "group", width: 240 },
  { title: "等权平均涨跌", render: (_: unknown, item: AshareTechGroupSummary) => changeValue(item.averageChangePct), width: 130 },
  { title: "合计成交额", render: (_: unknown, item: AshareTechGroupSummary) => amountYi(item.totalAmount), width: 130 },
  { title: "上涨/下跌", render: (_: unknown, item: AshareTechGroupSummary) => <Space><Tag color="red">涨 {item.advancers}</Tag><Tag color="green">跌 {item.decliners}</Tag></Space>, width: 150 },
  { title: "口径", dataIndex: "source", width: 260 }
];

const stockColumns = [
  { title: "股票", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><strong>{item.name}</strong><span className="muted">{item.code}</span></div> },
  { title: "行情", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><span>收盘 {number(item.close)}</span><span>涨跌 {number(item.changePct)}%</span><span>20日回撤 {number(item.drawdown20Pct)}%</span></div> },
  { title: "均线", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><span>MA5/20/60</span><span>{number(item.ma5)} / {number(item.ma20)} / {number(item.ma60)}</span><span>偏离20/60 {number(item.ma20DeviationPct)}% / {number(item.ma60DeviationPct)}%</span></div> },
  { title: "量价", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><span>量比/额比 {number(item.volumeRatio20)} / {number(item.amountRatio20)}</span><span>换手 {number(item.turnoverRate)}%</span><span>{item.volumePriceState}</span></div> },
  { title: "技术结构", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><span>{item.ma20Position} · {item.ma60Position}</span><span>{item.movingAverageDirection}</span><span>{item.priceStructure} · {item.macdStatus}</span></div> },
  { title: "关键价位", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><span>支撑 {number(item.keySupport)}</span><span>观察 {item.observationZone?.map(number).join("–") || "-"}</span><span>{item.invalidation == null ? "无失效价" : `失效：收盘低于 ${number(item.invalidation)}`}</span></div> },
  { title: "判断", render: (_: unknown, item: AshareTechStockRow) => <div className="table-primary-cell"><Tag color={labelColor(item.conclusion)}>{item.conclusion}</Tag><span>{item.direction} · {item.triggerType}</span><span>{item.announcementRisk || "无公告风险提示"}</span></div> },
  { title: "数据", render: (_: unknown, item: AshareTechStockRow) => item.dataCompleteness?.missing?.length ? `降级：${item.dataCompleteness.missing.join("；")}` : `${item.dataCompleteness?.sampleCount || 0}日 / 完整` }
];

export function AshareTechInsights() {
  const reports = useAsyncData(api.ashareTechReports, emptyList, false);
  const capabilities = useAsyncData(api.ashareTechCapabilities, {
    poolSize: 26, totalPoolSize: 26, defaultPoolSize: 26, groups: [], primarySource: "TuShare Pro", crossCheckSource: "东方财富",
    promptVersion: "ashare-tech-gpt56-v1", configured: false, provider: null, model: null, endpointHost: null,
    apiStyle: "OpenAI-compatible chat/completions", agentMode: "hybrid_multi_agent" as const,
    defaultAnalysisMode: "deterministic" as const, stages: [], evaluationHorizons: [1, 5, 20],
    agentPromptVersion: "ashare-tech-agent-v2", llmOptional: true, paperHandoff: false,
    schedule: "工作日17:30", labels: []
  }, false);
  const watchlist = useAsyncData(api.ashareTechWatchlist, emptyWatchlist, false);
  const loadEvaluations = useCallback(
    () => api.ashareTechEvaluations({ limit: 500 }),
    []
  );
  const evaluationSummary = useAsyncData(api.ashareTechEvaluationSummary, emptyEvaluationSummary, false);
  const evaluations = useAsyncData<{ items: AshareTechEvaluationItem[]; count: number }>(
    loadEvaluations,
    { items: [], count: 0 },
    false
  );
  const [selected, setSelected] = useState<AshareTechReport | null>(null);
  const [agentRun, setAgentRun] = useState<AshareTechAgentRun | null>(null);
  const [diagnostic, setDiagnostic] = useState<AshareTechModelDiagnostic | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [refreshingEvaluations, setRefreshingEvaluations] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [detailWarning, setDetailWarning] = useState<string | null>(null);
  const [addForm] = Form.useForm();

  const loadErrors = [reports.error, capabilities.error, watchlist.error, evaluationSummary.error, evaluations.error].filter((item): item is Error => Boolean(item));
  const routeMissing = loadErrors.some((error) => error instanceof ApiError && error.status === 404);

  const refreshAll = useCallback(async () => {
    const [nextReports] = await Promise.all([
      reports.reload(), capabilities.reload(), watchlist.reload(), evaluationSummary.reload(), evaluations.reload()
    ]);
    if (selected && nextReports && !nextReports.items.some((item) => item.id === selected.id)) {
      setSelected(null);
      setDetailWarning("该报告已不在历史列表中，已清空详情并停止自动轮询。");
    }
  }, [capabilities, evaluationSummary, evaluations, reports, selected, watchlist]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const detail = await api.ashareTechReport(id);
      setSelected(detail);
      if (detail.active_agent_run_id) {
        try {
          setAgentRun(await api.ashareTechAgentRun(detail.active_agent_run_id));
        } catch (agentError) {
          setAgentRun(null);
          message.warning(`报告已加载，但 Agent 审计记录读取失败：${(agentError as Error).message}`);
        }
      } else {
        setAgentRun(null);
      }
      setDetailWarning(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setSelected(null);
        setDetailWarning("该报告已不存在，已停止自动轮询。可能是历史数据被清理或后端尚未加载新版路由。");
        return;
      }
      message.error((error as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!selected || !["queued", "running", "waiting_data"].includes(selected.status)) return;
    const timer = window.setTimeout(() => { void loadDetail(selected.id); void reports.reload(); }, 3000);
    return () => window.clearTimeout(timer);
  }, [loadDetail, reports.reload, selected?.id, selected?.status]);

  async function create(values: { requestedDate?: string; force?: boolean; analysisMode?: "auto" | "hybrid_multi_agent" | "deterministic" }) {
    setSubmitting(true);
    try {
      const result = await api.createAshareTechReport(values);
      message.success(result.reused ? "已打开同日报告任务" : "日报任务已进入队列");
      await reports.reload();
      await loadDetail(result.id);
    } catch (error) { message.error((error as Error).message); }
    finally { setSubmitting(false); }
  }

  async function diagnoseModel() {
    setDiagnosing(true);
    try {
      const result = await api.diagnoseAshareTechModel();
      setDiagnostic(result);
      if (result.status === "ok") message.success(`模型连接正常，耗时 ${result.latencyMs ?? "-"}ms`);
      else message.warning(result.error || "模型尚未配置");
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDiagnosing(false);
    }
  }

  async function refreshEvaluationData() {
    setRefreshingEvaluations(true);
    try {
      await api.refreshAshareTechEvaluations();
      message.success("预测评估刷新任务已进入队列");
      window.setTimeout(() => {
        void evaluationSummary.reload();
        void evaluations.reload();
      }, 2500);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setRefreshingEvaluations(false);
    }
  }

  async function addStock(values: { code: string; groupKey: AshareTechWatchlistItem["groupKey"]; ruleTags?: AshareTechRuleTag[] }) {
    setMutating(true);
    try {
      const item = await api.addAshareTechWatchlistItem({ ...values, code: values.code.trim(), ruleTags: values.ruleTags || [] });
      message.success(`已添加 ${item.code} ${item.name}`);
      setAddOpen(false);
      addForm.resetFields();
      await Promise.all([watchlist.reload(), capabilities.reload()]);
    } catch (error) { message.error((error as Error).message); }
    finally { setMutating(false); }
  }

  async function updateStock(code: string, payload: { enabled?: boolean; groupKey?: AshareTechWatchlistItem["groupKey"]; ruleTags?: AshareTechRuleTag[] }) {
    setMutating(true);
    try {
      await api.updateAshareTechWatchlistItem(code, payload);
      await Promise.all([watchlist.reload(), capabilities.reload()]);
    } catch (error) {
      message.error((error as Error).message);
      await watchlist.reload();
    } finally { setMutating(false); }
  }

  async function deleteStock(code: string) {
    setMutating(true);
    try {
      await api.deleteAshareTechWatchlistItem(code);
      message.success(`已从当前观察池删除 ${code}`);
      await Promise.all([watchlist.reload(), capabilities.reload()]);
    } catch (error) { message.error((error as Error).message); }
    finally { setMutating(false); }
  }

  async function resetStocks() {
    setMutating(true);
    try {
      await api.resetAshareTechWatchlist();
      message.success("已恢复默认26只观察池");
      await Promise.all([watchlist.reload(), capabilities.reload()]);
    } catch (error) { message.error((error as Error).message); }
    finally { setMutating(false); }
  }

  async function deleteReport(item: AshareTechReport) {
    setMutating(true);
    try {
      const active = ["created", "queued", "running", "waiting_data", "interrupted"].includes(item.status);
      const result = await api.deleteAshareTechReport(item.id, active);
      if (selected?.id === item.id) setSelected(null);
      message.success(result.recoveredOrphan
        ? `已清理 ${item.requested_date} 的孤儿报告`
        : result.cancelledTasks > 0
          ? `已取消任务并删除 ${item.requested_date} 的报告`
          : `已删除 ${item.requested_date} 的历史报告`);
      await reports.reload();
    } catch (error) { message.error((error as Error).message); }
    finally { setMutating(false); }
  }

  const report = selected?.report;
  const marketEnvironment = report?.marketEnvironment || [];
  const indexEnvironment = marketEnvironment.filter((item) => item.category !== "sector");
  const sectorEnvironment = marketEnvironment.filter((item) => item.category === "sector" && !item.unresolved);
  const unresolvedSectorEnvironment = marketEnvironment.filter((item) => item.category === "sector" && item.unresolved);
  const expectedSectorKeywords = ["半导体", "存储", "CPO", "PCB", "AI服务器"];
  const coveredSectorKeywords = new Set(sectorEnvironment.map((item) => item.keyword).filter(Boolean));
  const missingSectorKeywords = expectedSectorKeywords.filter((keyword) => !coveredSectorKeywords.has(keyword));
  const selectedSymbols = new Map((report?.fullPool || []).map((item) => [item.code, item]));
  const predictionMap = new Map(
    (agentRun?.predictions || []).map((item) => [`${item.symbol}:${item.horizon_days}`, item])
  );
  const topSelections = report?.agentRunSummary?.topSelections || selected?.agentSummary?.topSelections || [];
  const topSelectionRows = topSelections.map((item) => ({
    ...item,
    name: selectedSymbols.get(item.symbol)?.name || item.symbol,
    ruleConclusion: selectedSymbols.get(item.symbol)?.conclusion
  }));
  const stageItems = (agentRun?.stages || report?.agentRunSummary?.stages || []).map((stage) => ({
    title: capabilities.data.stages.find((item) => item.key === stage.stage_key)?.name || stage.stage_key,
    status: stage.status === "success" ? "finish" as const
      : stage.status === "failed" ? "error" as const
        : stage.status === "running" ? "process" as const
          : "wait" as const,
    description: <Space direction="vertical" size={0}>
      <Tag color={agentStatusColor(stage.status)}>{stage.status}</Tag>
      <span className="muted">{stage.model || capabilities.data.model || "-"} · {stage.latency_ms == null ? "-" : `${stage.latency_ms}ms`}</span>
    </Space>
  }));
  const evaluationChartOption = {
    tooltip: { trigger: "axis" },
    legend: { data: ["方向命中率", "平均收益", "平均超额", "Top5提升"] },
    xAxis: { type: "category", data: evaluationSummary.data.byHorizon.map((item) => `${item.horizonDays}日`) },
    yAxis: [
      { type: "value", name: "百分比", axisLabel: { formatter: "{value}%" } }
    ],
    series: [
      {
        name: "方向命中率", type: "bar",
        data: evaluationSummary.data.byHorizon.map((item) => item.directionAccuracy == null ? null : item.directionAccuracy * 100)
      },
      {
        name: "平均收益", type: "line",
        data: evaluationSummary.data.byHorizon.map((item) => item.averageReturnPct ?? null)
      },
      {
        name: "平均超额", type: "line",
        data: evaluationSummary.data.byHorizon.map((item) => item.averageExcessReturnPct ?? null)
      },
      {
        name: "Top5提升", type: "line",
        data: evaluationSummary.data.byHorizon.map((item) => item.top5LiftPct ?? null)
      }
    ]
  };
  return (
    <>
      <Card
        title={<Space><ApiOutlined />大模型与多 Agent 接口</Space>}
        style={{ marginBottom: 16 }}
        extra={<Button icon={<ApiOutlined />} loading={diagnosing} onClick={() => void diagnoseModel()}>检测连接</Button>}
      >
        <Row gutter={[16, 16]}>
          <Col xs={24} md={6}><Statistic title="Provider / 模型" value={`${capabilities.data.provider || "未配置"} / ${capabilities.data.model || "-"}`} /></Col>
          <Col xs={12} md={4}><Statistic title="连接配置" value={capabilities.data.configured ? "已配置" : "未配置"} valueStyle={{ color: capabilities.data.configured ? "#3f8600" : "#cf1322" }} /></Col>
          <Col xs={12} md={4}><Statistic title="默认模式" value={capabilities.data.defaultAnalysisMode === "hybrid_multi_agent" ? "六阶段 Agent" : "确定性"} /></Col>
          <Col xs={12} md={5}><Statistic title="接口" value={capabilities.data.apiStyle} /></Col>
          <Col xs={12} md={5}><Statistic title="Prompt" value={capabilities.data.agentPromptVersion} /></Col>
        </Row>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          模型通过 {capabilities.data.endpointHost || "未配置端点"} 的结构化 JSON 接口运行。规则引擎提供事实和硬风险门禁；
          Agent 负责技术趋势、基本面、多空复核、风险审查与研究排序。API Key 仅保存在服务环境变量中，页面不会读取或保存密钥。
        </Typography.Paragraph>
        {diagnostic && <Alert
          showIcon style={{ marginTop: 12 }}
          type={diagnostic.status === "ok" ? "success" : diagnostic.status === "unconfigured" ? "warning" : "error"}
          message={`连接诊断：${diagnostic.status}${diagnostic.latencyMs == null ? "" : ` · ${diagnostic.latencyMs}ms`}`}
          description={diagnostic.error || `${diagnostic.provider || "-"} / ${diagnostic.model || "-"} 已返回合法结构化 JSON`}
        />}
      </Card>
      <Alert
        showIcon type="info" style={{ marginBottom: 16 }}
        message={`当前启用 ${capabilities.data.poolSize} / 总计 ${capabilities.data.totalPoolSize} 只｜${capabilities.data.schedule}｜${capabilities.data.stages.length || 6} 个 Agent`}
        description="TuShare Pro 提供量价与 PIT 基本面，东方财富只核验最新收盘。模型对观察池做研究排序，规则引擎保留最终风险门禁；任一 Agent 失败都会显式降级。本工作区没有 Paper 或自动下单入口。"
      />
      {loadErrors.length > 0 && <Alert
        showIcon type="error" style={{ marginBottom: 16 }}
        message={routeMissing ? "A股科技日报 API 未加载" : "刷新失败"}
        description={routeMissing
          ? "当前前端已使用新版独立接口，但 API 进程仍可能是旧版本。请重启 api、worker 和 beat：docker compose --profile app up -d --build api worker beat"
          : [...new Set(loadErrors.map((error) => error.message))].join("；")}
      />}
      {detailWarning && <Alert showIcon closable onClose={() => setDetailWarning(null)} type="warning" style={{ marginBottom: 16 }} message={detailWarning} />}
      <Card title="生成 A股科技股收盘日报" extra={<Button icon={<ReloadOutlined />} onClick={() => void refreshAll()}>刷新</Button>}>
        <Form layout="inline" onFinish={create} initialValues={{ force: false, analysisMode: "auto" }}>
          <Form.Item name="requestedDate" label="报告日期"><DateStringPicker /></Form.Item>
          <Form.Item name="analysisMode" label="分析模式">
            <Select style={{ width: 190 }} options={[
              { value: "auto", label: "自动（优先多 Agent）" },
              { value: "hybrid_multi_agent", label: "混合六阶段 Agent" },
              { value: "deterministic", label: "仅确定性规则" }
            ]} />
          </Form.Item>
          <Form.Item name="force" valuePropName="checked"><Checkbox>使用最新观察池强制重新生成</Checkbox></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={submitting}>生成/打开日报</Button></Form.Item>
        </Form>
      </Card>
      <Card
        title={`观察池管理（启用 ${watchlist.data.enabledCount} / 总计 ${watchlist.data.count}，上限 ${watchlist.data.maxSize}）`}
        style={{ marginTop: 16 }}
        extra={<Space>
          <Button icon={<PlusOutlined />} type="primary" onClick={() => setAddOpen(true)} disabled={watchlist.data.count >= watchlist.data.maxSize}>添加股票</Button>
          <Popconfirm title="恢复默认26只观察池？" description="当前自定义增删、启停和规则标签将被覆盖；历史报告不受影响。" onConfirm={() => void resetStocks()}>
            <Button danger loading={mutating}>恢复默认</Button>
          </Popconfirm>
        </Space>}
      >
        <Typography.Paragraph type="secondary">
          名称和上市状态由 TuShare 验证。修改只影响此后创建的报告；已排队、重试中及历史报告继续使用创建时快照。
        </Typography.Paragraph>
        <Table<AshareTechWatchlistItem>
          rowKey="code" size="small" loading={watchlist.loading} dataSource={watchlist.data.items}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "代码", dataIndex: "code", width: 90 }, { title: "名称", dataIndex: "name", width: 150 },
            { title: "规则分组（可编辑）", width: 220, render: (_, item) => <Select
              value={item.groupKey}
              options={watchlist.data.groups.map((group) => ({ value: group.key, label: group.name }))}
              style={{ width: "100%" }}
              disabled={mutating}
              onChange={(groupKey) => void updateStock(item.code, { groupKey })}
            /> },
            { title: "启用", width: 80, render: (_, item) => <Switch checked={item.enabled} loading={mutating} onChange={(enabled) => void updateStock(item.code, { enabled })} /> },
            { title: "特殊规则标签（可编辑）", width: 260, render: (_, item) => <Select
              mode="multiple" value={item.ruleTags} options={ruleTagOptions} style={{ width: "100%" }} disabled={mutating}
              onChange={(ruleTags) => void updateStock(item.code, { ruleTags: ruleTags as AshareTechRuleTag[] })}
            /> },
            { title: "操作", width: 90, render: (_, item) => <Popconfirm title={`删除 ${item.code} ${item.name}？`} description="只从当前观察池删除，历史报告保持不变。" onConfirm={() => void deleteStock(item.code)}>
              <Button danger size="small" disabled={mutating}>删除</Button>
            </Popconfirm> }
          ]}
        />
      </Card>
      <Card title={`历史报告（${reports.data.count}）`} style={{ marginTop: 16 }}>
        <Table<AshareTechReport> rowKey="id" size="small" loading={reports.loading} dataSource={reports.data.items} pagination={{ pageSize: 8 }} columns={[
          { title: "请求日期", dataIndex: "requested_date" }, { title: "分析日期", dataIndex: "analysis_date" },
          { title: "市场状态", dataIndex: "market_status" },
          { title: "状态", render: (_, item) => <Tag color={statusColor(item.status)}>{item.status}</Tag> },
          { title: "尝试", dataIndex: "attempt_count" },
          { title: "操作", render: (_, item) => <Space>
            <Button size="small" onClick={() => void loadDetail(item.id)}>查看</Button>
            <Popconfirm
              title={`删除 ${item.requested_date} 的历史报告？`}
              description={["created", "queued", "running", "waiting_data", "interrupted"].includes(item.status)
                ? "活动任务会先取消；若任务已丢失，则清理孤儿状态。报告及日志随后删除。"
                : "报告及关联任务日志会被删除，此操作不可撤销。"}
              okText="删除"
              okButtonProps={{ danger: true }}
              onConfirm={() => void deleteReport(item)}
            >
              <Button danger size="small" icon={<DeleteOutlined />} loading={mutating}>
                {["created", "queued", "running", "waiting_data", "interrupted"].includes(item.status) ? "取消并删除" : "删除"}
              </Button>
            </Popconfirm>
          </Space> }
        ]} />
      </Card>
      {selected && <Card title={report?.title || `报告 ${selected.requested_date}`} style={{ marginTop: 16 }}>
        <Descriptions bordered size="small" column={3}>
          <Descriptions.Item label="状态"><Tag color={statusColor(selected.status)}>{selected.status}</Tag></Descriptions.Item>
          <Descriptions.Item label="行情日">{selected.analysis_date || "-"}</Descriptions.Item>
          <Descriptions.Item label="截止">{selected.data_cutoff_at || "-"}</Descriptions.Item>
          <Descriptions.Item label="主源">{report?.primarySource || selected.primary_source}</Descriptions.Item>
          <Descriptions.Item label="交叉核验">{report?.crossCheckSource || "-"}</Descriptions.Item>
          <Descriptions.Item label="模型">
            <Space>
              <span>{selected.model || capabilities.data.model || "未配置"}</span>
              <Tag color={agentStatusColor(selected.llm_status)}>{selected.llm_status || "legacy / deterministic"}</Tag>
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {selected.error && <Alert type="error" showIcon message={selected.error} style={{ marginTop: 16 }} />}
        {report?.summary && <Alert type="warning" showIcon message={report.summary} style={{ marginTop: 16 }} />}
        <Tabs
          style={{ marginTop: 16 }}
          items={[
            {
              key: "decision",
              label: "AI 决策台",
              children: <>
                {topSelectionRows.length === 0
                  ? <Alert
                    showIcon
                    type={selected.llm_status === "degraded" ? "warning" : "info"}
                    message={selected.llm_status === "degraded" ? "Agent 已降级，保留规则报告" : "该报告没有可用的 Agent 排名"}
                    description={report?.agentRunSummary?.fallbackReason || selected.agentSummary?.fallbackReason || "旧报告或确定性模式不会生成模型排名。"}
                  />
                  : <Table
                    rowKey="symbol"
                    size="small"
                    pagination={false}
                    dataSource={topSelectionRows}
                    columns={[
                      { title: "排名", dataIndex: "rank", width: 70 },
                      { title: "股票", render: (_, item) => <div className="table-primary-cell"><strong>{item.name}</strong><span>{item.symbol}</span></div> },
                      { title: "规则结论", render: (_, item) => <Tag color={labelColor(item.ruleConclusion || "")}>{item.ruleConclusion || "-"}</Tag> },
                      ...([1, 5, 20] as const).map((horizon) => ({
                        title: `${horizon}日趋势`,
                        render: (_: unknown, item: typeof topSelectionRows[number]) => {
                          const prediction = predictionMap.get(`${item.symbol}:${horizon}`);
                          return <div className="table-primary-cell">
                            {directionTag(prediction?.predicted_direction)}
                            <span>{prediction ? `置信 ${(prediction.confidence * 100).toFixed(0)}%` : "-"}</span>
                          </div>;
                        }
                      })),
                      { title: "共识分", dataIndex: "consensusScore", width: 85, render: (value: number) => number(value) },
                      { title: "可审计摘要", dataIndex: "rationale", ellipsis: true }
                    ]}
                  />}
                {topSelectionRows.length > 0 && <Alert
                  style={{ marginTop: 12 }}
                  type="info"
                  showIcon
                  message={report?.agentRunSummary?.marketRegime || selected.agentSummary?.marketRegime || "Agent 综合研究"}
                  description={report?.agentRunSummary?.summary || selected.agentSummary?.summary}
                />}
              </>
            },
            {
              key: "agents",
              label: "Agent 过程",
              children: <>
                {stageItems.length > 0
                  ? <Steps responsive size="small" items={stageItems} />
                  : <Alert type="info" showIcon message="尚无 Agent 阶段记录" description="旧报告或确定性模式只显示规则输出。" />}
                {(agentRun?.stages || []).length > 0 && <Table
                  style={{ marginTop: 18 }}
                  rowKey="stage_key"
                  size="small"
                  pagination={false}
                  dataSource={agentRun?.stages}
                  expandable={{
                    expandedRowRender: (stage) => <pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>
                      {JSON.stringify(stage.output || {}, null, 2)}
                    </pre>
                  }}
                  columns={[
                    { title: "阶段", render: (_, item) => capabilities.data.stages.find((stage) => stage.key === item.stage_key)?.name || item.stage_key },
                    { title: "状态", render: (_, item) => <Tag color={agentStatusColor(item.status)}>{item.status}</Tag> },
                    { title: "模型", dataIndex: "model" },
                    { title: "耗时", render: (_, item) => item.latency_ms == null ? "-" : `${item.latency_ms}ms` },
                    { title: "尝试", dataIndex: "attempt_count" },
                    { title: "诊断", render: (_, item) => item.error ? `${item.error_category}: ${item.error}` : "结构校验通过" }
                  ]}
                />}
                <Alert
                  style={{ marginTop: 12 }}
                  type="info"
                  showIcon
                  message="这里只展示结构化观点和证据引用"
                  description="系统不保存或展示模型隐藏思维链。每个阶段只能引用服务端生成的 factId，规则风险否决拥有最终优先级。"
                />
              </>
            },
            {
              key: "evaluation",
              label: "效果评估",
              children: <>
                <Space style={{ marginBottom: 12 }}>
                  <Button icon={<ReloadOutlined />} loading={refreshingEvaluations} onClick={() => void refreshEvaluationData()}>刷新成熟预测</Button>
                  <Tag color={evaluationSummary.data.sampleSufficient ? "green" : "orange"}>
                    {evaluationSummary.data.sampleSufficient ? "样本可评估" : "样本不足（少于20）"}
                  </Tag>
                  <Tag>全模型 / Prompt 版本汇总</Tag>
                </Space>
                <Row gutter={[16, 16]}>
                  <Col xs={12} md={4}><Statistic title="成熟样本" value={evaluationSummary.data.sampleSize} /></Col>
                  <Col xs={12} md={4}><Statistic title="待成熟" value={evaluationSummary.data.pending} /></Col>
                  <Col xs={12} md={4}><Statistic title="方向命中" value={evaluationSummary.data.directionAccuracy == null ? "-" : evaluationSummary.data.directionAccuracy * 100} suffix={evaluationSummary.data.directionAccuracy == null ? "" : "%"} precision={1} /></Col>
                  <Col xs={12} md={4}><Statistic title="Brier" value={evaluationSummary.data.meanBrier ?? "-"} precision={3} /></Col>
                  <Col xs={12} md={4}><Statistic title="平均收益" value={evaluationSummary.data.averageReturnPct ?? "-"} suffix={evaluationSummary.data.averageReturnPct == null ? "" : "%"} precision={2} /></Col>
                  <Col xs={12} md={4}><Statistic title="平均超额" value={evaluationSummary.data.averageExcessReturnPct ?? "-"} suffix={evaluationSummary.data.averageExcessReturnPct == null ? "" : "%"} precision={2} /></Col>
                </Row>
                {evaluationSummary.data.byHorizon.length > 0
                  ? <LeanChart option={evaluationChartOption} style={{ height: 340, marginTop: 16 }} />
                  : <Alert style={{ marginTop: 16 }} type="info" message="预测尚未到达1/5/20个交易日评估窗口" />}
                <Table<AshareTechEvaluationItem>
                  style={{ marginTop: 16 }}
                  rowKey="id"
                  size="small"
                  dataSource={evaluations.data.items.slice(0, 50)}
                  pagination={{ pageSize: 10 }}
                  columns={[
                    { title: "股票", dataIndex: "symbol" },
                    { title: "周期", render: (_, item) => `${item.horizon_days}日` },
                    { title: "模型 / Prompt", render: (_, item) => <div className="table-primary-cell"><span>{item.model}</span><span className="muted">{item.prompt_version}</span></div> },
                    { title: "预测", render: (_, item) => directionTag(item.predicted_direction) },
                    { title: "实际", render: (_, item) => directionTag(item.realized_direction) },
                    { title: "收益", render: (_, item) => item.return_pct == null ? "-" : `${item.return_pct.toFixed(2)}%` },
                    { title: "超额", render: (_, item) => item.excess_return_pct == null ? "-" : `${item.excess_return_pct.toFixed(2)}%` },
                    { title: "结果", render: (_, item) => item.evaluation_status === "evaluated"
                      ? <Tag color={item.direction_hit ? "green" : "red"}>{item.direction_hit ? "命中" : "未命中"}</Tag>
                      : <Tag color="orange">{item.evaluation_status || "pending"}</Tag> }
                  ]}
                />
              </>
            },
            {
              key: "contract",
              label: "接口与证据",
              children: <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label="协议">{capabilities.data.apiStyle}</Descriptions.Item>
                <Descriptions.Item label="端点主机">{capabilities.data.endpointHost || "-"}</Descriptions.Item>
                <Descriptions.Item label="Provider / 模型">{capabilities.data.provider || "-"} / {capabilities.data.model || "-"}</Descriptions.Item>
                <Descriptions.Item label="Prompt 版本">{capabilities.data.agentPromptVersion}</Descriptions.Item>
                <Descriptions.Item label="预测周期">{capabilities.data.evaluationHorizons.join(" / ")} 个交易日</Descriptions.Item>
                <Descriptions.Item label="安全边界">密钥仅在环境变量；无 Paper/下单接口</Descriptions.Item>
                <Descriptions.Item label="输入事实" span={2}>
                  量价与均线、PIT 基本面、官方公告/政策、市场与板块环境、数据完整性和规则结论。
                </Descriptions.Item>
              </Descriptions>
            }
          ]}
        />
        {report?.conclusionFirst && <>
          <Divider>1. 结论先行</Divider>
          <Row gutter={16}>
            <Col span={8}><Statistic title="低吸观察" value={report.conclusionFirst.lowBuy.join("、")} /></Col>
            <Col span={8}><Statistic title="小仓试错前置" value={report.conclusionFirst.smallPositionTrial.join("、")} /></Col>
            <Col span={8}><Statistic title="来源冲突" value={report.sourceConflicts?.length || 0} suffix="项" /></Col>
          </Row>
          <Typography.Paragraph style={{ marginTop: 16 }}>{report.conclusionFirst.importantChanges.join("；") || "今日无重要升级"}</Typography.Paragraph>
          <Typography.Paragraph>较上一期：{JSON.stringify(report.conclusionFirst.versusPrevious)}</Typography.Paragraph>
          {report.conclusionFirst.highRisk.length > 0 && <Alert type="warning" message="高位追涨/破位风险" description={report.conclusionFirst.highRisk.join("；")} />}
          {report.modelNarrative && <Alert type="info" style={{ marginTop: 12 }} message={`模型叙述（${report.narrativeStatus}）`} description={Object.values(report.modelNarrative).join(" ")} />}
          {(report.sourceConflicts?.length || 0) > 0 && <Alert type="warning" style={{ marginTop: 12 }} message="来源冲突（采用TuShare并降级）" description={<pre>{JSON.stringify(report.sourceConflicts, null, 2)}</pre>} />}
        </>}
        {report?.focus && <><Divider>2. 重点提醒表</Divider><Table rowKey="code" size="small" tableLayout="fixed" dataSource={report.focus} columns={stockColumns} pagination={false} /></>}
        {report?.fullPool && <><Divider>3. 全池分析表（{report.fullPool.length}只）</Divider>
          {[...new Set(report.fullPool.map((item) => item.group))].map((group) => <Card key={group} type="inner" title={group} style={{ marginBottom: 12 }}>
            <Table rowKey="code" size="small" tableLayout="fixed" dataSource={report.fullPool?.filter((item) => item.group === group)} columns={stockColumns} pagination={false} />
          </Card>)}
        </>}
        {report?.groupSummary && <><Divider>4. 板块趋势总结</Divider>
          <Typography.Title level={5}>大盘指数环境</Typography.Title>
          <Table<AshareTechMarketEnvironmentItem>
            rowKey="code" size="small" dataSource={indexEnvironment} columns={marketColumns}
            scroll={{ x: 1000 }} pagination={false}
          />
          <Typography.Title level={5} style={{ marginTop: 20 }}>科技主题板块</Typography.Title>
          {missingSectorKeywords.length > 0 && <Alert
            type="warning" showIcon style={{ marginBottom: 12 }}
            message={`板块数据缺失：${missingSectorKeywords.join("、")}`}
            description={unresolvedSectorEnvironment.map((item) =>
              `${item.keyword}：已尝试 ${(item.attemptedAliases || []).join("、")}；来源 ${(item.attemptedSources || []).join("、")}`
            ).join("；") || "所有可核验来源均未匹配，本期不补造数据。"}
          />}
          <Table<AshareTechMarketEnvironmentItem>
            rowKey={(item) => `${item.source}:${item.code}`} size="small" dataSource={sectorEnvironment}
            columns={sectorColumns} tableLayout="fixed" pagination={false}
          />
          <Typography.Title level={5} style={{ marginTop: 20 }}>观察池分组表现</Typography.Title>
          <Table<AshareTechGroupSummary>
            rowKey="group" size="small" dataSource={report.groupSummary}
            columns={groupColumns} tableLayout="fixed" pagination={false}
          />
          <Typography.Paragraph type="secondary" style={{ marginTop: 10 }}>
            分组涨跌采用观察池内个股等权平均，成交额为组内个股合计，仅用于内部环境比较，不替代正式行业指数。
          </Typography.Paragraph>
          {(report.policyEvidence?.length || 0) > 0 && <><Typography.Title level={5}>最近7日官方政策证据</Typography.Title><ul>{report.policyEvidence?.map((item) => <li key={item.url}>{item.date} {item.source}：<a href={item.url} target="_blank" rel="noreferrer">{item.title}</a></li>)}</ul></>}
        </>}
        {report?.doNotChase && <><Divider>5. 今日不追高/只观察</Divider><Table rowKey="code" size="small" tableLayout="fixed" dataSource={report.doNotChase} columns={stockColumns} pagination={false} /></>}
        {report?.nextTradingDayWatch && <><Divider>6. 下一交易日观察清单</Divider><ol>{report.nextTradingDayWatch.map((item, index) => <li key={`${item.code}-${index}`}>{item.code} {item.name}：{item.condition}；失效位 {item.invalidation ?? "数据缺失"}</li>)}</ol></>}
        {report?.finalThreeLines && <><Divider>7. 三行最终结论</Divider><Space direction="vertical"><div>最值得跟踪：{report.finalThreeLines.mostWorthTracking}</div><div>最应回避追高/警惕破位：{report.finalThreeLines.avoidChasingOrBreakdown}</div><div>总体阶段：{report.finalThreeLines.overallStage}</div></Space></>}
        {report?.disclaimer && <Alert type="info" message={report.disclaimer} style={{ marginTop: 16 }} />}
      </Card>}
      <Modal title="添加A股股票" open={addOpen} onCancel={() => setAddOpen(false)} footer={null} destroyOnHidden>
        <Form form={addForm} layout="vertical" onFinish={addStock} initialValues={{ groupKey: "core", ruleTags: [] }}>
          <FormGrid modal>
            <Form.Item name="code" label="股票代码" rules={[{ required: true }, { pattern: /^\d{6}$/, message: "请输入6位股票代码" }]}>
              <SecuritySearch market="china" placeholder="代码 / 公司名 / 拼音 / 别名" />
            </Form.Item>
            <Form.Item name="groupKey" label="加入固定分组" rules={[{ required: true }]}>
              <Select options={watchlist.data.groups.map((group) => ({ value: group.key, label: group.name }))} />
            </Form.Item>
            <Form.Item className="form-field--full" name="ruleTags" label="特殊低吸约束">
              <Checkbox.Group options={ruleTagOptions} />
            </Form.Item>
          </FormGrid>
          <Alert type="info" showIcon message="保存前必须通过 TuShare 确认为在市A股，名称由系统自动填写。" style={{ marginBottom: 16 }} />
          <FormActions><Button type="primary" htmlType="submit" loading={mutating}>验证并添加</Button></FormActions>
        </Form>
      </Modal>
    </>
  );
}
