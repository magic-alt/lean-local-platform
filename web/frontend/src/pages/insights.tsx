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
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { InsightReport, PaperSession } from "../api";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { useAsyncData } from "../hooks";
import { AshareTechInsights } from "./ashare-tech-insights";


const emptyList = { items: [], count: 0, limit: 100, offset: 0 };
const loadInsights = () => api.insights({ limit: 100 });

function statusColor(status: string) {
  if (status === "success" || status === "active" || status === "handed_off") return "green";
  if (status === "failed") return "red";
  if (status === "running") return "blue";
  return "default";
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 }}>
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

function GenericInsightsPage() {
  const capabilities = useAsyncData(api.insightCapabilities, {
    configured: false,
    provider: null,
    model: null,
    assetClasses: ["equity", "crypto", "crypto_future", "future"],
    resolutions: ["daily"],
    paperHandoffAssetClasses: ["equity", "crypto"],
    promptVersion: "lean-insights-v1"
  });
  const reports = useAsyncData(loadInsights, emptyList);
  const paperSessions = useAsyncData<PaperSession[]>(api.paperSessions, []);
  const [form] = Form.useForm();
  const assetClass = Form.useWatch("assetClass", form) || "equity";
  const market = Form.useWatch("market", form) || "china";
  const [handoffForm] = Form.useForm();
  const [selected, setSelected] = useState<InsightReport | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [handoffSubmitting, setHandoffSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadDetail = useCallback(async (id: string) => {
    try {
      setSelected(await api.insight(id));
    } catch (error) {
      message.error((error as Error).message);
    }
  }, []);

  useEffect(() => {
    if (!selected || !["queued", "running"].includes(selected.status)) return;
    const timer = window.setTimeout(() => {
      void loadDetail(selected.id);
      void reports.reload();
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [loadDetail, reports, selected]);

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
      await loadDetail(result.id);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handoff(values: { sessionId: string; targetPercent?: number }) {
    if (!selected) return;
    setHandoffSubmitting(true);
    try {
      const result = await api.handoffInsightToPaper(selected.id, values);
      setSelected(result.report);
      message.success(result.created ? "Paper signal created" : "Paper signal already exists");
      await paperSessions.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setHandoffSubmitting(false);
    }
  }

  async function deleteReport(item: InsightReport) {
    setDeletingId(item.id);
    try {
      const result = await api.deleteInsight(item.id);
      if (selected?.id === item.id) setSelected(null);
      message.success(result.paperAuditPreserved ? "Insight 已删除；已进入 Paper 的审计记录继续保留" : "Insight 历史报告已删除");
      await reports.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

  const finalSignal = selected?.signal?.finalSignal;
  const compatibleSessions = paperSessions.data.filter(
    (session) => session.mode !== "lean_walkforward"
      && !session.legacy_read_only
      && session.asset_class === selected?.asset_class
      && session.venue === selected?.venue
      && ((session.parameters?.symbols as string[] | undefined) || [session.symbol]).includes(selected?.symbol || "")
  );

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
          ? "Reports use LEAN market data only. Signals remain advisory until you explicitly hand them to Paper."
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
          <div className="field-grid">
            <Form.Item name="assetClass" label="Asset Class" rules={[{ required: true }]}>
              <Select options={capabilities.data.assetClasses.map((value) => ({ value, label: value }))} />
            </Form.Item>
            <Form.Item name="symbol" label="Symbol" rules={[{ required: true }]}><SecuritySearch assetClass={assetClass} market={market} placeholder="代码 / 公司名 / 拼音 / 别名" /></Form.Item>
            <Form.Item name="market" label="Market"><Input placeholder="china / usa" /></Form.Item>
            <Form.Item name="venue" label="Venue"><Input placeholder="china / coinbase / comex" /></Form.Item>
            <Form.Item name="asOfDate" label="As-of Date"><DateStringPicker /></Form.Item>
            <Form.Item name="lookbackBars" label="Lookback Bars"><InputNumber min={60} max={500} style={{ width: "100%" }} /></Form.Item>
            <Form.Item name="backtestRunId" label="Optional Backtest Run"><Input allowClear /></Form.Item>
          </div>
          <Button type="primary" htmlType="submit" loading={submitting} disabled={!capabilities.data.configured}>Generate Insight</Button>
        </Form>
      </Card>

      <Card title={`History (${reports.data.count})`} style={{ marginTop: 16 }}>
        <Table<InsightReport>
          rowKey="id"
          loading={reports.loading}
          dataSource={reports.data.items}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: "Created", dataIndex: "created_at" },
            { title: "Asset", dataIndex: "asset_class" },
            { title: "Venue", dataIndex: "venue" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "As Of", dataIndex: "as_of_date" },
            { title: "Status", render: (_, item) => <Tag color={statusColor(item.status)}>{item.status}</Tag> },
            { title: "Action", render: (_, item) => <Space>
              <Button size="small" onClick={() => void loadDetail(item.id)}>View</Button>
              <Popconfirm
                title={`Delete ${item.asset_class}/${item.symbol} insight?`}
                description="The report, guarded signal, task, and task log will be deleted. Paper audit records are preserved."
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
              <Divider>Technical</Divider>
              <JsonBlock value={selected.report.technical} />
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
                <Alert type="warning" showIcon message="Guardrail adjustments" description={selected.signal.guardrail.violations.join(", ")} style={{ marginTop: 16 }} />
              )}
              {finalSignal?.actionable && capabilities.data.paperHandoffAssetClasses.includes(selected.asset_class) && !selected.signal.paper_signal_id && (
                <Card type="inner" title="Confirm Paper Handoff" style={{ marginTop: 16 }}>
                  <Form form={handoffForm} layout="inline" onFinish={handoff} initialValues={{ targetPercent: Math.max(finalSignal.targetExposure, 0.01) }}>
                    <Form.Item name="sessionId" label="Paper Session" rules={[{ required: true }]}>
                      <Select style={{ width: 280 }} options={compatibleSessions.map((session) => ({ value: session.id, label: `${session.name} (${session.symbol})` }))} />
                    </Form.Item>
                    <Form.Item name="targetPercent" label="Target" rules={[{ required: ["enter", "add"].includes(finalSignal.intent) }]}>
                      <InputNumber min={0.01} max={1} step={0.05} />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" loading={handoffSubmitting} disabled={compatibleSessions.length === 0}>Create Paper Signal</Button>
                  </Form>
                </Card>
              )}
              {selected.signal.paper_signal_id && <Alert type="success" showIcon message={`Paper signal created: ${selected.signal.paper_signal_id}`} style={{ marginTop: 16 }} />}
            </>
          )}
          <Divider />
          <Alert type="info" message={selected.report?.disclaimer || "Research use only; not investment advice."} />
        </Card>
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
