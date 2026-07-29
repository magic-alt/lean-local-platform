import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  message
} from "antd";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined
} from "@ant-design/icons";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../api";
import type {
  DataScope,
  DataScopeResolution,
  Project,
  ResearchRun,
  ResearchTemplate,
  ResearchWorkspace
} from "../api";
import { useAsyncData } from "../hooks";

type ResearchView = "new" | "runs" | "workspaces";

const defaultScope: DataScope = {
  asset: {
    assetClass: "equity",
    market: "china",
    venue: "china",
    resolution: "daily",
    dataType: "trade"
  },
  selection: { type: "symbols", values: ["000300.SH"] },
  time: {
    startDate: dayjs().subtract(1, "year").format("YYYY-MM-DD"),
    endDate: dayjs().format("YYYY-MM-DD"),
    asOfDate: dayjs().format("YYYY-MM-DD")
  },
  price: { adjust: "raw" },
  provider: { source: "tushare", mode: "strict", allowResearchSource: false }
};

const categoryColors: Record<string, string> = {
  market: "blue",
  data: "cyan",
  universe: "purple",
  factor: "geekblue",
  cbond: "gold",
  futures: "volcano"
};

function viewFromPath(pathname: string): ResearchView {
  if (pathname.includes("/workspaces")) return "workspaces";
  if (pathname.includes("/runs")) return "runs";
  return "new";
}

function statusTag(status: string) {
  const color = status === "success" || status === "running"
    ? "green"
    : status === "failed"
      ? "red"
      : status === "cancelled" || status === "stopped"
        ? "default"
        : "blue";
  return <Tag color={color}>{status.toUpperCase()}</Tag>;
}

function concise(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(4);
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function TemplateParameters({ template }: { template: string }) {
  if (template === "universe-pit") {
    return (
      <>
        <Form.Item name={["parameters", "universeCode"]} label="指数股票池">
          <Select options={["CSI300", "CSI500", "CSI1000", "SSE50", "STAR50", "ALL_A"].map((value) => ({ value, label: value }))} />
        </Form.Item>
        <Form.Item name={["parameters", "tradable"]} valuePropName="checked"><Checkbox>仅保留当日可交易证券</Checkbox></Form.Item>
      </>
    );
  }
  if (template === "factor-evaluation") {
    return (
      <>
        <Form.Item name={["parameters", "factorNames"]} label="因子" rules={[{ required: true }]}>
          <Select mode="tags" tokenSeparators={[","]} placeholder="momentum_20, value_pe" />
        </Form.Item>
        <Form.Item name={["parameters", "universeCode"]} label="股票池"><Input /></Form.Item>
        <Form.Item name={["parameters", "forwardDays"]} label="前瞻周期"><InputNumber min={1} max={252} /></Form.Item>
        <Form.Item name={["parameters", "quantiles"]} label="分位数"><InputNumber min={2} max={20} /></Form.Item>
        <Form.Item name={["parameters", "engine"]} label="计算引擎">
          <Select options={["python", "duckdb", "polars"].map((value) => ({ value, label: value }))} />
        </Form.Item>
      </>
    );
  }
  if (template === "cbond-double-low") {
    return (
      <>
        <Form.Item name={["parameters", "maxDoubleLow"]} label="双低上限"><InputNumber min={0} /></Form.Item>
        <Form.Item name={["parameters", "excludeCallRisk"]} valuePropName="checked"><Checkbox>排除强赎风险</Checkbox></Form.Item>
      </>
    );
  }
  if (template === "futures-continuous") {
    return (
      <>
        <Form.Item name={["parameters", "product"]} label="品种"><Input placeholder="RB" /></Form.Item>
        <Form.Item name={["parameters", "exchange"]} label="交易所"><Input placeholder="SHFE" /></Form.Item>
        <Form.Item name={["parameters", "adjustment"]} label="连续处理">
          <Select options={[
            { value: "backward_ratio", label: "后复权比例" },
            { value: "backward_difference", label: "后复权价差" },
            { value: "none", label: "不复权" }
          ]} />
        </Form.Item>
      </>
    );
  }
  return <Alert type="info" showIcon message="该模板无需额外参数，数据范围就是完整配置。" />;
}

function ResultPanel({ run }: { run?: ResearchRun }) {
  const result = run?.result;
  if (!run) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="运行分析后，结果会固定在这里并进入历史记录" />;
  if (run.status === "failed") return <Alert type="error" showIcon message="分析失败" description={run.error} />;
  if (!result) return <Alert type="info" showIcon message={`任务状态：${run.status}`} />;
  const summary = Object.entries(result.summary || {}).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value));
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      {(result.warnings || []).map((warning) => <Alert key={warning} type="warning" showIcon message={warning} />)}
      <div className="research-summary-grid">
        {summary.slice(0, 6).map(([key, value]) => (
          <Card size="small" key={key}><Statistic title={key} value={concise(value)} /></Card>
        ))}
      </div>
      {(result.tables || []).map((table) => (
        <Card key={table.name} size="small" title={table.name} extra={table.truncated ? <Tag>预览前 1000 行</Tag> : null}>
          <Table
            size="small"
            rowKey={(_, index) => String(index)}
            scroll={{ x: "max-content" }}
            pagination={{ pageSize: 20, showSizeChanger: false }}
            dataSource={table.rows}
            columns={table.columns.map((column) => ({
              title: column,
              dataIndex: column,
              key: column,
              render: concise
            }))}
          />
        </Card>
      ))}
    </Space>
  );
}

function NewResearch({
  templates,
  onCreated
}: {
  templates: ResearchTemplate[];
  onCreated: (run: ResearchRun) => void;
}) {
  const [form] = Form.useForm();
  const [selected, setSelected] = useState("market-eda");
  const [resolution, setResolution] = useState<DataScopeResolution>();
  const [busy, setBusy] = useState<"preview" | "run">();
  const [latestRun, setLatestRun] = useState<ResearchRun>();
  const current = templates.find((item) => item.key === selected);

  useEffect(() => {
    const parameters = current?.parameterSchema || {};
    const templateDefaults: Record<string, unknown> = {
      template: selected,
      name: current?.name,
      parameters
    };
    if (selected === "universe-pit" || selected === "factor-evaluation") {
      Object.assign(templateDefaults, {
        asset: { ...defaultScope.asset, assetClass: "equity" },
        selectionType: "universe",
        selectionValues: selected === "universe-pit" ? "CSI300" : "ALL_A"
      });
    } else if (selected === "cbond-double-low") {
      Object.assign(templateDefaults, {
        asset: { ...defaultScope.asset, assetClass: "cbond" },
        selectionType: "all",
        selectionValues: ""
      });
    } else if (selected === "futures-continuous") {
      Object.assign(templateDefaults, {
        asset: { ...defaultScope.asset, assetClass: "future", market: "china", venue: "SHFE" },
        selectionType: "products",
        selectionValues: "RB"
      });
    } else {
      Object.assign(templateDefaults, {
        asset: defaultScope.asset,
        selectionType: defaultScope.selection.type,
        selectionValues: defaultScope.selection.values.join(", ")
      });
    }
    form.setFieldsValue(templateDefaults);
    setResolution(undefined);
  }, [current, form, selected]);

  function payloadFrom(values: Record<string, any>) {
    const valuesText = String(values.selectionValues || "");
    const scope: DataScope = {
      asset: values.asset,
      selection: {
        type: values.selectionType,
        values: valuesText.split(/[\s,，]+/).map((value) => value.trim()).filter(Boolean)
      },
      time: values.time,
      price: values.price,
      provider: values.provider
    };
    return { template: selected, name: values.name, scope, parameters: values.parameters || {} };
  }

  async function preflight() {
    try {
      setBusy("preview");
      const values = await form.validateFields();
      setResolution(await api.previewResearchRun(payloadFrom(values)));
      message.success("数据预检完成");
    } catch (error) {
      if (error instanceof Error) message.error(error.message);
    } finally {
      setBusy(undefined);
    }
  }

  async function run() {
    try {
      setBusy("run");
      const values = await form.validateFields();
      const payload = payloadFrom(values);
      const preview = resolution || await api.previewResearchRun(payload);
      setResolution(preview);
      if ((preview.blocking || []).length) throw new Error(`预检未通过：${preview.blocking?.join(", ")}`);
      const created = await api.createResearchRun(payload);
      setLatestRun(created);
      onCreated(created);
      if (created.status === "success") message.success("研究分析已完成并固化");
      else message.warning(created.error || `任务状态：${created.status}`);
    } catch (error) {
      if (error instanceof Error) message.error(error.message);
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <div className="research-workbench">
      <aside className="research-template-rail" aria-label="研究模板">
        <div className="research-section-label">分析模板</div>
        {templates.map((item) => (
          <button
            type="button"
            key={item.key}
            className={`research-template ${selected === item.key ? "is-active" : ""}`}
            onClick={() => setSelected(item.key)}
          >
            <span><Tag color={categoryColors[item.category]}>{item.category}</Tag>{item.name}</span>
            <small>{item.description}</small>
          </button>
        ))}
        <Alert className="research-boundary-note" type="info" showIcon message="研究 ≠ 回测" description="这里只做数据、信号与统计分析；订单、持仓、资金、费用和交易盈亏统一进入回测。" />
      </aside>

      <main className="research-config-panel">
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            template: selected,
            name: "市场研究",
            asset: defaultScope.asset,
            selectionType: defaultScope.selection.type,
            selectionValues: defaultScope.selection.values.join(", "),
            time: defaultScope.time,
            price: defaultScope.price,
            provider: defaultScope.provider,
            parameters: {}
          }}
        >
          <Card size="small" title={<><ExperimentOutlined /> {current?.name || "新建分析"}</>} className="research-config-card">
            <div className="research-form-grid">
              <Form.Item name="name" label="研究名称" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name={["asset", "assetClass"]} label="资产类别">
                <Select options={[
                  { value: "equity", label: "股票" },
                  { value: "cbond", label: "可转债" },
                  { value: "future", label: "期货" },
                  { value: "crypto", label: "数字资产" }
                ]} />
              </Form.Item>
              <Form.Item name={["asset", "market"]} label="市场"><Input /></Form.Item>
              <Form.Item name={["asset", "venue"]} label="场所 / 交易所"><Input /></Form.Item>
              <Form.Item name={["asset", "resolution"]} label="频率">
                <Select options={["daily", "hour", "minute"].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name={["price", "adjust"]} label="价格口径">
                <Select options={["raw", "qfq", "hfq"].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Form.Item name="selectionType" label="选择方式">
                <Select options={[
                  { value: "symbols", label: "证券代码" },
                  { value: "universe", label: "PIT 股票池" },
                  { value: "products", label: "期货品种" },
                  { value: "all", label: "全部" }
                ]} />
              </Form.Item>
              <Form.Item name="selectionValues" label="代码 / 股票池 / 品种"><Input placeholder="000001.SZ, 600000.SH" /></Form.Item>
              <Form.Item name={["time", "startDate"]} label="开始日期"><Input type="date" /></Form.Item>
              <Form.Item name={["time", "endDate"]} label="结束日期"><Input type="date" /></Form.Item>
              <Form.Item name={["time", "asOfDate"]} label="PIT 截止日"><Input type="date" /></Form.Item>
              <Form.Item name={["provider", "source"]} label="数据源"><Input /></Form.Item>
              <Form.Item name={["provider", "mode"]} label="来源策略">
                <Select options={[
                  { value: "strict", label: "严格使用指定源" },
                  { value: "fallback", label: "允许认证回退" }
                ]} />
              </Form.Item>
              <Form.Item name={["provider", "allowResearchSource"]} valuePropName="checked">
                <Checkbox>允许研究 / 非认证来源</Checkbox>
              </Form.Item>
            </div>
          </Card>
          <Card size="small" title="模板参数" className="research-config-card">
            <div className="research-form-grid"><TemplateParameters template={selected} /></div>
          </Card>
          <Space>
            <Button icon={<DatabaseOutlined />} loading={busy === "preview"} onClick={() => void preflight()}>数据预检</Button>
            <Button type="primary" icon={<PlayCircleOutlined />} loading={busy === "run"} onClick={() => void run()}>运行并固化结果</Button>
          </Space>
        </Form>
      </main>

      <aside className="research-readiness-panel">
        <Card size="small" title="数据就绪度" extra={resolution ? (resolution.ready ? <Tag color="green">READY</Tag> : <Tag color="red">BLOCKED</Tag>) : <Tag>待检查</Tag>}>
          {resolution ? (
            <Space direction="vertical" size={10} style={{ width: "100%" }}>
              <div className="research-readiness-row"><span>来源</span><strong>{resolution.source}</strong></div>
              <div className="research-readiness-row"><span>记录</span><strong>{Number(resolution.coverage.rows || 0).toLocaleString()}</strong></div>
              <div className="research-readiness-row"><span>证券</span><strong>{Number(resolution.coverage.symbols || 0).toLocaleString()}</strong></div>
              <div className="research-readiness-row"><span>覆盖</span><strong>{resolution.coverage.first_date || "—"} → {resolution.coverage.last_date || "—"}</strong></div>
              <Tooltip title={resolution.scopeHash}><div className="research-hash">SCOPE {resolution.scopeHash.slice(0, 12)}</div></Tooltip>
              <Tooltip title={resolution.dataFingerprint}><div className="research-hash">DATA {resolution.dataFingerprint.slice(0, 12)}</div></Tooltip>
            </Space>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="先运行数据预检" />}
        </Card>
        <Card size="small" title="最新结果"><ResultPanel run={latestRun} /></Card>
      </aside>
    </div>
  );
}

function RunHistory({ runs, reload }: { runs: ResearchRun[]; reload: () => void }) {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<ResearchRun>();

  async function handoff(item: ResearchRun) {
    const draft = await api.researchBacktestDraft(item.id);
    navigate(`/backtests?researchRunId=${encodeURIComponent(item.id)}&scope=${draft.target === "batch" ? "batch" : "single"}`);
  }

  return (
    <div className="research-history-layout">
      <Card size="small" title="Research Runs" extra={<Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>}>
        <Table
          className="research-runs-table"
          size="small"
          rowKey="id"
          dataSource={runs}
          tableLayout="fixed"
          scroll={{ x: 1210 }}
          pagination={{ pageSize: 20 }}
          onRow={(record) => ({ onClick: () => setSelected(record) })}
          columns={[
            { title: "状态", dataIndex: "status", width: 100, render: statusTag },
            {
              title: "名称",
              dataIndex: "name",
              width: 300,
              render: (value) => {
                const name = value ? String(value) : "—";
                return <Tooltip title={name}><span className="research-run-name">{name}</span></Tooltip>;
              }
            },
            { title: "模板", dataIndex: "template_key", width: 160 },
            { title: "数据指纹", dataIndex: "data_fingerprint", width: 140, render: (value) => value ? <code>{String(value).slice(0, 12)}</code> : "—" },
            { title: "创建时间", dataIndex: "created_at", width: 170 },
            {
              title: "操作",
              key: "actions",
              width: 340,
              render: (_, item) => (
                <Space onClick={(event) => event.stopPropagation()}>
                  <Button size="small" icon={<ArrowRightOutlined />} disabled={item.status !== "success"} onClick={() => void handoff(item)}>转回测</Button>
                  <Button size="small" icon={<CodeOutlined />} disabled={item.status !== "success"} onClick={async () => {
                    const snapshot = await api.createResearchSnapshot(item.scope);
                    await navigator.clipboard?.writeText(snapshot.snapshotId);
                    message.success(`只读快照已生成：${snapshot.snapshotId.slice(0, 12)}（ID 已复制）`);
                  }}>快照</Button>
                  <Button size="small" icon={<DownloadOutlined />} href={api.researchRunExportUrl(item.id)}>CSV</Button>
                  <Button size="small" onClick={async () => { await api.retryResearchRun(item.id); reload(); }}>重试</Button>
                  <Button size="small" danger icon={<DeleteOutlined />} onClick={async () => { await api.deleteResearchRun(item.id); reload(); }}>删除</Button>
                </Space>
              )
            }
          ]}
        />
      </Card>
      <Card size="small" title={selected ? selected.name : "运行详情"}>
        <ResultPanel run={selected} />
      </Card>
    </div>
  );
}

function Workspaces({ projects, workspaces, reload }: { projects: Project[]; workspaces: ResearchWorkspace[]; reload: () => void }) {
  const [open, setOpen] = useState(false);
  const [logs, setLogs] = useState("");
  const [form] = Form.useForm();

  async function create() {
    const values = await form.validateFields();
    await api.startResearch(values);
    setOpen(false);
    form.resetFields();
    reload();
  }

  return (
    <Card
      size="small"
      title="Notebook Workspaces"
      extra={<Space><Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button><Button type="primary" icon={<CodeOutlined />} onClick={() => setOpen(true)}>新建工作区</Button></Space>}
    >
      <Alert
        type="info"
        showIcon
        message="Workspace 是交互式 Notebook 环境，不是 Research Run 的另一个名字。"
        description="Run 固定输入和结果、适合审计与复用；Workspace 用于探索。容器禁用网络，数据以只读快照方式提供。"
        style={{ marginBottom: 16 }}
      />
      <Table
        size="small"
        rowKey="id"
        dataSource={workspaces}
        scroll={{ x: "max-content" }}
        columns={[
          { title: "状态", dataIndex: "status", width: 110, render: statusTag },
          { title: "项目", dataIndex: "project_name" },
          { title: "端口", dataIndex: "port", width: 90 },
          { title: "快照", dataIndex: "snapshot_id", render: (value) => value ? <code>{String(value).slice(0, 12)}</code> : "未绑定" },
          { title: "创建时间", dataIndex: "created_at", width: 180 },
          {
            title: "操作",
            key: "actions",
            width: 330,
            render: (_, item) => (
              <Space>
                {item.url && <Button size="small" href={item.url} target="_blank">打开</Button>}
                <Button size="small" onClick={async () => { const result = await api.researchLogs(item.id); setLogs(result.logs); }}>日志</Button>
                {item.status === "running"
                  ? <Button size="small" onClick={async () => { await api.stopResearch(item.id); reload(); }}>停止</Button>
                  : <Button size="small" onClick={async () => { await api.restartResearch(item.id); reload(); }}>重启</Button>}
                <Button size="small" danger icon={<DeleteOutlined />} onClick={async () => { await api.deleteResearch(item.id); reload(); }}>删除</Button>
              </Space>
            )
          }
        ]}
      />
      <Modal title="新建 Notebook Workspace" open={open} onCancel={() => setOpen(false)} onOk={() => void create()}>
        <Form form={form} layout="vertical">
          <Form.Item name="projectId" label="研究项目" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={projects.map((project) => ({ value: project.id, label: project.name }))} />
          </Form.Item>
          <Form.Item name="port" label="端口（可选）"><InputNumber min={1024} max={65535} /></Form.Item>
          <Form.Item name="snapshotId" label="冻结数据快照 ID" rules={[{ required: true, message: "Workspace 必须绑定冻结快照" }]}>
            <Input placeholder="从 Research Run 生成并粘贴快照 ID" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title="Workspace 日志" open={Boolean(logs)} footer={null} onCancel={() => setLogs("")} width={900}>
        <pre className="research-log">{logs}</pre>
      </Modal>
    </Card>
  );
}

export function ResearchPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const view = viewFromPath(location.pathname);
  const templates = useAsyncData(api.researchTemplates, { items: [], count: 0 });
  const runs = useAsyncData(api.researchRuns, []);
  const projects = useAsyncData(api.projects, []);
  const workspaces = useAsyncData(api.researchSessions, []);
  const activeWorkspaces = workspaces.data.filter((item) => ["queued", "starting", "running"].includes(item.status)).length;

  useEffect(() => {
    if (!activeWorkspaces) return;
    const timer = window.setInterval(() => { void workspaces.reload(); }, 4000);
    return () => window.clearInterval(timer);
  }, [activeWorkspaces, workspaces.reload]);

  const options = useMemo(() => [
    { label: "新建分析", value: "new", icon: <ExperimentOutlined /> },
    { label: `运行历史 ${runs.data.length}`, value: "runs", icon: <CheckCircleOutlined /> },
    { label: `Notebook ${activeWorkspaces ? `· ${activeWorkspaces} 活跃` : ""}`, value: "workspaces", icon: <CloudServerOutlined /> }
  ], [activeWorkspaces, runs.data.length]);

  return (
    <div className="research-page">
      <div className="research-page-header">
        <div>
          <div className="research-eyebrow">RESEARCH WORKBENCH</div>
          <h1 className="page-title">研究工作台</h1>
          <p>用统一数据范围完成可复现分析；验证交易执行时，一键把同一数据口径交给回测。</p>
        </div>
        <div className="research-flow">
          <span className="is-current">1 研究假设</span><ArrowRightOutlined /><span>2 回测验证</span><ArrowRightOutlined /><span>3 模拟交易</span>
        </div>
      </div>
      <Segmented
        block
        className="research-navigation"
        options={options}
        value={view}
        onChange={(value) => navigate(value === "new" ? "/research" : `/research/${value}`)}
      />
      {view === "new" && <NewResearch templates={templates.data.items} onCreated={() => void runs.reload()} />}
      {view === "runs" && <RunHistory runs={runs.data} reload={() => void runs.reload()} />}
      {view === "workspaces" && (
        <Workspaces projects={projects.data} workspaces={workspaces.data} reload={() => void workspaces.reload()} />
      )}
    </div>
  );
}
