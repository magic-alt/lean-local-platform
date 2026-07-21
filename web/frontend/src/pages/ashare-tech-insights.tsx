import { Alert, Button, Card, Checkbox, Col, Descriptions, Divider, Form, Input, Modal, Popconfirm, Row, Select, Space, Statistic, Switch, Table, Tag, Typography, message } from "antd";
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import type { AshareTechGroupSummary, AshareTechMarketEnvironmentItem, AshareTechReport, AshareTechRuleTag, AshareTechStockRow, AshareTechWatchlistItem } from "../api";
import { ApiError } from "../api/client";
import { DateStringPicker } from "../components/DateStringPicker";
import { SecuritySearch } from "../components/SecuritySearch";
import { useAsyncData } from "../hooks";

const emptyList = { items: [], count: 0, limit: 50, offset: 0 };
const emptyWatchlist = { items: [], count: 0, enabledCount: 0, maxSize: 60, groups: [], fingerprint: "" };
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
    promptVersion: "ashare-tech-gpt56-v1", model: null, llmOptional: true, paperHandoff: false,
    schedule: "工作日17:30", labels: []
  }, false);
  const watchlist = useAsyncData(api.ashareTechWatchlist, emptyWatchlist, false);
  const [selected, setSelected] = useState<AshareTechReport | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mutating, setMutating] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [detailWarning, setDetailWarning] = useState<string | null>(null);
  const [addForm] = Form.useForm();

  const loadErrors = [reports.error, capabilities.error, watchlist.error].filter((item): item is Error => Boolean(item));
  const routeMissing = loadErrors.some((error) => error instanceof ApiError && error.status === 404);

  const refreshAll = useCallback(async () => {
    const [nextReports] = await Promise.all([reports.reload(), capabilities.reload(), watchlist.reload()]);
    if (selected && nextReports && !nextReports.items.some((item) => item.id === selected.id)) {
      setSelected(null);
      setDetailWarning("该报告已不在历史列表中，已清空详情并停止自动轮询。");
    }
  }, [capabilities, reports, selected, watchlist]);

  const loadDetail = useCallback(async (id: string) => {
    try {
      setSelected(await api.ashareTechReport(id));
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
  }, [loadDetail, reports, selected]);

  async function create(values: { requestedDate?: string; force?: boolean }) {
    setSubmitting(true);
    try {
      const result = await api.createAshareTechReport(values);
      message.success(result.reused ? "已打开同日报告任务" : "日报任务已进入队列");
      await reports.reload();
      await loadDetail(result.id);
    } catch (error) { message.error((error as Error).message); }
    finally { setSubmitting(false); }
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

  async function updateStock(code: string, payload: { enabled?: boolean; ruleTags?: AshareTechRuleTag[] }) {
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
      await api.deleteAshareTechReport(item.id);
      if (selected?.id === item.id) setSelected(null);
      message.success(`已删除 ${item.requested_date} 的历史报告`);
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
  return (
    <>
      <Alert
        showIcon type="info" style={{ marginBottom: 16 }}
        message={`当前启用 ${capabilities.data.poolSize} / 总计 ${capabilities.data.totalPoolSize} 只｜${capabilities.data.schedule}`}
        description="TuShare Pro 统一计算前复权日线、成交量、成交额和换手率；东方财富只核验最新收盘。规则引擎决定分类，模型未配置时仍生成确定性报告。本工作区没有 Paper 或自动下单入口。"
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
        <Form layout="inline" onFinish={create} initialValues={{ force: false }}>
          <Form.Item name="requestedDate" label="报告日期"><DateStringPicker /></Form.Item>
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
            { title: "固定分组", dataIndex: "group", width: 220 },
            { title: "启用", width: 80, render: (_, item) => <Switch checked={item.enabled} loading={mutating} onChange={(enabled) => void updateStock(item.code, { enabled })} /> },
            { title: "特殊规则标签", width: 260, render: (_, item) => <Select
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
              description="报告及关联任务日志会被删除，此操作不可撤销。"
              okText="删除"
              okButtonProps={{ danger: true }}
              onConfirm={() => void deleteReport(item)}
              disabled={["created", "queued", "running", "waiting_data", "interrupted"].includes(item.status)}
            >
              <Button danger size="small" icon={<DeleteOutlined />} loading={mutating} disabled={["created", "queued", "running", "waiting_data", "interrupted"].includes(item.status)}>删除</Button>
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
          <Descriptions.Item label="模型">{selected.model || "确定性模板（未调用模型）"}</Descriptions.Item>
        </Descriptions>
        {selected.error && <Alert type="error" showIcon message={selected.error} style={{ marginTop: 16 }} />}
        {report?.summary && <Alert type="warning" showIcon message={report.summary} style={{ marginTop: 16 }} />}
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
          <Form.Item name="code" label="股票代码" rules={[{ required: true }, { pattern: /^\d{6}$/, message: "请输入6位股票代码" }]}>
            <SecuritySearch market="china" placeholder="代码 / 公司名 / 拼音 / 别名" />
          </Form.Item>
          <Form.Item name="groupKey" label="加入固定分组" rules={[{ required: true }]}>
            <Select options={watchlist.data.groups.map((group) => ({ value: group.key, label: group.name }))} />
          </Form.Item>
          <Form.Item name="ruleTags" label="特殊低吸约束">
            <Checkbox.Group options={ruleTagOptions} />
          </Form.Item>
          <Alert type="info" showIcon message="保存前必须通过 TuShare 确认为在市A股，名称由系统自动填写。" style={{ marginBottom: 16 }} />
          <Button type="primary" htmlType="submit" loading={mutating}>验证并添加</Button>
        </Form>
      </Modal>
    </>
  );
}
