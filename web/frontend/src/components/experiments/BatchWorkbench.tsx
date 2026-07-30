import { Alert, Button, Card, Checkbox, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Table, Tag, message } from "antd";
import { DeleteOutlined, DownloadOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import type { Key } from "react";
import dayjs from "dayjs";

import { api } from "../../api";
import { LeanChart } from "../../charts/LeanChart";
import type { DataScope, ExperimentBatch, ExperimentBatchComparison, ExperimentBatchPreview, ExperimentSensitivity, Project, WorkflowExample } from "../../api";
import { DateStringPicker } from "../DateStringPicker";
import { AdvancedFields, FormActions, FormGrid, FormSection } from "../forms/FormLayout";
import { marketCostParameters } from "../../domain/backtest-request";
import { projectSelectOptions } from "../../utils/projects";


const MODES = {
  backtest: [
    { value: "independent", label: "独立矩阵" },
    { value: "rolling", label: "滚动窗口" },
    { value: "dynamic_universe", label: "动态组合" }
  ],
  optimization: [
    { value: "single_symbol_grid", label: "单股参数网格" },
    { value: "universe_robust", label: "股票池稳健参数" },
    { value: "walk_forward", label: "Walk-forward" },
    { value: "multi_strategy", label: "多策略分别寻优" }
  ],
  research: [
    { value: "analysis", label: "快捷研究" },
    { value: "factor_batch", label: "多因子批量评价" }
  ]
};
const UNIVERSE_OPTIONS = [
  { value: "CSI300", label: "沪深300（CSI300）", benchmark: "000300" },
  { value: "CSI500", label: "中证500（CSI500）", benchmark: "000905" },
  { value: "CSI1000", label: "中证1000（CSI1000）", benchmark: "000852" },
  { value: "STAR50", label: "科创50（STAR50）", benchmark: "000688" },
  { value: "SSE50", label: "上证50（SSE50）", benchmark: "000016" },
  { value: "ALL_A", label: "全A股（ALL_A）", benchmark: "000300" }
];

function sensitivityOption(sensitivity: ExperimentSensitivity) {
  const xIndex = new Map(sensitivity.xValues.map((value, index) => [value, index]));
  const yIndex = new Map(sensitivity.yValues.map((value, index) => [value, index]));
  const values = sensitivity.cells.map((cell) => cell.value);
  return {
    tooltip: {
      formatter: (item: any) => {
        const cell = sensitivity.cells[item.data[3]];
        return `${sensitivity.xParameter}: ${cell.x}<br/>${sensitivity.yParameter}: ${cell.y}<br/>${sensitivity.metric}: ${cell.value.toFixed(4)}<br/>样本: ${cell.count}`;
      }
    },
    grid: { left: 72, right: 40, top: 30, bottom: 70 },
    xAxis: { type: "category", name: sensitivity.xParameter, data: sensitivity.xValues.map(String), splitArea: { show: true } },
    yAxis: { type: "category", name: sensitivity.yParameter, data: sensitivity.yValues.map(String), splitArea: { show: true } },
    visualMap: {
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 1,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 4
    },
    series: [{
      type: "heatmap",
      data: sensitivity.cells.map((cell, index) => [xIndex.get(cell.x), yIndex.get(cell.y), cell.value, index]),
      label: { show: true, formatter: (item: any) => Number(item.value[2]).toFixed(2) },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,0.35)" } }
    }]
  };
}

function phaseOption(batches: ExperimentBatchComparison["batches"]) {
  const points = batches.flatMap((batch) => batch.phaseSeries.map((row: any) => ({
    key: `${batch.name} · F${row.fold}`,
    batchId: batch.id,
    row
  })));
  return {
    tooltip: { trigger: "axis" },
    legend: { data: ["Train", "Validation", "OOS"] },
    grid: { left: 60, right: 30, top: 44, bottom: 80 },
    xAxis: { type: "category", data: points.map((point) => point.key), axisLabel: { rotate: 30 } },
    yAxis: { type: "value", name: "Sharpe" },
    series: [
      { name: "Train", type: "bar", data: points.map((point) => point.row.trainSharpe ?? null) },
      { name: "Validation", type: "bar", data: points.map((point) => point.row.validationSharpe ?? null) },
      { name: "OOS", type: "bar", data: points.map((point) => point.row.oosSharpe ?? null) }
    ]
  };
}

function metricText(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "-";
}

type BatchPreset = {
  example: WorkflowExample;
  project: Project;
  defaults: Record<string, unknown>;
};

function defaultBenchmark(market: string) {
  if (market === "china") return "000300";
  if (market === "hongkong") return "02800";
  return "SPY";
}

function defaultSource(market: string) {
  return market === "china" || market === "hongkong" ? "tushare" : "";
}

export function BatchWorkbench({
  kind,
  projects,
  preset,
  handoffDraft,
}: {
  kind: "backtest" | "optimization" | "research";
  projects: Project[];
  preset?: BatchPreset;
  handoffDraft?: { sourceResearchRunId: string; dataScope: DataScope };
}) {
  const [form] = Form.useForm();
  const [preview, setPreview] = useState<ExperimentBatchPreview>();
  const [batches, setBatches] = useState<ExperimentBatch[]>([]);
  const [selected, setSelected] = useState<ExperimentBatch>();
  const [compareIds, setCompareIds] = useState<Key[]>([]);
  const [comparison, setComparison] = useState<ExperimentBatchComparison>();
  const [compareMetric, setCompareMetric] = useState("sharpe");
  const [busy, setBusy] = useState(false);
  const symbolSource = Form.useWatch("symbolSource", form) || "symbols";
  const mode = Form.useWatch("mode", form) || MODES[kind][0].value;
  const market = Form.useWatch("market", form) || "china";
  const selectedProjectIds = Form.useWatch("projectIds", form) || [];
  const isIndexScreening = projects.some(
    (project) => selectedProjectIds.includes(project.id)
      && project.config?.templateKey === "ashare_index_screening"
  );
  const universeOptions = isIndexScreening
    ? UNIVERSE_OPTIONS.filter((item) => ["CSI300", "CSI500", "CSI1000", "STAR50"].includes(item.value))
    : UNIVERSE_OPTIONS;

  async function reload() {
    try {
      setBatches((await api.experimentBatches()).filter((item) => item.kind === kind));
      if (selected) setSelected(await api.experimentBatch(selected.id));
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  useEffect(() => { void reload(); }, [kind]);
  useEffect(() => {
    const applyPreset = (detail: { example?: { kind?: string; mode?: string }; project?: Project; defaults?: Record<string, unknown> }) => {
      if (detail.example?.kind !== kind || !detail.project) return;
      const defaults = detail.defaults || {};
      const nextMarket = String(defaults.market || "china");
      form.setFieldsValue({
        market: nextMarket,
        benchmarkSymbol: defaultBenchmark(nextMarket),
        source: defaultSource(nextMarket),
        ...defaults,
        mode: detail.example.mode || MODES[kind][0].value,
        projectIds: [detail.project.id],
        symbolSource: defaults.universeCode ? "universe" : "symbols",
        symbols: defaults.symbol || "000001",
        parameterGridJson: defaults.parameterGrid ? JSON.stringify(defaults.parameterGrid) : form.getFieldValue("parameterGridJson"),
        parameters: defaults.parameters || {}
      });
      setPreview(undefined);
    };
    if (preset) {
      applyPreset(preset);
    }
    const applyExample = (event: Event) => {
      const detail = (event as CustomEvent).detail as { example?: { kind?: string; mode?: string }; project?: Project; launch?: { defaults?: Record<string, unknown> } };
      applyPreset({ example: detail.example, project: detail.project, defaults: detail.launch?.defaults });
    };
    window.addEventListener("lean-example-instantiated", applyExample);
    return () => window.removeEventListener("lean-example-instantiated", applyExample);
  }, [form, kind, preset]);
  useEffect(() => {
    if (kind !== "backtest" || !handoffDraft) return;
    const scope = handoffDraft.dataScope;
    const universe = scope.selection.type === "universe";
    form.setFieldsValue({
      name: `Research validation · ${handoffDraft.sourceResearchRunId.slice(0, 8)}`,
      mode: "independent",
      market: scope.asset.market,
      venue: scope.asset.venue || scope.asset.market,
      resolution: scope.asset.resolution,
      dataType: scope.asset.dataType,
      symbolSource: universe ? "universe" : "symbols",
      symbols: universe ? "" : scope.selection.values.join(","),
      universeCode: universe ? scope.selection.values[0] : undefined,
      start: scope.time.startDate,
      end: scope.time.endDate,
      asOfDate: scope.time.asOfDate || scope.time.startDate,
      source: scope.provider.source,
      allowResearchSource: scope.provider.allowResearchSource,
      sourceResearchRunId: handoffDraft.sourceResearchRunId,
      dataScope: scope,
    });
    setPreview(undefined);
  }, [form, handoffDraft, kind]);
  useEffect(() => {
    if (!batches.some((item) => ["queued", "running"].includes(item.status))) return;
    const timer = window.setInterval(() => void reload(), 4000);
    return () => window.clearInterval(timer);
  }, [batches]);

  function payload(values: Record<string, any>) {
    const symbols = String(values.symbols || "").split(/[\s,]+/).map((item) => item.trim().toUpperCase()).filter(Boolean);
    let parameterGrid = {};
    if (values.parameterGridJson) parameterGrid = JSON.parse(values.parameterGridJson);
    let parameterGrids = {};
    if (values.parameterGridsJson) parameterGrids = JSON.parse(values.parameterGridsJson);
    const projectIds = values.projectIds || (values.projectId ? [values.projectId] : []);
    const executionParameters = kind === "research" ? (values.parameters || {}) : {
      ...(values.parameters || {}),
      benchmarkSymbol: values.benchmarkSymbol,
      feeModel: values.feeModel,
      slippageModel: values.slippageModel,
      source: values.source,
      allowResearchSource: values.allowResearchSource === true,
      ...marketCostParameters(values.market, values.feeModel, values.slippageModel)
    };
    return {
      ...values,
      kind,
      projectIds,
      parameters: executionParameters,
      symbols: values.symbolSource === "symbols" ? symbols : [],
      universeCode: values.symbolSource === "universe" || mode === "dynamic_universe" ? values.universeCode : undefined,
      asOfDate: values.asOfDate || values.start,
      parameterGrid,
      parameterGrids,
      factorNames: String(values.factorNames || "").split(/[\s,]+/).filter(Boolean),
      sourceResearchRunId: values.sourceResearchRunId,
      dataScope: values.dataScope,
    };
  }

  async function runPreview() {
    try {
      setPreview(await api.experimentBatchPreview(payload(await form.validateFields())));
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  async function submit(values: Record<string, any>) {
    setBusy(true);
    try {
      const body = payload(values);
      const report = preview || await api.experimentBatchPreview(body);
      if (!report.withinLimit) throw new Error(report.warnings.join(" "));
      await api.createExperimentBatch(body);
      message.success(`批次已排队，共 ${report.expandedCount} 个工作单元`);
      setPreview(undefined);
      await reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function open(batch: ExperimentBatch) {
    setSelected(await api.experimentBatch(batch.id));
  }

  async function compareSelected() {
    if (compareIds.length < 2) return;
    setBusy(true);
    try {
      setComparison(await api.compareExperimentBatches({ batchIds: compareIds.map(String), metric: compareMetric }));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const activeProjectRequired = kind !== "research" || mode !== "analysis";
  const completed = (batch: ExperimentBatch) => batch.succeeded + batch.failed + batch.skipped + batch.cancelled;
  const ranking = useMemo(() => selected?.summary?.ranking || [], [selected]);

  return (
    <>
      <Card title={isIndexScreening ? "新建选股分析" : kind === "backtest" ? "New Backtest" : kind === "optimization" ? "批量优化" : "快捷研究任务"} style={{ marginTop: 16 }}>
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{
          name: kind === "backtest" ? "Batch Backtest" : kind === "optimization" ? "Batch Optimization" : "Research Analysis",
          mode: MODES[kind][0].value, symbolSource: "symbols", symbols: "000001", universeCode: "CSI300",
          start: dayjs().subtract(5, "year").format("YYYY-MM-DD"), end: dayjs().format("YYYY-MM-DD"), cash: 300000,
          market: "china", benchmarkSymbol: "000300", source: "tushare", feeModel: "default", slippageModel: "default",
          allowResearchSource: false,
          maxCandidates: 200, trainYears: 3, testYears: 1, validationMonths: 6, stepYears: 1,
          adjustmentContract: "raw-v1", featurePipelineVersion: "features-v1", labelHorizonDays: 0,
          factorNames: "momentum,volatility", parameterGridJson: '{"fast":[5,10,20],"slow":[30,60]}'
        }}>
          <FormSection title="批次与标的">
          <FormGrid>
            <Form.Item className="form-field--wide" name="name" label="批次名称" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="mode" label="运行模式"><Select virtual={false} options={MODES[kind]} onChange={() => setPreview(undefined)} /></Form.Item>
            {kind !== "research" && <Form.Item name="market" label="市场"><Select onChange={(value) => form.setFieldsValue({ benchmarkSymbol: defaultBenchmark(value), source: defaultSource(value) })} options={[{ value: "china", label: "A 股" }, { value: "hongkong", label: "港股" }, { value: "usa", label: "美股" }]} /></Form.Item>}
            {activeProjectRequired && <Form.Item className="form-field--wide" name="projectIds" label="项目" rules={[{ required: true }]}><Select virtual={false} mode="multiple" options={projectSelectOptions(projects)} /></Form.Item>}
            {kind !== "research" && <Form.Item name="symbolSource" label="标的来源"><Select options={[{ value: "symbols", label: "股票代码" }, { value: "universe", label: "PIT股票池" }]} /></Form.Item>}
            {kind !== "research" && symbolSource === "symbols" && mode !== "dynamic_universe" && <Form.Item className="form-field--wide" name="symbols" label="股票代码"><Input.TextArea rows={2} placeholder="000001,600519" /></Form.Item>}
            {kind !== "research" && (symbolSource === "universe" || mode === "dynamic_universe") && <Form.Item name="universeCode" label="股票池"><Select options={universeOptions} onChange={(value) => {
              const option = UNIVERSE_OPTIONS.find((item) => item.value === value);
              if (option) form.setFieldValue("benchmarkSymbol", option.benchmark);
              setPreview(undefined);
            }} /></Form.Item>}
            {kind === "research" && <Form.Item className="form-field--wide" name="factorNames" label="因子/研究项"><Input placeholder="momentum,volatility" /></Form.Item>}
          </FormGrid>
          </FormSection>
          {kind !== "research" && <FormSection title={isIndexScreening ? "分析区间" : "回测范围"}>
          <FormGrid>
            <Form.Item name="start" label="开始日期"><DateStringPicker /></Form.Item>
            <Form.Item name="end" label="结束日期"><DateStringPicker /></Form.Item>
            <Form.Item name="cash" label="每个运行初始资金"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
          </FormGrid>
          </FormSection>}
          {kind !== "research" && <FormSection title="执行与数据配置" description="每个展开后的子回测复用同一市场、基准、来源、费用和滑点口径。">
            <FormGrid>
              <Form.Item name="benchmarkSymbol" label="基准" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item className="form-field--wide" name="source" label="数据来源">
                {market === "china" || market === "hongkong" ? <Select options={[
                  { value: "tushare", label: "TuShare Pro" },
                  { value: "akshare", label: "AKShare" },
                  { value: "baostock", label: "Baostock" },
                  { value: "yfinance", label: "YFinance" }
                ]} /> : <Input placeholder="optional provider source" />}
              </Form.Item>
              {!isIndexScreening && <Form.Item name="feeModel" label="费用模型"><Select options={[{ value: "default", label: "市场默认费用" }, { value: "zero", label: "零费用（仅研究）" }]} /></Form.Item>}
              {!isIndexScreening && <Form.Item name="slippageModel" label="滑点模型"><Select options={[{ value: "default", label: "默认" }, { value: "zero", label: "零滑点" }]} /></Form.Item>}
              <Form.Item className="form-field--full" name="allowResearchSource" valuePropName="checked" label="Research data override">
                <Checkbox>允许显式选择未经认证的研究数据；生成的运行不可作为可信 Paper 输入</Checkbox>
              </Form.Item>
            </FormGrid>
          </FormSection>}
          {kind === "optimization" && <>
            <AdvancedFields label="高级优化设置">
              <FormGrid>
                {mode === "walk_forward" && <>
                  <Form.Item name="trainYears" label="训练年数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                  <Form.Item name="testYears" label="评价年数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                  <Form.Item name="validationMonths" label="Validation 月数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                  <Form.Item name="stepYears" label="滚动步长（年）"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                  <Form.Item className="form-field--wide" name="datasetVersion" label="冻结 Dataset Version" rules={[{ required: true, message: "必须选择已认证的 dataset version" }]}><Input placeholder="dataset:production:..." /></Form.Item>
                  <Form.Item className="form-field--wide" name="universeVersion" label="冻结 Universe Version" rules={[{ required: true, message: "必须记录 universe version" }]}><Input placeholder="universe:CSI300:..." /></Form.Item>
                  <Form.Item className="form-field--wide" name="adjustmentContract" label="复权契约" rules={[{ required: true }]}><Input /></Form.Item>
                  <Form.Item className="form-field--wide" name="featurePipelineVersion" label="特征流水线版本" rules={[{ required: true }]}><Input /></Form.Item>
                  <Form.Item name="labelHorizonDays" label="标签窗口（日）"><InputNumber min={0} style={{ width: "100%" }} /></Form.Item>
                </>}
                <Form.Item className="form-field--full" name="parameterGridJson" label="通用参数网格 JSON"><Input.TextArea rows={3} /></Form.Item>
                {mode === "multi_strategy" && <Form.Item className="form-field--full" name="parameterGridsJson" label="各项目参数网格（可选，以 projectId 为键）"><Input.TextArea rows={3} placeholder='{"project-id":{"period":[10,20,30]}}' /></Form.Item>}
              </FormGrid>
            </AdvancedFields>
          </>}
          {preview && <Alert style={{ marginBottom: 12 }} type={preview.withinLimit ? "success" : "error"} showIcon message={`将展开 ${preview.expandedCount} 个工作单元 · 上限 ${preview.limit} · 并发 ${preview.effectiveConcurrency}`} description={preview.warnings.join(" ") || "股票池和参数已经解析，可以排队。"} />}
          <FormActions><Button onClick={runPreview}>预览展开</Button><Button type="primary" htmlType="submit" icon={<PlayCircleOutlined />} loading={busy}>{isIndexScreening ? "运行筛选" : "确认并排队"}</Button></FormActions>
        </Form>
      </Card>
      <Card title="批次历史" style={{ marginTop: 16 }} extra={<Space>
        <Select value={compareMetric} onChange={setCompareMetric} style={{ width: 120 }} options={[
          { value: "sharpe", label: "Sharpe" },
          { value: "return", label: "收益" },
          { value: "drawdown", label: "回撤" },
          { value: "trades", label: "交易数" }
        ]} />
        <Button disabled={compareIds.length < 2} loading={busy} onClick={compareSelected}>比较已选（{compareIds.length}）</Button>
        <Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>
      </Space>}>
        <Table<ExperimentBatch>
          rowKey="id"
          size="small"
          dataSource={batches}
          rowSelection={{
            selectedRowKeys: compareIds,
            onChange: setCompareIds,
            getCheckboxProps: (row) => ({ disabled: !["success", "partial", "failed", "cancelled"].includes(row.status) })
          }}
          columns={[
          { title: "名称", dataIndex: "name" },
          { title: "模式", dataIndex: "mode", render: (value) => <Tag>{value}</Tag> },
          { title: "状态", dataIndex: "status", render: (value) => <Tag color={value === "success" ? "success" : value === "failed" ? "error" : value === "partial" ? "warning" : "processing"}>{value}</Tag> },
          { title: "进度", render: (_, row) => <Progress size="small" percent={row.total ? Math.round(completed(row) * 100 / row.total) : 0} /> },
          { title: "成功/失败", render: (_, row) => `${row.succeeded}/${row.failed}` },
          { title: "操作", render: (_, row) => <Space wrap>
            <Button size="small" onClick={() => open(row)}>详情</Button>
            <Popconfirm title="删除这个批次记录？" description="仅删除批次清单和批次快照；批次已经产生的回测/优化结果仍在各自页面管理。" okText="删除" okButtonProps={{ danger: true }} disabled={["queued", "running"].includes(row.status)} onConfirm={async () => { try { await api.deleteExperimentBatch(row.id); if (selected?.id === row.id) setSelected(undefined); message.success("批次记录已删除"); await reload(); } catch (error) { message.error((error as Error).message); } }}>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                aria-label={`删除批次 ${row.name || row.id}`}
                disabled={["queued", "running"].includes(row.status)}
              />
            </Popconfirm>
          </Space> }
        ]} />
      </Card>
      <Modal title={selected?.name || "批次详情"} open={Boolean(selected)} onCancel={() => setSelected(undefined)} width={1100} footer={selected && <Space>
        {["queued", "running"].includes(selected.status) && <Button danger icon={<StopOutlined />} onClick={async () => setSelected(await api.cancelExperimentBatch(selected.id))}>取消</Button>}
        {selected.failed > 0 && !selected.cancel_requested && <Button onClick={async () => setSelected(await api.retryExperimentBatch(selected.id))}>仅重试失败项</Button>}
        {Boolean(selected.cancel_requested) && selected.cancelled > 0 && <Button onClick={async () => setSelected(await api.restartExperimentBatch(selected.id))}>恢复未完成项</Button>}
        <Button icon={<DownloadOutlined />} href={api.experimentBatchExportUrl(selected.id)}>导出 CSV</Button>
        <Button onClick={() => setSelected(undefined)}>关闭</Button>
      </Space>}>
        {selected && <>
          <Alert showIcon type={selected.status === "success" ? "success" : selected.status === "partial" ? "warning" : "info"} message={`${selected.status} · ${completed(selected)}/${selected.total}`} description={`成功 ${selected.succeeded} · 失败 ${selected.failed} · 跳过 ${selected.skipped} · 取消 ${selected.cancelled}`} />
          {selected.walkForwardEvidence && <Card size="small" title="Train / Validation / 参数冻结 / OOS" style={{ marginTop: 12, marginBottom: 12 }}>
            <Alert
              showIcon
              type={selected.walkForwardEvidence.windows.every((window) => window.leakage?.decision === "ALLOW") ? "success" : "error"}
              message={`Dataset ${selected.walkForwardEvidence.dataset_version} · Universe ${selected.walkForwardEvidence.universe_version}`}
              description={`选择指标 ${selected.walkForwardEvidence.selection_metric} · ${selected.walkForwardEvidence.selection_rule}`}
            />
            <Table size="small" rowKey="id" pagination={false} dataSource={selected.walkForwardEvidence.windows} columns={[
              { title: "Fold", dataIndex: "fold" },
              { title: "Train", render: (_, row) => `${row.train_start} – ${row.train_end}` },
              { title: "Validation", render: (_, row) => `${row.validation_start} – ${row.validation_end}` },
              { title: "OOS", render: (_, row) => `${row.oos_start} – ${row.oos_end}` },
              { title: "泄漏检查", render: (_, row) => <Tag color={row.leakage?.decision === "ALLOW" ? "success" : "error"}>{row.leakage?.decision || "MISSING"}</Tag> },
              { title: "候选/选中", render: (_, row) => `${row.candidates?.length || 0}/${row.candidates?.filter((candidate: any) => Boolean(candidate.selected)).length || 0}` },
              { title: "OOS 状态", render: (_, row) => row.oosEvaluation?.status || "等待参数冻结" }
            ]} />
          </Card>}
          {(selected.summary?.walkForward?.length || 0) > 0 && <Card size="small" title="Train / Validation / OOS 表现" style={{ marginTop: 12, marginBottom: 12 }}>
            <LeanChart style={{ height: 340 }} option={phaseOption([{
              id: selected.id,
              name: selected.name,
              kind: selected.kind,
              mode: selected.mode,
              status: selected.status,
              createdAt: selected.created_at,
              rank: 1,
              metrics: { runs: 0, successes: 0 },
              parameterSensitivity: selected.summary?.parameterSensitivity || [],
              phaseSeries: selected.summary?.walkForward || []
            }])} />
          </Card>}
          {(selected.summary?.parameterSensitivity || []).map((sensitivity) => <Card key={`${sensitivity.xParameter}:${sensitivity.yParameter}`} size="small" title={`参数敏感性 · ${sensitivity.xParameter} × ${sensitivity.yParameter}`} style={{ marginBottom: 12 }}>
            <LeanChart style={{ height: 380 }} option={sensitivityOption(sensitivity)} />
          </Card>)}
          <Table size="small" rowKey={(row) => String(row.itemId)} dataSource={ranking} pagination={{ pageSize: 20 }} columns={[
            { title: "股票", dataIndex: "symbol" }, { title: "项目", dataIndex: "projectId", ellipsis: true },
            { title: "状态", dataIndex: "status" }, { title: "Sharpe", dataIndex: "sharpe" },
            { title: "收益", dataIndex: "return" }, { title: "回撤", dataIndex: "drawdown" },
            { title: "交易", dataIndex: "trades" },
            { title: "结果", render: (_, row: any) => row.runId ? <a href={`#/runs/${row.runId}`}>打开</a> : "-" },
            { title: "错误", dataIndex: "error", ellipsis: true }
          ]} />
        </>}
      </Modal>
      <Modal title={`跨批次比较 · ${comparison?.rankingMetric || compareMetric}`} open={Boolean(comparison)} onCancel={() => setComparison(undefined)} width={1280} footer={<Button onClick={() => setComparison(undefined)}>关闭</Button>}>
        {comparison && <>
          <Alert showIcon type="info" message={`按成功运行的${comparison.rankingBasis}排名`} description={`共比较 ${comparison.batches.length} 个批次；排名指标 ${comparison.rankingMetric}。`} />
          <Table
            style={{ marginTop: 12 }}
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={comparison.batches}
            columns={[
              { title: "排名", dataIndex: "rank", width: 70 },
              { title: "批次", dataIndex: "name" },
              { title: "模式", dataIndex: "mode", render: (value) => <Tag>{value}</Tag> },
              { title: "排名值", dataIndex: "rankingValue", render: metricText },
              { title: "Sharpe 中位", render: (_, row) => metricText(typeof row.metrics.sharpe === "object" ? row.metrics.sharpe.median : null) },
              { title: "收益中位", render: (_, row) => metricText(typeof row.metrics.return === "object" ? row.metrics.return.median : null) },
              { title: "回撤中位", render: (_, row) => metricText(typeof row.metrics.drawdown === "object" ? row.metrics.drawdown.median : null) },
              { title: "成功/总数", render: (_, row) => `${row.metrics.successes}/${row.metrics.runs}` },
              { title: "最佳运行", render: (_, row) => row.bestRun?.runId ? <a href={`#/runs/${row.bestRun.runId}`}>打开</a> : "-" }
            ]}
          />
          {comparison.batches.some((batch) => batch.phaseSeries.length > 0) && <Card size="small" title="Train / Validation / OOS 并排表现" style={{ marginTop: 12 }}>
            <LeanChart style={{ height: 420 }} option={phaseOption(comparison.batches)} />
          </Card>}
          {comparison.batches.flatMap((batch) => batch.parameterSensitivity.map((sensitivity) => ({ batch, sensitivity }))).map(({ batch, sensitivity }) => <Card key={`${batch.id}:${sensitivity.xParameter}:${sensitivity.yParameter}`} size="small" title={`${batch.name} · ${sensitivity.xParameter} × ${sensitivity.yParameter}`} style={{ marginTop: 12 }}>
            <LeanChart style={{ height: 380 }} option={sensitivityOption(sensitivity)} />
          </Card>)}
        </>}
      </Modal>
    </>
  );
}
