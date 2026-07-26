import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message
} from "antd";
import {
  AppstoreOutlined,
  BarsOutlined,
  CopyOutlined,
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SwapOutlined
} from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api } from "../api";
import type {
  PaperAccount,
  PaperAccountComparison,
  PaperAccountOverview,
  PaperBacktestCandidate,
  PaperDeployment,
  PaperExecutionCycle,
  PaperPosition,
  PaperSignal,
  Project
} from "../api";


const money = (value?: string | number | null, currency = "CNY") =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(Number(value || 0));

const percent = (value?: string | number | null) =>
  `${(Number(value || 0) * 100).toFixed(2)}%`;

const statusColor: Record<string, string> = {
  active: "green",
  paused: "gold",
  waiting_data: "cyan",
  running: "blue",
  queued: "geekblue",
  finalizing: "purple",
  error: "red",
  failed: "red",
  archived: "default",
  draft: "default",
  succeeded: "green",
  skipped: "default",
  healthy: "green",
  stale: "gold"
};

function StatusBadge({ value }: { value?: string | null }) {
  const normalized = String(value || "unknown");
  return <Tag color={statusColor[normalized] || "default"}>{normalized.replaceAll("_", " ").toUpperCase()}</Tag>;
}

function Metric({
  title,
  value,
  kind = "money",
  currency = "CNY"
}: {
  title: string;
  value?: string | number | null;
  kind?: "money" | "percent" | "number" | "text";
  currency?: string;
}) {
  const rendered = kind === "money"
    ? money(value, currency)
    : kind === "percent"
      ? percent(value)
      : kind === "number"
        ? String(value ?? 0)
        : String(value ?? "—");
  return <Statistic title={title} value={rendered} />;
}

function AccountCard({
  account,
  selected,
  onSelect,
  onDelete
}: {
  account: PaperAccount;
  selected: boolean;
  onSelect: (checked: boolean) => void;
  onDelete: () => Promise<void>;
}) {
  return (
    <Card
      className="paper-account-card"
      title={(
        <Space>
          <Checkbox checked={selected} onChange={(event) => onSelect(event.target.checked)} />
          <Link to={`/paper/accounts/${account.id}`}>{account.name}</Link>
        </Space>
      )}
      extra={(
        <Space>
          <StatusBadge value={account.status} />
          <Popconfirm
            title="删除 Paper 账户？"
            description="账户、执行周期、订单、成交和账本记录将永久删除。"
            okText="删除"
            okButtonProps={{ danger: true }}
            disabled={account.status === "active"}
            onConfirm={onDelete}
          >
            <Button
              aria-label={`删除 ${account.name}`}
              danger
              size="small"
              icon={<DeleteOutlined />}
              disabled={account.status === "active"}
            />
          </Popconfirm>
        </Space>
      )}
    >
      <div className="paper-account-card__metrics">
        <Metric title="总资产" value={account.total_equity} currency={account.base_currency} />
        <Metric title="可用现金" value={account.available_cash} currency={account.base_currency} />
        <Metric title="持仓市值" value={account.market_value} currency={account.base_currency} />
        <Metric title="当日盈亏" value={account.daily_pnl} currency={account.base_currency} />
        <Metric title="累计收益" value={account.cumulative_return} kind="percent" />
        <Metric title="超额收益" value={account.excess_return} kind="percent" />
      </div>
      <Divider />
      <Space wrap>
        <Tag>{account.primary_strategy || "未绑定策略"}</Tag>
        <Badge status={account.health_status === "healthy" ? "success" : "warning"} text={account.health_status || "unknown"} />
        <span>持仓 {account.position_count || 0}</span>
        <span>信号 {account.pending_signal_count || 0}</span>
        <span>待成交 {account.pending_order_count || 0}</span>
      </Space>
      <div className="paper-account-card__schedule">
        最近成功：{account.last_successful_trading_date || "—"} · 下次运行：{account.next_scheduled_at || "—"}
      </div>
    </Card>
  );
}

function AccountWizard({
  open,
  onClose,
  onCreated
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [step, setStep] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [candidates, setCandidates] = useState<PaperBacktestCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const projectId = Form.useWatch("projectId", form);
  const candidateId = Form.useWatch("sourceBacktestId", form);
  const selectedCandidate = candidates.find((item) => item.id === candidateId);

  useEffect(() => {
    if (!open) return;
    api.projects().then(setProjects).catch((error) => message.error((error as Error).message));
  }, [open]);

  useEffect(() => {
    if (!projectId) {
      setCandidates([]);
      return;
    }
    let current = true;
    api.paperCandidates(projectId)
      .then((items) => {
        if (current) setCandidates(items);
      })
      .catch((error) => message.error((error as Error).message));
    return () => {
      current = false;
    };
  }, [projectId]);

  async function advance() {
    const stepFields = [
      ["name", "marketScope", "baseCurrency", "initialCash", "benchmarkSymbol"],
      ["projectId", "sourceBacktestId"],
      ["automatic", "marketTimezone", "signalMode"],
      ["maxPositions", "maxPositionWeight", "cashFloor", "maxOrderAmount", "maxDailyTurnover"]
    ][step];
    if (stepFields) await form.validateFields(stepFields);
    setStep((value) => Math.min(value + 1, 4));
  }

  async function create() {
    const values = await form.validateFields();
    setBusy(true);
    try {
      const account = await api.createPaperAccount({
        name: values.name,
        description: values.description,
        marketScope: "china",
        baseCurrency: "CNY",
        initialCash: String(values.initialCash),
        benchmarkSymbol: values.benchmarkSymbol,
        riskConfig: {
          maxPositions: values.maxPositions,
          maxPositionWeight: String(values.maxPositionWeight),
          cashFloor: String(values.cashFloor),
          maxOrderAmount: String(values.maxOrderAmount),
          maxDailyTurnover: String(values.maxDailyTurnover),
          blacklist: values.blacklist || [],
          observeOnly: values.observeOnly === true,
          ashareRules: { t1: true, st: true, suspension: true, priceLimit: true, boardLot: true },
          feeModelVersion: "paper-ashare-v2",
          slippageModelVersion: "paper-next-open-v2"
        }
      });
      await api.createPaperDeployment(account.id, {
        name: values.deploymentName || `${values.name} 主策略`,
        projectId: values.projectId,
        sourceBacktestId: values.sourceBacktestId,
        scheduleType: values.automatic ? "market_daily" : "manual",
        scheduleExpression: "after_close+00:45",
        marketTimezone: "Asia/Shanghai",
        executionTiming: "next_open",
        signalMode: values.signalMode,
        isPrimary: true
      });
      if (values.automatic) await api.paperAccountAction(account.id, "activate");
      message.success("模拟账户、Opening Ledger 和冻结策略部署已创建");
      form.resetFields();
      setStep(0);
      onClose();
      await onCreated();
    } catch (error) {
      message.error(`创建失败：${(error as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const steps = [
    {
      title: "账户",
      content: (
        <div className="paper-wizard-grid">
          <Form.Item name="name" label="账户名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="说明"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="marketScope" label="市场" rules={[{ required: true }]}>
            <Select options={[{ value: "china", label: "中国 A 股（日线）" }]} />
          </Form.Item>
          <Form.Item name="baseCurrency" label="基准币种" rules={[{ required: true }]}>
            <Select options={[{ value: "CNY", label: "CNY 人民币" }]} />
          </Form.Item>
          <Form.Item name="initialCash" label="初始资金" rules={[{ required: true }]}>
            <InputNumber min={1} precision={2} stringMode style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="benchmarkSymbol" label="Benchmark" rules={[{ required: true }]}><Input /></Form.Item>
        </div>
      )
    },
    {
      title: "策略",
      content: (
        <>
          <Alert
            type="info"
            showIcon
            message="只显示成功、认证、验证通过并具有冻结项目快照的 Backtest。"
            style={{ marginBottom: 16 }}
          />
          <Form.Item name="projectId" label="Project" rules={[{ required: true }]}>
            <Select
              options={projects.map((item) => ({ value: item.id, label: item.display_name || item.name }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="sourceBacktestId" label="可信 Backtest Candidate" rules={[{ required: true }]}>
            <Select
              disabled={!projectId}
              options={candidates.map((item) => ({
                value: item.id,
                label: `${item.name || item.symbol} · ${item.start} → ${item.end}`
              }))}
            />
          </Form.Item>
          {selectedCandidate && (
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="标的">{selectedCandidate.symbol}</Descriptions.Item>
              <Descriptions.Item label="区间">{selectedCandidate.start} → {selectedCandidate.end}</Descriptions.Item>
              <Descriptions.Item label="策略版本">{selectedCandidate.strategyVersionId || "fingerprint 固定"}</Descriptions.Item>
              <Descriptions.Item label="Admission">{selectedCandidate.admissionStage || "validation passed"}</Descriptions.Item>
              <Descriptions.Item label="参数哈希" span={2}>{selectedCandidate.parameterHash || "—"}</Descriptions.Item>
            </Descriptions>
          )}
        </>
      )
    },
    {
      title: "执行",
      content: (
        <>
          <Alert
            type="warning"
            showIcon
            message="T 收盘后生成信号，委托进入 pending next session，按 T+1 认证开盘价与 A 股约束模拟成交。"
            style={{ marginBottom: 16 }}
          />
          <Form.Item name="automatic" label="自动运行" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="marketTimezone" label="市场时区"><Input disabled /></Form.Item>
          <Form.Item name="signalMode" label="模式" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value="paper_execute">Paper Execute</Radio.Button>
              <Radio.Button value="signal_only">Signal Only</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="deploymentName" label="Deployment 名称"><Input /></Form.Item>
        </>
      )
    },
    {
      title: "风险",
      content: (
        <div className="paper-wizard-grid">
          <Form.Item name="maxPositions" label="最大持仓数" rules={[{ required: true }]}><InputNumber min={1} /></Form.Item>
          <Form.Item name="maxPositionWeight" label="单标的最大权重" rules={[{ required: true }]}><InputNumber min={0} max={1} step={0.01} /></Form.Item>
          <Form.Item name="cashFloor" label="现金下限" rules={[{ required: true }]}><InputNumber min={0} stringMode /></Form.Item>
          <Form.Item name="maxOrderAmount" label="最大订单金额" rules={[{ required: true }]}><InputNumber min={1} stringMode /></Form.Item>
          <Form.Item name="maxDailyTurnover" label="最大日换手" rules={[{ required: true }]}><InputNumber min={0} max={5} step={0.05} /></Form.Item>
          <Form.Item name="blacklist" label="Blacklist"><Select mode="tags" tokenSeparators={[","]} /></Form.Item>
          <Form.Item name="observeOnly" label="Observe only" valuePropName="checked"><Switch /></Form.Item>
          <Alert
            type="info"
            message="ST、停牌、涨跌停、整手、T+1、费用与滑点规则默认 fail-closed。"
            className="paper-wizard-grid__wide"
          />
        </div>
      )
    },
    {
      title: "确认",
      content: (
        <Descriptions bordered column={1}>
          <Descriptions.Item label="账户">{form.getFieldValue("name")}</Descriptions.Item>
          <Descriptions.Item label="初始资金">{money(form.getFieldValue("initialCash"))}</Descriptions.Item>
          <Descriptions.Item label="Benchmark">{form.getFieldValue("benchmarkSymbol")}</Descriptions.Item>
          <Descriptions.Item label="策略快照">{candidateId || "—"}</Descriptions.Item>
          <Descriptions.Item label="执行">T close signal → T+1 certified next-open</Descriptions.Item>
          <Descriptions.Item label="配置冻结">
            创建后生成 strategy、dataset、risk 与 deployment fingerprints；修改参数将创建新 deployment version。
          </Descriptions.Item>
        </Descriptions>
      )
    }
  ];

  return (
    <Modal
      open={open}
      width={820}
      title="新建模拟账户"
      onCancel={onClose}
      footer={(
        <Space>
          {step > 0 && <Button onClick={() => setStep((value) => value - 1)}>上一步</Button>}
          {step < 4
            ? <Button type="primary" onClick={advance}>下一步</Button>
            : <Button type="primary" loading={busy} onClick={create}>创建并冻结</Button>}
        </Space>
      )}
    >
      <Steps current={step} items={steps.map((item) => ({ title: item.title }))} style={{ marginBottom: 24 }} />
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          marketScope: "china",
          baseCurrency: "CNY",
          initialCash: "1000000",
          benchmarkSymbol: "000300",
          automatic: true,
          marketTimezone: "Asia/Shanghai",
          signalMode: "paper_execute",
          maxPositions: 10,
          maxPositionWeight: 0.2,
          cashFloor: "50000",
          maxOrderAmount: "200000",
          maxDailyTurnover: 0.5,
          observeOnly: false
        }}
      >
        {steps[step].content}
      </Form>
    </Modal>
  );
}

function ComparisonModal({
  open,
  accountIds,
  onClose
}: {
  open: boolean;
  accountIds: string[];
  onClose: () => void;
}) {
  const [result, setResult] = useState<PaperAccountComparison | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open || accountIds.length < 2) return;
    setLoading(true);
    api.comparePaperAccounts(accountIds)
      .then(setResult)
      .catch((error) => message.error((error as Error).message))
      .finally(() => setLoading(false));
  }, [accountIds, open]);
  return (
    <Modal open={open} width={1000} title="多账户收益比较" footer={null} onCancel={onClose}>
      {loading ? <Spin /> : result && (
        <>
          {!result.comparable && (
            <Alert type="warning" showIcon message="账户币种不同，收益金额不可静默合并。" />
          )}
          <Descriptions size="small" column={3} style={{ margin: "16px 0" }}>
            <Descriptions.Item label="统一起点">{result.comparisonStart || "共同可用首日"}</Descriptions.Item>
            <Descriptions.Item label="估值日期">{result.valuationDate || "尚无估值"}</Descriptions.Item>
            <Descriptions.Item label="币种">{result.currencies.join(", ")}</Descriptions.Item>
          </Descriptions>
          <Table
            rowKey="accountId"
            pagination={false}
            scroll={{ x: 900 }}
            dataSource={result.accounts}
            columns={[
              { title: "账户", dataIndex: "name", fixed: "left" },
              { title: "累计收益", dataIndex: "cumulativeReturn", render: percent },
              { title: "基准收益", dataIndex: "benchmarkReturn", render: percent },
              { title: "超额收益", dataIndex: "excessReturn", render: percent },
              { title: "换手率", dataIndex: "turnover", render: percent },
              { title: "交易次数", dataIndex: "tradeCount" },
              { title: "现金比例", dataIndex: "cashRatio", render: percent },
              { title: "持仓数", dataIndex: "positionCount" },
              { title: "风险拒单", dataIndex: "riskRejectCount" },
              { title: "最后运行", dataIndex: "lastRunDate", render: (value) => value || "—" }
            ]}
          />
        </>
      )}
    </Modal>
  );
}

export function PaperAccountsPage() {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [view, setView] = useState<"cards" | "table">("cards");
  const [selected, setSelected] = useState<string[]>([]);
  const [comparisonOpen, setComparisonOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.paperAccounts({ keyword, status });
      setAccounts(result.items);
      setSelected((ids) => ids.filter((id) => result.items.some((account) => account.id === id)));
    } catch (error) {
      message.error(`账户列表加载失败：${(error as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [keyword, status]);

  useEffect(() => {
    void load();
  }, [load]);

  function select(id: string, checked: boolean) {
    setSelected((items) => checked ? [...new Set([...items, id])] : items.filter((item) => item !== id));
  }

  async function deleteAccount(account: PaperAccount) {
    try {
      await api.deletePaperAccount(account.id);
      message.success(`账户“${account.name}”已删除`);
      await load();
    } catch (error) {
      message.error(`账户删除失败：${(error as Error).message}`);
    }
  }

  return (
    <>
      <div className="toolbar paper-toolbar">
        <div>
          <h1 className="page-title">Paper Accounts</h1>
          <Typography.Text type="secondary">多账户隔离的 LEAN 模拟券商工作台</Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<SwapOutlined />} disabled={selected.length < 2 || selected.length > 10} onClick={() => setComparisonOpen(true)}>
            比较 {selected.length || ""}
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setWizardOpen(true)}>新建模拟账户</Button>
        </Space>
      </div>
      <Alert
        showIcon
        type="info"
        message="每日自动运行是正式 Paper Execution Cycle，不是会覆写账户的普通全量 Backtest。无信号仍是成功，有信号也可能因风险或市场规则不成交。"
        style={{ marginBottom: 16 }}
        action={<Link to="/paper/legacy">查看 Legacy Sessions</Link>}
      />
      <Card className="paper-filter-card">
        <Space wrap>
          <Input.Search
            allowClear
            placeholder="搜索账户或说明"
            onSearch={setKeyword}
            style={{ width: 260 }}
          />
          <Select
            allowClear
            placeholder="账户状态"
            style={{ width: 160 }}
            onChange={setStatus}
            options={["draft", "active", "paused", "error", "archived"].map((value) => ({ value, label: value }))}
          />
          <Select value="china" disabled style={{ width: 150 }} options={[{ value: "china", label: "中国 A 股" }]} />
          <Radio.Group value={view} onChange={(event) => setView(event.target.value)}>
            <Radio.Button value="cards"><AppstoreOutlined /></Radio.Button>
            <Radio.Button value="table"><BarsOutlined /></Radio.Button>
          </Radio.Group>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
        </Space>
      </Card>
      <Spin spinning={loading}>
        {!accounts.length && !loading ? <Empty description="尚无模拟账户" /> : view === "cards" ? (
          <div className="paper-account-grid">
            {accounts.map((account) => (
              <AccountCard
                key={account.id}
                account={account}
                selected={selected.includes(account.id)}
                onSelect={(checked) => select(account.id, checked)}
                onDelete={() => deleteAccount(account)}
              />
            ))}
          </div>
        ) : (
          <Table
            rowKey="id"
            dataSource={accounts}
            scroll={{ x: 1200 }}
            rowSelection={{ selectedRowKeys: selected, onChange: (keys) => setSelected(keys.map(String)) }}
            columns={[
              { title: "账户", dataIndex: "name", fixed: "left", render: (value, row) => <Link to={`/paper/accounts/${row.id}`}>{value}</Link> },
              { title: "状态", dataIndex: "status", render: (value) => <StatusBadge value={value} /> },
              { title: "策略", dataIndex: "primary_strategy", render: (value) => value || "—" },
              { title: "总资产", dataIndex: "total_equity", render: (value, row) => money(value, row.base_currency) },
              { title: "可用现金", dataIndex: "available_cash", render: (value, row) => money(value, row.base_currency) },
              { title: "当日盈亏", dataIndex: "daily_pnl", render: (value, row) => money(value, row.base_currency) },
              { title: "累计收益", dataIndex: "cumulative_return", render: percent },
              { title: "超额收益", dataIndex: "excess_return", render: percent },
              { title: "持仓", dataIndex: "position_count" },
              { title: "健康", dataIndex: "health_status", render: (value) => <StatusBadge value={value} /> },
              { title: "最后运行", dataIndex: "last_successful_trading_date", render: (value) => value || "—" },
              {
                title: "操作",
                fixed: "right",
                render: (_, account) => (
                  <Popconfirm
                    title="删除 Paper 账户？"
                    description="账户、执行周期、订单、成交和账本记录将永久删除。"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    disabled={account.status === "active"}
                    onConfirm={() => deleteAccount(account)}
                  >
                    <Button danger size="small" disabled={account.status === "active"} icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                )
              }
            ]}
          />
        )}
      </Spin>
      <AccountWizard open={wizardOpen} onClose={() => setWizardOpen(false)} onCreated={load} />
      <ComparisonModal open={comparisonOpen} accountIds={selected} onClose={() => setComparisonOpen(false)} />
    </>
  );
}

function DataError({ label, error }: { label: string; error?: string }) {
  if (!error) return null;
  return <Alert type="warning" showIcon message={`${label} 局部加载失败`} description={error} style={{ marginBottom: 12 }} />;
}

export function PaperAccountDetailPage() {
  const { id = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [overview, setOverview] = useState<PaperAccountOverview | null>(null);
  const [deployments, setDeployments] = useState<PaperDeployment[]>([]);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [orders, setOrders] = useState<Array<Record<string, unknown>>>([]);
  const [trades, setTrades] = useState<Array<Record<string, unknown>>>([]);
  const [signals, setSignals] = useState<PaperSignal[]>([]);
  const [cycles, setCycles] = useState<PaperExecutionCycle[]>([]);
  const [audit, setAudit] = useState<Array<Record<string, unknown>>>([]);
  const [performance, setPerformance] = useState<Array<Record<string, unknown>>>([]);
  const [workerHealth, setWorkerHealth] = useState<string>("unknown");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [positionDrawer, setPositionDrawer] = useState<PaperPosition | null>(null);
  const loadedTabs = useRef(new Set<string>());
  const activeAccountId = useRef(id);
  const navigate = useNavigate();
  const activeTab = searchParams.get("tab") || "overview";

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.paperAccountOverview(id);
      if (activeAccountId.current !== id) return;
      setOverview(result);
      setDeployments(result.deployment ? [result.deployment] : []);
      setErrors((current) => {
        const next = { ...current };
        delete next.overview;
        return next;
      });
    } catch (error) {
      if (activeAccountId.current === id) {
        setErrors((current) => ({ ...current, overview: (error as Error).message }));
      }
    } finally {
      if (activeAccountId.current === id) setLoading(false);
    }
  }, [id]);

  const loadTab = useCallback(async (tab: string, force = false) => {
    if (!force && loadedTabs.current.has(tab)) return;
    const requests: Array<[string, Promise<unknown>]> = [];
    if (tab === "overview") {
      requests.push(["positions", api.paperAccountPositions(id)], ["performance", api.paperAccountPerformance(id)]);
    } else if (tab === "positions") {
      requests.push(["positions", api.paperAccountPositions(id)]);
    } else if (tab === "orders") {
      requests.push(["orders", api.paperAccountOrders(id)]);
    } else if (tab === "trades") {
      requests.push(["trades", api.paperAccountTrades(id)]);
    } else if (tab === "signals") {
      requests.push(["signals", api.paperAccountSignals(id)]);
    } else if (tab === "performance") {
      requests.push(["performance", api.paperAccountPerformance(id)]);
    } else if (tab === "automation") {
      requests.push(
        ["deployments", api.paperDeployments(id)],
        ["cycles", api.paperAccountCycles(id)],
        ["dependencies", api.dependencyHealth()]
      );
    } else if (tab === "audit") {
      requests.push(["audit", api.paperAccountAudit(id)]);
    }
    if (!requests.length) return;
    const results = await Promise.allSettled(requests.map(([, request]) => request));
    if (activeAccountId.current !== id) return;
    const nextErrors: Record<string, string> = {};
    results.forEach((result, index) => {
      const name = requests[index][0];
      if (result.status === "rejected") {
        nextErrors[name] = (result.reason as Error).message;
        return;
      }
      const value = result.value as any;
      if (name === "positions") setPositions(value.items);
      if (name === "orders") setOrders(value.items);
      if (name === "trades") setTrades(value.items);
      if (name === "signals") setSignals(value.items);
      if (name === "cycles") setCycles(value.items);
      if (name === "audit") setAudit(value.items);
      if (name === "performance") setPerformance(value.points);
      if (name === "deployments") setDeployments(value);
      if (name === "dependencies") {
        const worker = value.dependencies.find((item: { service: string }) => item.service === "backtest_worker");
        setWorkerHealth(worker?.ok ? "healthy" : "error");
      }
    });
    setErrors((current) => {
      const next = { ...current };
      requests.forEach(([name]) => delete next[name]);
      return { ...next, ...nextErrors };
    });
    loadedTabs.current.add(tab);
  }, [id]);

  const load = useCallback(async () => {
    loadedTabs.current.delete(activeTab);
    await loadOverview();
    await loadTab(activeTab, true);
  }, [activeTab, loadOverview, loadTab]);

  useEffect(() => {
    activeAccountId.current = id;
    loadedTabs.current.clear();
    setOverview(null);
    void loadOverview();
  }, [id, loadOverview]);

  useEffect(() => {
    void loadTab(activeTab);
  }, [activeTab, loadTab]);

  async function accountAction(action: "activate" | "pause" | "resume" | "archive") {
    try {
      await api.paperAccountAction(id, action);
      message.success(`账户已${action}`);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  async function deploymentAction(deployment: PaperDeployment, action: "activate" | "pause" | "resume") {
    try {
      await api.paperDeploymentAction(deployment.id, action);
      message.success(`Deployment 已${action}`);
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  async function runNow(deployment: PaperDeployment) {
    try {
      const cycle = await api.runPaperDeploymentNow(deployment.id);
      message.success(cycle.status === "succeeded" ? "该交易日已经成功，未重复成交" : "缺失交易日 cycle 已进入队列");
      await load();
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  if (loading && !overview) return <Spin size="large" />;
  if (!overview) return <Alert type="error" message="账户加载失败" description={errors.overview} />;
  const account = overview.account;
  const primary = deployments.find((item) => Boolean(item.is_primary)) || deployments[0];
  const chartPoints = performance.map((item) => [
    String(item.tradingDate || item.trading_date || ""),
    Number(item.cumulativeReturn || item.cumulative_return || 0)
  ]);

  const positionColumns = [
    { title: "证券代码", dataIndex: "symbol", fixed: "left" as const, render: (value: string, row: PaperPosition) => <Button type="link" onClick={() => setPositionDrawer(row)}>{value}</Button> },
    { title: "证券名称", dataIndex: "security_name", render: (value: string) => value || "—" },
    { title: "持仓数量", dataIndex: "quantity" },
    { title: "可卖数量", dataIndex: "sellable_quantity" },
    { title: "冻结数量", dataIndex: "frozen_quantity" },
    { title: "平均成本", dataIndex: "average_cost", render: (value: string) => Number(value).toFixed(4) },
    { title: "最新认证价格", dataIndex: "certified_price", render: (value: string) => value ? Number(value).toFixed(4) : "—" },
    { title: "行情日期", dataIndex: "quote_data_timestamp", render: (value: string) => value || "—" },
    { title: "市值", dataIndex: "market_value", render: (value: string) => money(value, account.base_currency) },
    { title: "账户权重", dataIndex: "account_weight", render: percent },
    { title: "浮动盈亏", dataIndex: "unrealized_pnl", render: (value: string) => money(value, account.base_currency) },
    { title: "数据状态", dataIndex: "data_status", render: (value: string) => <StatusBadge value={value} /> }
  ];

  const tabItems = [
    {
      key: "overview",
      label: "Overview",
      children: (
        <>
          <DataError label="收益曲线" error={errors.performance} />
          <Card title="资产与收益">
            {chartPoints.length ? (
              <ReactECharts option={{
                tooltip: { trigger: "axis" },
                xAxis: { type: "category", data: chartPoints.map((item) => item[0]) },
                yAxis: { type: "value", axisLabel: { formatter: (value: number) => `${(value * 100).toFixed(1)}%` } },
                series: [{ type: "line", name: "累计收益", data: chartPoints.map((item) => item[1]), smooth: true }]
              }} style={{ height: 300 }} />
            ) : <Empty description="完成首个 cycle 后显示收益曲线" />}
          </Card>
          <Card title="当前持仓摘要" style={{ marginTop: 16 }}>
            <Table rowKey="symbol" size="small" pagination={false} scroll={{ x: 1100 }} dataSource={positions.slice(0, 5)} columns={positionColumns} />
          </Card>
        </>
      )
    },
    {
      key: "positions",
      label: "Positions",
      children: (
        <>
          <DataError label="持仓" error={errors.positions} />
          <Alert type="info" showIcon message="价格列为最新认证收盘价，不代表实时行情；过期或缺失数据会明确标记。" style={{ marginBottom: 12 }} />
          <Table rowKey="symbol" scroll={{ x: 1300 }} dataSource={positions} columns={positionColumns} />
        </>
      )
    },
    {
      key: "orders",
      label: "Orders",
      children: (
        <>
          <DataError label="委托" error={errors.orders} />
          <Table
            rowKey={(row) => String(row.id)}
            scroll={{ x: 1300 }}
            dataSource={orders}
            columns={[
              { title: "Order ID", dataIndex: "id", fixed: "left", ellipsis: true },
              { title: "Symbol", dataIndex: "symbol" },
              { title: "Side", dataIndex: "side" },
              { title: "Type", dataIndex: "order_type" },
              { title: "Quantity", dataIndex: "precise_quantity" },
              { title: "Submitted Price", dataIndex: "precise_requested_price" },
              { title: "Expected Date", dataIndex: "trade_date" },
              { title: "13-state Status", dataIndex: "status", render: (value) => <StatusBadge value={String(value)} /> },
              { title: "Filled", dataIndex: "filled_quantity" },
              { title: "Avg Fill", dataIndex: "average_fill_price" },
              { title: "Fees", dataIndex: "fees" },
              { title: "Reject Reason", dataIndex: "reject_reason", render: (value) => value || "—" },
              { title: "Created", dataIndex: "created_at" }
            ]}
          />
        </>
      )
    },
    {
      key: "trades",
      label: "Trades",
      children: (
        <>
          <DataError label="成交" error={errors.trades} />
          <Table
            rowKey={(row) => String(row.id)}
            scroll={{ x: 1400 }}
            dataSource={trades}
            columns={[
              { title: "Fill Time", dataIndex: "created_at", fixed: "left" },
              { title: "Symbol", dataIndex: "symbol" },
              { title: "Side", dataIndex: "side" },
              { title: "Quantity", dataIndex: "precise_quantity" },
              { title: "Price", dataIndex: "precise_price" },
              { title: "Principal", dataIndex: "principal" },
              { title: "Commission", dataIndex: "commission" },
              { title: "Stamp Duty", dataIndex: "stamp_duty" },
              { title: "Transfer Fee", dataIndex: "transfer_fee" },
              { title: "Slippage", dataIndex: "precise_slippage" },
              { title: "Cash Impact", dataIndex: "total_cash_impact" },
              { title: "Order", dataIndex: "intent_id", ellipsis: true },
              { title: "Trading Date", dataIndex: "trade_date" }
            ]}
          />
        </>
      )
    },
    {
      key: "signals",
      label: "Signals",
      children: (
        <>
          <DataError label="信号" error={errors.signals} />
          <Table
            rowKey="id"
            scroll={{ x: 1400 }}
            dataSource={signals}
            columns={[
              { title: "Type", dataIndex: "signal_type", fixed: "left" },
              { title: "Symbol", dataIndex: "symbol", render: (value) => value || "—" },
              { title: "Signal Time", dataIndex: "signal_timestamp" },
              { title: "Intended Execution", dataIndex: "intended_execution_date" },
              { title: "Target Qty", dataIndex: "target_quantity" },
              { title: "Target Weight", dataIndex: "target_weight", render: (value) => value ? percent(value) : "—" },
              { title: "Disposition", dataIndex: "disposition", render: (value) => <StatusBadge value={value} /> },
              { title: "为什么没有交易", dataIndex: "no_trade_reason", render: (value) => value || "—" },
              { title: "LEAN Run", dataIndex: "lean_run_id", ellipsis: true },
              { title: "Data Timestamp", dataIndex: "data_timestamp" }
            ]}
          />
        </>
      )
    },
    {
      key: "performance",
      label: "Performance",
      children: <Table rowKey={(row) => String(row.tradingDate || row.trading_date)} dataSource={performance} columns={[
        { title: "交易日", dataIndex: "tradingDate" },
        { title: "总资产", dataIndex: "totalEquity" },
        { title: "累计收益", dataIndex: "cumulativeReturn", render: percent },
        { title: "基准收益", dataIndex: "benchmarkReturn", render: percent },
        { title: "超额收益", dataIndex: "excessReturn", render: percent }
      ]} />
    },
    {
      key: "automation",
      label: "Automation",
      children: (
        <>
          <DataError label="运行周期" error={errors.cycles} />
          {primary ? (
            <Card
              title={primary.name}
              extra={<StatusBadge value={primary.status} />}
              actions={[
                primary.status === "active"
                  ? <Button key="pause" icon={<PauseCircleOutlined />} onClick={() => void deploymentAction(primary, "pause")}>暂停策略</Button>
                  : <Button key="resume" icon={<PlayCircleOutlined />} onClick={() => void deploymentAction(primary, "resume")}>恢复策略</Button>,
                <Button key="run" type="primary" icon={<PlayCircleOutlined />} disabled={primary.status !== "active"} onClick={() => void runNow(primary)}>Run now</Button>
              ]}
            >
              <Alert type="info" showIcon message="Run now 只补跑缺失交易日；已成功日期返回幂等结果，不会重复扣费或修改已结算 ledger。" />
              <Descriptions bordered size="small" column={2} style={{ marginTop: 16 }}>
                <Descriptions.Item label="自动运行">{primary.schedule_type === "market_daily" ? "启用" : "手动"}</Descriptions.Item>
                <Descriptions.Item label="市场时区">{primary.market_timezone}</Descriptions.Item>
                <Descriptions.Item label="计划">{primary.schedule_expression}</Descriptions.Item>
                <Descriptions.Item label="Next Run">{primary.next_scheduled_at || "—"}</Descriptions.Item>
                <Descriptions.Item label="Last Success">{primary.last_successful_trading_date || "—"}</Descriptions.Item>
                <Descriptions.Item label="Execution">{primary.execution_timing}</Descriptions.Item>
                <Descriptions.Item label="Dataset">{primary.dataset_version_id}</Descriptions.Item>
                <Descriptions.Item label="Failures">{primary.consecutive_failures}</Descriptions.Item>
                <Descriptions.Item label="Data Watermark">{overview.dataReadiness?.watermark?.last_data_date || "未就绪"}</Descriptions.Item>
                <Descriptions.Item label="QA Status">{overview.dataReadiness?.qa?.severity || "unknown"}</Descriptions.Item>
                <Descriptions.Item label="Worker / Queue"><StatusBadge value={workerHealth} /></Descriptions.Item>
                <Descriptions.Item label="Last Failure">
                  {cycles.find((item) => item.status === "failed")?.failure_code || "—"}
                </Descriptions.Item>
                <Descriptions.Item label="Checkpoint" span={2}>{account.source_checkpoint_digest || "—"}</Descriptions.Item>
              </Descriptions>
            </Card>
          ) : <Empty description="尚无策略部署" />}
          <Table
            rowKey="id"
            style={{ marginTop: 16 }}
            dataSource={cycles}
            columns={[
              { title: "Trading Date", dataIndex: "trading_date" },
              { title: "Status", dataIndex: "status", render: (value) => <StatusBadge value={value} /> },
              { title: "Signals", dataIndex: "signal_count" },
              { title: "Intents", dataIndex: "intent_count" },
              { title: "Orders", dataIndex: "order_count" },
              { title: "Fills", dataIndex: "fill_count" },
              { title: "Rejected", dataIndex: "rejected_count" },
              { title: "Reason", render: (_, row) => row.failure_code || row.skip_reason || "—" }
            ]}
          />
        </>
      )
    },
    {
      key: "audit",
      label: "Audit",
      children: (
        <>
          <DataError label="审计" error={errors.audit} />
          <Table rowKey={(row) => String(row.id)} dataSource={audit} columns={[
            { title: "Time", dataIndex: "created_at" },
            { title: "Trading Date", dataIndex: "trading_date" },
            { title: "Event", dataIndex: "event_type" },
            { title: "From", dataIndex: "from_status" },
            { title: "To", dataIndex: "to_status", render: (value) => <StatusBadge value={String(value)} /> },
            { title: "Payload", dataIndex: "payload", render: (value) => <Typography.Text code>{JSON.stringify(value)}</Typography.Text> }
          ]} />
        </>
      )
    }
  ];

  return (
    <>
      <div className="toolbar paper-toolbar">
        <div>
          <Space>
            <Button onClick={() => navigate("/paper")}>返回账户</Button>
            <h1 className="page-title">{account.name}</h1>
            <StatusBadge value={account.status} />
          </Space>
          <Typography.Text type="secondary">
            {account.market_scope.toUpperCase()} · {account.base_currency} · Benchmark {account.benchmark_symbol}
          </Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<CopyOutlined />} onClick={async () => {
            const clone = await api.clonePaperAccount(id);
            message.success("已克隆配置，新账户使用独立 Opening Ledger");
            navigate(`/paper/accounts/${clone.id}`);
          }}>克隆</Button>
          {account.status === "active" && <Button onClick={() => void accountAction("pause")}>暂停账户</Button>}
          {account.status === "paused" && <Button type="primary" onClick={() => void accountAction("resume")}>恢复账户</Button>}
          {account.status === "draft" && <Button type="primary" onClick={() => void accountAction("activate")}>激活账户</Button>}
          {["paused", "draft", "error"].includes(account.status) && <Button danger onClick={() => void accountAction("archive")}>归档</Button>}
          <Popconfirm
            title="永久删除 Paper 账户？"
            description="账户、执行周期、订单、成交和账本记录将永久删除。"
            okText="删除"
            okButtonProps={{ danger: true }}
            disabled={account.status === "active"}
            onConfirm={async () => {
              try {
                await api.deletePaperAccount(id);
                message.success("Paper 账户已删除");
                navigate("/paper");
              } catch (error) {
                message.error(`账户删除失败：${(error as Error).message}`);
              }
            }}
          >
            <Button danger icon={<DeleteOutlined />} disabled={account.status === "active"}>删除</Button>
          </Popconfirm>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>刷新</Button>
        </Space>
      </div>
      <Card className="paper-account-summary">
        <div className="paper-summary-metrics">
          <Metric title="总资产 / NAV" value={account.total_equity} currency={account.base_currency} />
          <Metric title="可用现金" value={account.available_cash} currency={account.base_currency} />
          <Metric title="持仓市值" value={account.market_value} currency={account.base_currency} />
          <Metric title="当日盈亏" value={account.daily_pnl} currency={account.base_currency} />
          <Metric title="累计收益" value={account.cumulative_return} kind="percent" />
          <Metric title="基准收益" value={account.benchmark_return} kind="percent" />
          <Metric title="超额收益" value={account.excess_return} kind="percent" />
          <Metric title="持仓数" value={account.position_count} kind="number" />
        </div>
        <Divider />
        <Space wrap>
          <StatusBadge value={overview.latestCycle?.status || account.health_status} />
          <span>最后估值：{account.last_valuation_at || "—"}</span>
          <span>行情日期：{account.quote_data_timestamp || "—"}</span>
          <span>主策略：{primary?.name || "—"}</span>
        </Space>
      </Card>
      <Tabs
        activeKey={activeTab}
        onChange={(tab) => setSearchParams({ tab })}
        items={tabItems}
        className="paper-account-tabs"
      />
      <Drawer
        size="large"
        open={Boolean(positionDrawer)}
        onClose={() => setPositionDrawer(null)}
        title={`${positionDrawer?.symbol || ""} 标的详情`}
      >
        {positionDrawer && (
          <>
            <Descriptions bordered column={1}>
              <Descriptions.Item label="当前仓位">{positionDrawer.quantity}</Descriptions.Item>
              <Descriptions.Item label="可卖数量">{positionDrawer.sellable_quantity}</Descriptions.Item>
              <Descriptions.Item label="平均成本">{positionDrawer.average_cost}</Descriptions.Item>
              <Descriptions.Item label="最新认证收盘价">{positionDrawer.certified_price || "—"}</Descriptions.Item>
              <Descriptions.Item label="行情日期">{positionDrawer.quote_data_timestamp || "—"}</Descriptions.Item>
              <Descriptions.Item label="浮动盈亏">{money(positionDrawer.unrealized_pnl, account.base_currency)}</Descriptions.Item>
              <Descriptions.Item label="数据状态">{positionDrawer.data_status}</Descriptions.Item>
            </Descriptions>
            <Divider />
            <Typography.Title level={5}>信号 → Intent → 风控 → 委托 → 成交</Typography.Title>
            {signals.filter((item) => item.symbol === positionDrawer.symbol).length ? (
              signals.filter((item) => item.symbol === positionDrawer.symbol).map((signal) => (
                <Card key={signal.id} size="small" style={{ marginBottom: 8 }}>
                  <StatusBadge value={signal.signal_type} /> {signal.signal_timestamp}<br />
                  结果：{signal.disposition} {signal.no_trade_reason ? `· ${signal.no_trade_reason}` : ""}
                  <br />LEAN: {signal.lean_run_id || "—"} · Data: {signal.data_timestamp || "—"}
                </Card>
              ))
            ) : <Empty description="该标的暂无信号证据" />}
          </>
        )}
      </Drawer>
    </>
  );
}
