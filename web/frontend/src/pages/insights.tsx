import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tabs,
  message
} from "antd";
import { DeleteOutlined, ReloadOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { InsightAgentSummary, InsightReport, InsightTechnicalReport } from "../api";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { FormActions, FormGrid, FormSection } from "../components/forms/FormLayout";
import { useAsyncData } from "../hooks";
import { AshareTechInsights } from "./ashare-tech-insights";


const emptyList = { items: [], count: 0, limit: 100, offset: 0 };
const loadInsights = () => api.insights({ limit: 100 });
const guardrailLabels: Record<string, string> = {
  invalid_stance: "模型返回了无法识别的观点，已改为中性",
  invalid_direction: "模型返回了无法识别的方向，已改为空仓",
  invalid_intent: "模型返回了无法识别的操作意图，已改为观望",
  invalid_horizon: "模型返回了无法识别的持有周期，已改为波段",
  spot_short_exposure_blocked: "现货资产不支持做空，已转换为空仓/退出建议",
  invalid_long_price_plan: "多头价格计划顺序不合理，信号不可执行",
  invalid_short_price_plan: "空头价格计划顺序不合理，信号不可执行",
  data_quality_degraded: "数据质量不足，信号已降级为观察",
  evidence_missing: "缺少可追溯证据，信号已降级为观察"
};

function statusColor(status: string) {
  if (status === "success" || status === "active") return "green";
  if (status === "failed") return "red";
  if (status === "running") return "blue";
  return "default";
}

const technicalMetricLabels: Record<string, string> = {
  latestClose: "最新收盘",
  sma20: "SMA20",
  sma50: "SMA50",
  rsi14: "RSI14",
  return5dPct: "5日收益",
  return20dPct: "20日收益",
  realizedVolatility20dPct: "20日年化波动",
  high20: "20日高点",
  low20: "20日低点",
  latestVolume: "最新成交量",
  averageVolume20: "20日平均成交量"
};
const assessmentLabels: Record<string, string> = {
  bullish: "多头",
  bearish: "空头",
  mixed: "震荡/混合",
  positive: "偏强",
  negative: "偏弱",
  neutral: "中性",
  overbought: "超买",
  oversold: "超卖",
  expanding: "放量",
  contracting: "缩量",
  normal: "正常",
  unknown: "未知"
};

function metricValue(key: string, value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  if (key.endsWith("Pct")) return `${value.toFixed(2)}%`;
  if (key.toLowerCase().includes("volume")) return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
  return value.toFixed(4).replace(/\.?0+$/, "");
}

function uncertaintyLabel(value: string) {
  if (value.startsWith("stale_daily_bars:")) return `行情已滞后 ${value.split(":")[1]}，禁止生成可执行信号`;
  if (value.startsWith("insufficient_daily_bars:")) return `历史样本不足：${value.split(":")[1]}`;
  if (value === "daily_bars_missing") return "缺少日线行情";
  if (value === "backtest_evidence_not_attached") return "未附加回测证据，本报告仅基于行情与技术指标";
  return value;
}

function TechnicalPanel({ technical }: { technical?: InsightTechnicalReport }) {
  if (!technical) return <Alert type="warning" showIcon message="Technical 数据缺失" />;
  const assessment = technical.assessment || {};
  return <>
    <Descriptions bordered size="small" column={3}>
      <Descriptions.Item label="趋势"><Tag color={assessment.trend === "bullish" ? "green" : assessment.trend === "bearish" ? "red" : "default"}>{assessmentLabels[assessment.trend || "unknown"] || assessment.trend}</Tag></Descriptions.Item>
      <Descriptions.Item label="动量">{assessmentLabels[assessment.momentum || "unknown"] || assessment.momentum}</Descriptions.Item>
      <Descriptions.Item label="量能">{assessmentLabels[assessment.volume || "unknown"] || assessment.volume}</Descriptions.Item>
      <Descriptions.Item label="20日量比">{assessment.volumeRatio20 == null ? "-" : `${assessment.volumeRatio20.toFixed(2)}×`}</Descriptions.Item>
      <Descriptions.Item label="20日区间位置">{assessment.rangePosition20Pct == null ? "-" : `${assessment.rangePosition20Pct.toFixed(2)}%`}</Descriptions.Item>
    </Descriptions>
    <Descriptions bordered size="small" column={3} style={{ marginTop: 12 }}>
      {Object.entries(technical.metrics || {}).map(([key, value]) => (
        <Descriptions.Item key={key} label={technicalMetricLabels[key] || key}>{metricValue(key, value)}</Descriptions.Item>
      ))}
    </Descriptions>
    {(technical.modelNotes?.length || 0) > 0 && <Alert type="info" showIcon message="模型补充观察" description={<ul style={{ marginBottom: 0 }}>{technical.modelNotes?.map((item) => <li key={item}>{item}</li>)}</ul>} style={{ marginTop: 12 }} />}
  </>;
}

function AgentPanel({ agent }: { agent?: InsightAgentSummary }) {
  if (!agent) return null;
  return <>
    <Alert type="info" showIcon message={`Agent 分析流程 · ${agent.workflowVersion}`} description={agent.objective} />
    <Table
      size="small"
      pagination={false}
      rowKey="key"
      dataSource={agent.steps}
      style={{ marginTop: 12 }}
      columns={[
        { title: "步骤", dataIndex: "label", width: 180 },
        { title: "状态", width: 100, render: (_, item) => <Tag color={item.status === "complete" ? "green" : "orange"}>{item.status === "complete" ? "完成" : "需注意"}</Tag> },
        { title: "审计摘要", dataIndex: "detail" }
      ]}
    />
    <Descriptions bordered size="small" column={3} style={{ marginTop: 12 }}>
      <Descriptions.Item label="证据事实">{agent.evidenceCoverage.factCount}</Descriptions.Item>
      <Descriptions.Item label="证据类型">{agent.evidenceCoverage.sourceKeys.join("、") || "-"}</Descriptions.Item>
      <Descriptions.Item label="数据源">{agent.evidenceCoverage.dataSources.join("、") || "-"}</Descriptions.Item>
      <Descriptions.Item label="最终意图">{agent.decision.intent || "-"}</Descriptions.Item>
      <Descriptions.Item label="周期">{agent.decision.horizon || "-"}</Descriptions.Item>
      <Descriptions.Item label="可执行"><Tag color={agent.decision.actionable ? "green" : "orange"}>{agent.decision.actionable ? "是" : "否"}</Tag></Descriptions.Item>
    </Descriptions>
    {agent.uncertainties.length > 0 && <Alert type="warning" showIcon message="不确定性与边界" description={<ul style={{ marginBottom: 0 }}>{agent.uncertainties.map((item) => <li key={item}>{uncertaintyLabel(item)}</li>)}</ul>} style={{ marginTop: 12 }} />}
  </>;
}

function GenericInsightsPage() {
  const capabilities = useAsyncData(api.insightCapabilities, {
    configured: false,
    provider: null,
    model: null,
    assetClasses: ["equity", "crypto", "crypto_future", "future"],
    resolutions: ["daily"],
    promptVersion: "lean-insights-v2"
  });
  const reports = useAsyncData(loadInsights, emptyList);
  const [form] = Form.useForm();
  const assetClass = Form.useWatch("assetClass", form) || "equity";
  const market = Form.useWatch("market", form) || "china";
  const [selected, setSelected] = useState<InsightReport | null>(null);
  const detailRef = useRef<HTMLDivElement | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [viewingId, setViewingId] = useState<string | null>(null);
  const [revealId, setRevealId] = useState<string | null>(null);

  const loadDetail = useCallback(async (id: string, reveal = false) => {
    if (reveal) setViewingId(id);
    try {
      setSelected(await api.insight(id));
      if (reveal) setRevealId(id);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      if (reveal) setViewingId(null);
    }
  }, []);

  useEffect(() => {
    if (!selected || selected.id !== revealId) return;
    detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setRevealId(null);
  }, [revealId, selected]);

  useEffect(() => {
    if (!selected || !["queued", "running"].includes(selected.status)) return;
    const timer = window.setInterval(() => {
      void loadDetail(selected.id);
      void reports.reload();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loadDetail, reports.reload, selected?.id, selected?.status]);

  async function submit(values: {
    symbol: string;
    assetClass: "equity" | "crypto" | "crypto_future" | "future";
    market?: string;
    venue?: string;
    asOfDate?: string;
    lookbackBars: number;
    backtestRunId?: string;
  }) {
    setSubmitting(true);
    try {
      const result = await api.createInsight({ ...values, symbol: values.symbol.trim(), resolution: "daily", dataType: "trade" });
      message.success("Insight task queued");
      await reports.reload();
      await loadDetail(result.id, true);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteReport(item: InsightReport) {
    setDeletingId(item.id);
    try {
      await api.deleteInsight(item.id);
      if (selected?.id === item.id) setSelected(null);
      message.success("Insight 历史报告已删除");
      await reports.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  const finalSignal = selected?.signal?.finalSignal;
  return (
    <>
      <div className="toolbar">
        <span />
        <Button icon={<ReloadOutlined />} onClick={() => { void capabilities.reload(); void reports.reload(); }}>Refresh</Button>
      </div>
      <Alert
        type={capabilities.data.configured ? "info" : "warning"}
        showIcon
        message={capabilities.data.configured
          ? `Structured analysis enabled: ${capabilities.data.provider} / ${capabilities.data.model}`
          : "Insights LLM is not configured"}
        description={capabilities.data.configured
          ? "Reports use LEAN market data only. Signals are advisory research outputs."
          : "Set a DeepSeek, Zhipu, Kimi, OpenAI, or Anthropic API key for both API and worker."}
        style={{ marginBottom: 16 }}
      />
      <Card title="Create Structured Insight">
        <Form
          form={form}
          layout="vertical"
          onFinish={submit}
          initialValues={{ assetClass: "equity", market: "china", venue: "china", lookbackBars: 120 }}
        >
          <FormSection title="Instrument and analysis range">
          <FormGrid>
            <Form.Item name="assetClass" label="Asset Class" rules={[{ required: true }]}>
              <Select options={capabilities.data.assetClasses.map((value) => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item className="form-field--wide" name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={assetClass} market={market} placeholder="代码 / 公司名 / 拼音 / 别名" /></Form.Item>
            <Form.Item name="market" label="Market"><Input placeholder="china / usa" /></Form.Item>
            <Form.Item name="venue" label="Venue"><Input placeholder="china / coinbase / comex" /></Form.Item>
            <Form.Item name="asOfDate" label="As-of Date"><DateStringPicker /></Form.Item>
            <Form.Item name="lookbackBars" label="Lookback Bars"><InputNumber min={60} max={500} style={{ width: "100%" }} /></Form.Item>
            <Form.Item className="form-field--wide" name="backtestRunId" label="Optional Backtest Run"><Input allowClear /></Form.Item>
          </FormGrid>
          </FormSection>
          <FormActions><Button type="primary" htmlType="submit" loading={submitting} disabled={!capabilities.data.configured}>Generate Insight</Button></FormActions>
        </Form>
      </Card>

      <Card title={`History (${reports.data.count})`} style={{ marginTop: 16 }}>
        <Table<InsightReport>
          rowKey="id"
          loading={reports.loading}
          dataSource={reports.data.items}
          rowClassName={(item) => item.id === selected?.id ? "ant-table-row-selected" : ""}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Created", dataIndex: "created_at" },
            { title: "Asset", dataIndex: "asset_class" },
            { title: "Venue", dataIndex: "venue" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "As Of", dataIndex: "as_of_date" },
            { title: "Status", render: (_, item) => <Tag color={statusColor(item.status)}>{item.status}</Tag> },
            { title: "Action", render: (_, item) => <Space>
              <Button size="small" type={selected?.id === item.id ? "primary" : "default"} loading={viewingId === item.id} onClick={() => void loadDetail(item.id, true)}>
                {selected?.id === item.id ? "Viewing" : "View"}
              </Button>
              <Popconfirm
                title={`Delete ${item.asset_class}/${item.symbol} insight?`}
                description="The report, guarded signal, task, and task log will be deleted."
                okText="Delete"
                okButtonProps={{ danger: true }}
                onConfirm={() => void deleteReport(item)}
                disabled={["created", "queued", "running", "interrupted"].includes(item.status)}
              >
                <Button danger size="small" icon={<DeleteOutlined />} loading={deletingId === item.id} disabled={["created", "queued", "running", "interrupted"].includes(item.status)}>Delete</Button>
              </Popconfirm>
            </Space> }
          ]}
        />
      </Card>

      {selected && (
        <div ref={detailRef} style={{ scrollMarginTop: 16 }}>
        <Card title={`${selected.asset_class}/${selected.venue}/${selected.symbol}`} style={{ marginTop: 16 }}>
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="Status"><Tag color={statusColor(selected.status)}>{selected.status}</Tag></Descriptions.Item>
            <Descriptions.Item label="As Of">{selected.as_of_date || "-"}</Descriptions.Item>
            <Descriptions.Item label="Model">{selected.model || "-"}</Descriptions.Item>
            <Descriptions.Item label="Fingerprint">{selected.input_fingerprint?.slice(0, 16) || "-"}</Descriptions.Item>
          </Descriptions>
          {selected.error && <Alert type="error" showIcon message={selected.error} style={{ marginTop: 16 }} />}
          {selected.report && (
            <>
              <Divider>Report</Divider>
              <h2>{selected.report.summary?.headline}</h2>
              <p>{selected.report.summary?.thesis}</p>
              <Space wrap>
                <Tag color="blue">Score {selected.report.summary?.score ?? 0}</Tag>
                <Tag>Data {selected.report.dataQuality?.level || "unknown"}</Tag>
              </Space>
              {(selected.report.dataQuality?.warnings?.length || 0) > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message="数据质量限制"
                  description={selected.report.dataQuality?.warnings?.map(uncertaintyLabel).join("；")}
                  style={{ marginTop: 12 }}
                />
              )}
              <Divider>Agent Workflow</Divider>
              <AgentPanel agent={selected.report.agent} />
              <Divider>Technical</Divider>
              <TechnicalPanel technical={selected.report.technical} />
              <Divider>Risks</Divider>
              <ul>{(selected.report.risks || []).map((item) => <li key={item}>{item}</li>)}</ul>
              <Divider>Catalysts</Divider>
              <ul>{(selected.report.catalysts || []).map((item) => <li key={item}>{item}</li>)}</ul>
              <Divider>Evidence</Divider>
              <Table
                size="small"
                pagination={false}
                rowKey={(item) => `${item.sourceKey}:${item.fact}`}
                dataSource={selected.report.evidence || []}
                columns={[{ title: "Source", dataIndex: "sourceKey" }, { title: "Fact", dataIndex: "fact" }]}
              />
            </>
          )}
          {selected.signal && (
            <>
              <Divider><SafetyCertificateOutlined /> Guarded Signal</Divider>
              <Descriptions bordered size="small" column={3}>
                <Descriptions.Item label="Stance">{finalSignal?.stance}</Descriptions.Item>
                <Descriptions.Item label="Direction">{finalSignal?.direction}</Descriptions.Item>
                <Descriptions.Item label="Intent">{finalSignal?.intent}</Descriptions.Item>
                <Descriptions.Item label="Exposure">{finalSignal?.targetExposure}</Descriptions.Item>
                <Descriptions.Item label="Confidence">{finalSignal?.confidence}</Descriptions.Item>
                <Descriptions.Item label="Actionable"><Tag color={finalSignal?.actionable ? "green" : "orange"}>{String(Boolean(finalSignal?.actionable))}</Tag></Descriptions.Item>
              </Descriptions>
              {selected.signal.guardrail.violations.length > 0 && (
                <Alert
                  type={selected.signal.guardrail.violations.every((item) => item === "spot_short_exposure_blocked") ? "info" : "warning"}
                  showIcon
                  message="信号安全调整"
                  description={selected.signal.guardrail.violations.map((item) => guardrailLabels[item] || item).join("；")}
                  style={{ marginTop: 16 }}
                />
              )}
            </>
          )}
          <Divider />
          <Alert type="info" message={selected.report?.disclaimer || "Research use only; not investment advice."} />
        </Card>
        </div>
      )}
    </>
  );
}

export function InsightsPage() {
  return <>
    <div className="toolbar"><h1 className="page-title">Insights</h1></div>
    <Tabs defaultActiveKey="ashare-tech" items={[
      { key: "ashare-tech", label: "A股科技日报", children: <AshareTechInsights /> },
      { key: "structured", label: "通用结构化 Insight", children: <GenericInsightsPage /> }
    ]} />
  </>;
}
