import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import {
  DownloadOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SlidersOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import dayjs from "dayjs";

import { api } from "../../api";
import type {
  DataScope,
  ExperimentBatchComparison,
  ExperimentBatchPreview,
  OptimizationRequest,
  OptimizationRun,
  PortfolioOptimizationCandidate,
  PortfolioOptimizationRun,
  Project,
  StrategyParameter,
  StrategyTemplate,
} from "../../api";
import { defaultSettings } from "../../config/defaults";
import { useAsyncData } from "../../hooks";
import { shortValue } from "../../utils/display";
import { CompareRunsPanel } from "../../pages/compare";
import { DateStringPicker } from "../DateStringPicker";
import { ExampleGallery } from "../examples/ExampleGallery";
import { FormActions, FormGrid, FormSection } from "../forms/FormLayout";
import { StatusTag } from "../../components";


const MODE_OPTIONS = [
  { value: "single_symbol_grid", label: "单标的参数网格" },
  { value: "universe_robust", label: "股票池稳健性" },
  { value: "walk_forward", label: "Walk-forward" },
  { value: "multi_strategy", label: "多策略优化" },
];

const OBJECTIVES = [
  { value: "sharpe", label: "最大 Sharpe" },
  { value: "return", label: "最大收益" },
  { value: "drawdown", label: "最小回撤" },
];

function parseGrid(text: unknown): unknown[] {
  const source = String(text ?? "").trim();
  if (!source) return [];
  const range = source.match(/^(-?\d+(?:\.\d+)?):(-?\d+(?:\.\d+)?):(\d+(?:\.\d+)?)$/);
  if (range) {
    const start = Number(range[1]);
    const end = Number(range[2]);
    const step = Number(range[3]);
    if (step <= 0) return [];
    const values = [];
    for (let value = start; value <= end + step / 1000 && values.length < 1000; value += step) {
      values.push(Number(value.toFixed(10)));
    }
    return values;
  }
  return source.split(",").map((item) => item.trim()).filter(Boolean).map((item) => {
    if (item.toLowerCase() === "true") return true;
    if (item.toLowerCase() === "false") return false;
    const value = Number(item);
    return Number.isFinite(value) ? value : item;
  });
}

function projectTemplate(project: Project | undefined, templates: StrategyTemplate[]) {
  const key = String(project?.config?.templateKey ?? "");
  return templates.find((item) => item.key === key);
}

function projectLabel(project: Project) {
  return project.display_name || project.name;
}

export function OptimizationCenter() {
  const [searchParams] = useSearchParams();
  const projects = useAsyncData<Project[]>(api.projects, []);
  const templates = useAsyncData<StrategyTemplate[]>(api.strategyTemplates, []);
  const optimizations = useAsyncData<OptimizationRun[]>(api.optimizations, []);
  const portfolioCandidates = useAsyncData<PortfolioOptimizationCandidate[]>(
    api.portfolioOptimizationCandidates,
    [],
    false,
    "portfolio-optimization:candidates",
  );
  const portfolioRuns = useAsyncData<PortfolioOptimizationRun[]>(api.portfolioOptimizations, []);
  const [form] = Form.useForm();
  const [portfolioForm] = Form.useForm();
  const [preview, setPreview] = useState<ExperimentBatchPreview & { scopeHash?: string; dataFingerprint?: string }>();
  const [portfolioPreview, setPortfolioPreview] = useState<Record<string, unknown>>();
  const [selected, setSelected] = useState<OptimizationRun>();
  const [selectedPortfolio, setSelectedPortfolio] = useState<PortfolioOptimizationRun>();
  const [busy, setBusy] = useState(false);
  const [gridText, setGridText] = useState<Record<string, Record<string, string>>>({});
  const [fixedParameters, setFixedParameters] = useState<Record<string, Record<string, unknown>>>({});
  const [optimizationCompareIds, setOptimizationCompareIds] = useState<string[]>([]);
  const [optimizationComparison, setOptimizationComparison] = useState<ExperimentBatchComparison>();
  const mode = Form.useWatch("mode", form) || "single_symbol_grid";
  const projectIds: string[] = Form.useWatch("projectIds", form) || [];
  const scopeType = Form.useWatch("scopeType", form) || "symbols";

  const selectedProjects = useMemo(
    () => projectIds.map((id) => projects.data.find((project) => project.id === id)).filter(Boolean) as Project[],
    [projectIds, projects.data],
  );

  function initializeProjectParameters(
    ids: string[],
    schemas?: Record<string, StrategyParameter[]>,
    fixedSeed?: Record<string, Record<string, unknown>>,
  ) {
    const nextGrid = { ...gridText };
    const nextFixed = { ...(fixedSeed || fixedParameters) };
    ids.forEach((id) => {
      const project = projects.data.find((item) => item.id === id);
      const parameters = schemas?.[id] || projectTemplate(project, templates.data)?.parameters || [];
      nextGrid[id] = nextGrid[id] || {};
      nextFixed[id] = nextFixed[id] || {};
      parameters.forEach((parameter) => {
        if (nextGrid[id][parameter.key] === undefined) nextGrid[id][parameter.key] = String(parameter.default ?? "");
        if (nextFixed[id][parameter.key] === undefined) nextFixed[id][parameter.key] = parameter.default;
      });
    });
    setGridText(nextGrid);
    setFixedParameters(nextFixed);
  }

  useEffect(() => {
    const sourceBacktestRunId = searchParams.get("sourceBacktestRunId");
    if (!sourceBacktestRunId || !projects.data.length || !templates.data.length) return;
    let active = true;
    api.backtestOptimizationDraft(sourceBacktestRunId)
      .then((draft) => {
        if (!active) return;
        const scope = draft.dataScope;
        form.setFieldsValue({
          name: draft.name,
          mode: "single_symbol_grid",
          projectIds: draft.projectIds,
          scopeType: scope.selection.type === "universe" ? "universe" : "symbols",
          symbols: scope.selection.values.join(","),
          market: scope.asset.market,
          venue: scope.asset.venue || scope.asset.market,
          assetClass: scope.asset.assetClass,
          resolution: scope.asset.resolution,
          dataType: scope.asset.dataType,
          start: scope.time.startDate,
          end: scope.time.endDate,
          adjust: scope.price.adjust,
          provider: scope.provider.source,
          providerMode: scope.provider.mode,
          allowResearchSource: scope.provider.allowResearchSource,
          cash: draft.execution?.cash,
          benchmarkSymbol: draft.execution?.benchmarkSymbol,
          feeModel: draft.execution?.feeModel || "default",
          slippageModel: draft.execution?.slippageModel || "default",
          dockerImage: draft.execution?.dockerImage || defaultSettings.dockerImage,
          objective: draft.objective || "sharpe",
          sourceBacktestRunId,
        });
        initializeProjectParameters(
          draft.projectIds,
          draft.parameterSchemas,
          draft.fixedParametersByProject || {},
        );
        message.success("已载入回测数据口径与策略参数");
      })
      .catch((error) => message.error((error as Error).message));
    return () => { active = false; };
  }, [form, projects.data.length, searchParams, templates.data.length]);

  useEffect(() => {
    if (!optimizations.data.some((item) => ["queued", "running"].includes(item.status))) return;
    const timer = window.setInterval(() => void optimizations.reload(), 4000);
    return () => window.clearInterval(timer);
  }, [optimizations.data]);

  function payload(values: Record<string, any>): OptimizationRequest {
    const valuesList = String(values.symbols || "")
      .split(/[\s,]+/)
      .map((value) => value.trim().toUpperCase())
      .filter(Boolean);
    const parameterGrids = Object.fromEntries(
      values.projectIds.map((projectId: string) => [
        projectId,
        Object.fromEntries(
          Object.entries(gridText[projectId] || {})
            .map(([key, value]) => [key, parseGrid(value)])
            .filter(([, entries]) => (entries as unknown[]).length > 0),
        ),
      ]),
    );
    const dataScope: DataScope = {
      asset: {
        assetClass: values.assetClass,
        market: values.market,
        venue: values.venue || values.market,
        resolution: values.resolution,
        dataType: values.dataType,
      },
      selection: { type: values.scopeType, values: valuesList },
      time: { startDate: values.start, endDate: values.end, asOfDate: values.start },
      price: { adjust: values.adjust },
      provider: {
        source: values.provider,
        mode: values.providerMode,
        allowResearchSource: Boolean(values.allowResearchSource),
      },
    };
    return {
      name: values.name,
      mode: values.mode,
      projectIds: values.projectIds,
      dataScope,
      execution: {
        cash: Number(values.cash),
        benchmarkSymbol: values.benchmarkSymbol,
        feeModel: values.feeModel,
        slippageModel: values.slippageModel,
        dockerImage: values.dockerImage,
      },
      fixedParametersByProject: fixedParameters,
      parameterGrids,
      objective: values.objective,
      minCoverage: Number(values.minCoverage),
      maxCandidates: Number(values.maxCandidates),
      walkForward: values.mode === "walk_forward" ? {
        trainYears: Number(values.trainYears),
        testYears: Number(values.testYears),
        stepYears: Number(values.stepYears),
        validationMonths: Number(values.validationMonths),
      } : undefined,
      sourceBacktestRunId: values.sourceBacktestRunId || undefined,
    };
  }

  async function runPreview() {
    setBusy(true);
    try {
      setPreview(await api.optimizationPreview(payload(await form.validateFields())));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function submit(values: Record<string, any>) {
    setBusy(true);
    try {
      const body = payload(values);
      const report = preview || await api.optimizationPreview(body);
      if (!report.withinLimit) throw new Error(report.warnings.join(" "));
      await api.createOptimization(body);
      setPreview(undefined);
      message.success(`优化已排队：${report.parameterCandidates || "-"} 个参数候选，${report.expandedCount} 个工作单元`);
      await optimizations.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openOptimization(run: OptimizationRun) {
    try {
      setSelected(await api.optimization(run.id));
    } catch (error) {
      message.error((error as Error).message);
    }
  }

  async function previewPortfolio() {
    setBusy(true);
    try {
      const values = await portfolioForm.validateFields();
      setPortfolioPreview(await api.previewPortfolioOptimization({
        name: values.name,
        runIds: values.runIds as string[],
        objective: values.objective,
        step: Number(values.step),
        maxWeight: Number(values.maxWeight),
        allowShort: false,
      }) as unknown as Record<string, unknown>);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function createPortfolio(values: Record<string, any>) {
    setBusy(true);
    try {
      const created = await api.optimizePortfolio({
        name: String(values.name),
        runIds: values.runIds as string[],
        objective: values.objective,
        step: Number(values.step),
        maxWeight: Number(values.maxWeight),
        allowShort: false,
      });
      setSelectedPortfolio(created);
      setPortfolioPreview(undefined);
      message.success("组合优化已固化，可从历史运行中复查");
      await portfolioRuns.reload();
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function compareOptimizations() {
    if (optimizationCompareIds.length < 2) return;
    setBusy(true);
    try {
      setOptimizationComparison(await api.compareOptimizations({ optimizationIds: optimizationCompareIds }));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const optimizationDetail = selected?.summary;
  const portfolioResult = selectedPortfolio?.result;

  return (
    <>
      <div className="toolbar">
        <div>
          <h1 className="page-title">Optimization Center</h1>
          <span className="muted">统一配置参数寻优、稳健性验证、组合权重和运行比较</span>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void Promise.all([optimizations.reload(), portfolioRuns.reload(), portfolioCandidates.reload()])}>刷新</Button>
      </div>
      <Tabs
        destroyOnHidden={false}
        items={[
          {
            key: "create",
            label: "Create Optimization",
            children: (
              <>
                <ExampleGallery kind="optimization" onCreated={() => projects.reload()} />
                <Card title="优化契约" style={{ marginTop: 16 }}>
                  <Form
                    form={form}
                    layout="vertical"
                    onFinish={submit}
                    initialValues={{
                      name: "Strategy Optimization",
                      mode: "single_symbol_grid",
                      projectIds: [],
                      scopeType: "symbols",
                      symbols: "000001",
                      assetClass: "equity",
                      market: "china",
                      venue: "china",
                      resolution: "daily",
                      dataType: "trade",
                      start: dayjs().subtract(5, "year").format("YYYY-MM-DD"),
                      end: dayjs().format("YYYY-MM-DD"),
                      adjust: "raw",
                      provider: "tushare",
                      providerMode: "strict",
                      cash: 300000,
                      benchmarkSymbol: "000300",
                      feeModel: "default",
                      slippageModel: "default",
                      dockerImage: defaultSettings.dockerImage,
                      objective: "sharpe",
                      minCoverage: 0.8,
                      maxCandidates: 200,
                      trainYears: 3,
                      testYears: 1,
                      stepYears: 1,
                      validationMonths: 6,
                    }}
                  >
                    <FormSection title="模式与策略" description="模式只改变候选如何展开；每个候选仍走标准回测预检、调度和结果契约。">
                      <FormGrid>
                        <Form.Item className="form-field--wide" name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
                        <Form.Item name="mode" label="模式"><Select options={MODE_OPTIONS} onChange={() => setPreview(undefined)} /></Form.Item>
                        <Form.Item className="form-field--wide" name="projectIds" label="策略项目" rules={[{ required: true }]}>
                          <Select
                            mode="multiple"
                            options={projects.data.map((project) => ({ value: project.id, label: projectLabel(project) }))}
                            onChange={(ids) => { initializeProjectParameters(ids); setPreview(undefined); }}
                          />
                        </Form.Item>
                        <Form.Item name="objective" label="唯一目标"><Select options={OBJECTIVES} /></Form.Item>
                        <Form.Item name="minCoverage" label="最低成功覆盖"><InputNumber min={0.5} max={1} step={0.05} style={{ width: "100%" }} /></Form.Item>
                      </FormGrid>
                    </FormSection>
                    <FormSection title="DataScope" description="与 Research、Backtest 共用同一资产、标的、时间、复权和来源结构。">
                      <FormGrid>
                        <Form.Item name="scopeType" label="标的类型"><Select options={[{ value: "symbols", label: "代码列表" }, { value: "universe", label: "PIT 股票池" }, { value: "products", label: "产品列表" }]} /></Form.Item>
                        <Form.Item className="form-field--wide" name="symbols" label={scopeType === "universe" ? "股票池代码" : "标的代码"} rules={[{ required: true }]}><Input placeholder={scopeType === "universe" ? "CSI300" : "000001,600519"} /></Form.Item>
                        <Form.Item name="assetClass" label="资产"><Select options={["equity", "future", "crypto", "option"].map((value) => ({ value, label: value }))} /></Form.Item>
                        <Form.Item name="market" label="市场"><Select options={["china", "hongkong", "usa"].map((value) => ({ value, label: value }))} /></Form.Item>
                        <Form.Item name="venue" label="Venue"><Input /></Form.Item>
                        <Form.Item name="resolution" label="频率"><Select options={["daily", "hour", "minute"].map((value) => ({ value, label: value }))} /></Form.Item>
                        <Form.Item name="dataType" label="数据类型"><Input /></Form.Item>
                        <Form.Item name="start" label="开始"><DateStringPicker /></Form.Item>
                        <Form.Item name="end" label="结束"><DateStringPicker /></Form.Item>
                        <Form.Item name="adjust" label="复权"><Select options={["raw", "qfq", "hfq"].map((value) => ({ value, label: value }))} /></Form.Item>
                        <Form.Item name="provider" label="数据来源"><Input /></Form.Item>
                        <Form.Item name="providerMode" label="来源模式"><Select options={[{ value: "strict", label: "Strict" }, { value: "fallback", label: "Fallback" }]} /></Form.Item>
                      </FormGrid>
                    </FormSection>
                    <FormSection title="执行假设">
                      <FormGrid>
                        <Form.Item name="cash" label="初始资金"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                        <Form.Item name="benchmarkSymbol" label="基准"><Input /></Form.Item>
                        <Form.Item name="feeModel" label="费用模型"><Select options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero (research)" }]} /></Form.Item>
                        <Form.Item name="slippageModel" label="滑点模型"><Select options={[{ value: "default", label: "Default" }, { value: "zero", label: "Zero" }]} /></Form.Item>
                        <Form.Item className="form-field--wide" name="dockerImage" label="Docker Image"><Input /></Form.Item>
                        <Form.Item name="maxCandidates" label="候选上限"><InputNumber min={1} max={1000} style={{ width: "100%" }} /></Form.Item>
                      </FormGrid>
                    </FormSection>
                    <FormSection title="Parameter Grid" description="逗号枚举，例如 5,10,20；或范围 start:end:step，例如 5:30:5。">
                      {selectedProjects.length ? selectedProjects.map((project) => {
                        const parameters = projectTemplate(project, templates.data)?.parameters || [];
                        return (
                          <Card key={project.id} size="small" title={projectLabel(project)} style={{ marginBottom: 12 }}>
                            <FormGrid>
                              {parameters.map((parameter) => (
                                <Form.Item key={parameter.key} label={parameter.label}>
                                  <Input
                                    value={gridText[project.id]?.[parameter.key] ?? ""}
                                    onChange={(event) => {
                                      setGridText((current) => ({
                                        ...current,
                                        [project.id]: { ...(current[project.id] || {}), [parameter.key]: event.target.value },
                                      }));
                                      setPreview(undefined);
                                    }}
                                  />
                                </Form.Item>
                              ))}
                            </FormGrid>
                          </Card>
                        );
                      }) : <Alert type="info" showIcon message="先选择策略项目，参数控件会按模板动态生成。" />}
                    </FormSection>
                    {mode === "walk_forward" && (
                      <FormSection title="Walk-forward 窗口">
                        <FormGrid>
                          <Form.Item name="trainYears" label="训练年数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                          <Form.Item name="validationMonths" label="验证月数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                          <Form.Item name="testYears" label="评估年数"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                          <Form.Item name="stepYears" label="滚动步长"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
                        </FormGrid>
                      </FormSection>
                    )}
                    {preview && (
                      <Alert
                        type={preview.withinLimit ? "success" : "error"}
                        showIcon
                        style={{ marginBottom: 16 }}
                        message={`${preview.parameterCandidates || 0} 个参数候选 → ${preview.expandedCount} 个标准回测工作单元`}
                        description={[...(preview.warnings || []), preview.scopeHash ? `Scope ${preview.scopeHash.slice(0, 12)}` : ""].filter(Boolean).join(" · ")}
                      />
                    )}
                    <FormActions>
                      <Button onClick={() => void runPreview()} loading={busy}>预览展开</Button>
                      <Button type="primary" icon={<SlidersOutlined />} htmlType="submit" loading={busy} disabled={preview?.withinLimit === false}>创建优化</Button>
                    </FormActions>
                  </Form>
                </Card>
              </>
            ),
          },
          {
            key: "runs",
            label: "Optimization Runs",
            children: (
              <Card title="优化运行">
                <Table<OptimizationRun>
                  rowKey="id"
                  size="small"
                  dataSource={optimizations.data}
                  pagination={{ pageSize: 15 }}
                  columns={[
                    { title: "名称", render: (_, run) => <Button type="link" onClick={() => void openOptimization(run)}>{run.name}</Button> },
                    { title: "模式", dataIndex: "mode" },
                    { title: "目标", render: (_, run) => run.objective_metric || run.summary?.rankingMetric || "sharpe" },
                    { title: "状态", dataIndex: "status", render: (status) => <StatusTag status={status} /> },
                    { title: "进度", render: (_, run) => <Progress size="small" percent={run.total ? Math.round(((run.succeeded + run.failed + run.skipped + run.cancelled) / run.total) * 100) : 0} /> },
                    { title: "最佳候选", render: (_, run) => shortValue(run.summary?.bestCandidate || run.summary?.candidates?.[0] || "—") },
                    { title: "创建时间", dataIndex: "created_at" },
                    {
                      title: "操作",
                      render: (_, run) => (
                        <Space>
                          {["queued", "running"].includes(run.status) && <Button size="small" danger icon={<StopOutlined />} onClick={async () => { await api.cancelOptimization(run.id); await optimizations.reload(); }}>取消</Button>}
                          {["failed", "partial"].includes(run.status) && <Button size="small" onClick={async () => { await api.retryOptimization(run.id); await optimizations.reload(); }}>重试失败项</Button>}
                          <Button size="small" icon={<DownloadOutlined />} href={api.optimizationExportUrl(run.id)}>CSV</Button>
                          {!["queued", "running"].includes(run.status) && <Button size="small" onClick={async () => { await api.archiveOptimization(run.id); await optimizations.reload(); }}>归档</Button>}
                        </Space>
                      ),
                    },
                  ]}
                />
              </Card>
            ),
          },
          {
            key: "portfolio",
            label: "Portfolio Builder",
            children: (
              <>
                <Card title="组合权重契约">
                  <Alert
                    type="info"
                    showIcon
                    message="只能选择已通过策略准入、币种一致、频率一致且至少有 60 个重叠净值点的回测。混合币种必须先定义 FX 归一化契约。"
                    style={{ marginBottom: 16 }}
                  />
                  {portfolioCandidates.error && (
                    <Alert
                      type="error"
                      showIcon
                      message="组合候选加载失败"
                      description={portfolioCandidates.error.message}
                      action={<Button size="small" onClick={() => void portfolioCandidates.reload()}>重试</Button>}
                      style={{ marginBottom: 16 }}
                    />
                  )}
                  <Form form={portfolioForm} layout="vertical" onFinish={createPortfolio} initialValues={{ name: "Portfolio Optimization", objective: "sharpe", step: 0.1, maxWeight: 1 }}>
                    <FormGrid>
                      <Form.Item className="form-field--wide" name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
                      <Form.Item className="form-field--full" name="runIds" label="回测运行" rules={[{ required: true }]}>
                        <Select
                          mode="multiple"
                          optionFilterProp="label"
                          options={portfolioCandidates.data.map((candidate) => ({
                            value: candidate.id,
                            disabled: !candidate.admissionEligible,
                            label: `${candidate.name || candidate.symbol || candidate.id} · ${candidate.currency}/${candidate.resolution} · ${candidate.points} 点${candidate.admissionEligible ? "" : " · 未准入"}`,
                          }))}
                        />
                      </Form.Item>
                      <Form.Item name="objective" label="目标"><Select options={OBJECTIVES} /></Form.Item>
                      <Form.Item name="step" label="权重步长"><InputNumber min={0.01} max={0.5} step={0.05} style={{ width: "100%" }} /></Form.Item>
                      <Form.Item name="maxWeight" label="单策略上限"><InputNumber min={0.01} max={1} step={0.05} style={{ width: "100%" }} /></Form.Item>
                    </FormGrid>
                    {portfolioPreview && <Alert type="success" showIcon style={{ marginBottom: 16 }} message={`${portfolioPreview.baseCurrency}/${portfolioPreview.resolution} · ${portfolioPreview.alignedPoints} 个对齐点 · ${portfolioPreview.candidateCount} 个权重候选`} />}
                    <FormActions>
                      <Button onClick={() => void previewPortfolio()} loading={busy}>验证与预览</Button>
                      <Button type="primary" htmlType="submit" loading={busy}>计算并固化</Button>
                    </FormActions>
                  </Form>
                </Card>
                <Card title="组合优化历史" style={{ marginTop: 16 }}>
                  <Table<PortfolioOptimizationRun>
                    rowKey="id"
                    size="small"
                    dataSource={portfolioRuns.data}
                    columns={[
                      { title: "名称", render: (_, run) => <Button type="link" onClick={() => setSelectedPortfolio(run)}>{run.name}</Button> },
                      { title: "状态", dataIndex: "status", render: (status) => <StatusTag status={status} /> },
                      { title: "目标", dataIndex: "objective" },
                      { title: "输入", render: (_, run) => `${run.runIds.length} runs` },
                      { title: "币种/频率", render: (_, run) => `${run.base_currency || "—"} / ${run.resolution || "—"}` },
                      { title: "创建时间", dataIndex: "created_at" },
                      { title: "操作", render: (_, run) => <Button size="small" onClick={async () => { await api.archivePortfolioOptimization(run.id); await portfolioRuns.reload(); }}>归档</Button> },
                    ]}
                  />
                </Card>
              </>
            ),
          },
          {
            key: "compare",
            label: "Compare Results",
            children: (
              <>
                <Card title="比较优化批次">
                  <Space wrap>
                    <Select
                      mode="multiple"
                      style={{ minWidth: 480 }}
                      value={optimizationCompareIds}
                      onChange={setOptimizationCompareIds}
                      options={optimizations.data.filter((item) => ["success", "partial"].includes(item.status)).map((item) => ({ value: item.id, label: `${item.name} · ${item.mode}` }))}
                    />
                    <Button icon={<ExperimentOutlined />} disabled={optimizationCompareIds.length < 2} loading={busy} onClick={() => void compareOptimizations()}>比较</Button>
                  </Space>
                  {optimizationComparison && (
                    <Table<any>
                      style={{ marginTop: 16 }}
                      size="small"
                      pagination={false}
                      rowKey="id"
                      dataSource={optimizationComparison.batches}
                      columns={[
                        { title: "排名", dataIndex: "rank" },
                        { title: "优化", dataIndex: "name" },
                        { title: "模式", dataIndex: "mode" },
                        { title: "中位目标", dataIndex: "rankingValue", render: shortValue },
                        { title: "成功运行", render: (_, row) => `${row.metrics.successes}/${row.metrics.runs}` },
                      ]}
                    />
                  )}
                </Card>
                <Card title="比较回测运行" style={{ marginTop: 16 }}><CompareRunsPanel /></Card>
              </>
            ),
          },
        ]}
      />
      <Modal open={Boolean(selected)} width={1100} title={selected?.name} onCancel={() => setSelected(undefined)} footer={null}>
        {selected && (
          <>
            <Descriptions size="small" column={3} bordered items={[
              { key: "status", label: "状态", children: <StatusTag status={selected.status} /> },
              { key: "mode", label: "模式", children: selected.mode },
              { key: "objective", label: "目标", children: optimizationDetail?.rankingMetric || selected.objective_metric || "sharpe" },
              { key: "scope", label: "Scope Hash", children: selected.scope_hash?.slice(0, 16) || "—" },
              { key: "data", label: "Data Fingerprint", children: selected.data_fingerprint?.slice(0, 16) || "—" },
              { key: "coverage", label: "最低覆盖", children: optimizationDetail?.minCoverage ?? "—" },
            ]} />
            <Table<Record<string, any>>
              style={{ marginTop: 16 }}
              size="small"
              rowKey={(row) => String(row.key)}
              dataSource={(optimizationDetail?.candidates || []) as Array<Record<string, any>>}
              columns={[
                { title: "候选", dataIndex: "candidateKey" },
                { title: "参数", dataIndex: "overrides", render: (value) => shortValue(value) },
                { title: "覆盖", dataIndex: "coverage", render: (value) => `${(Number(value) * 100).toFixed(0)}%` },
                { title: "目标中位数", dataIndex: "medianObjective", render: (value) => shortValue(value) },
                { title: "有效", dataIndex: "valid", render: (value) => value ? <Tag color="green">VALID</Tag> : <Tag color="red">REJECTED</Tag> },
              ]}
            />
          </>
        )}
      </Modal>
      <Modal open={Boolean(selectedPortfolio)} width={900} title={selectedPortfolio?.name} onCancel={() => setSelectedPortfolio(undefined)} footer={null}>
        {portfolioResult ? (
          <>
            <Descriptions size="small" column={3} bordered items={[
              { key: "currency", label: "币种", children: portfolioResult.baseCurrency },
              { key: "resolution", label: "频率", children: portfolioResult.resolution },
              { key: "points", label: "对齐点", children: portfolioResult.alignedPoints },
              { key: "range", label: "区间", children: `${portfolioResult.alignedStart} → ${portfolioResult.alignedEnd}` },
              { key: "candidates", label: "候选", children: portfolioResult.candidateCount },
              { key: "objective", label: "目标", children: portfolioResult.objective },
            ]} />
            <Table
              style={{ marginTop: 16 }}
              size="small"
              pagination={false}
              rowKey="runId"
              dataSource={Object.entries(portfolioResult.weights).map(([runId, weight]) => ({ runId, weight }))}
              columns={[
                { title: "回测运行", dataIndex: "runId" },
                { title: "权重", dataIndex: "weight", render: (value) => `${(Number(value) * 100).toFixed(1)}%` },
              ]}
            />
          </>
        ) : <Alert type="error" showIcon message={selectedPortfolio?.error || "结果不可用"} />}
      </Modal>
    </>
  );
}
