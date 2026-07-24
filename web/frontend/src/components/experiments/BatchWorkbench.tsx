import { Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Space, Table, Tag, message } from "antd";
import { DeleteOutlined, DownloadOutlined, PlayCircleOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";

import { api } from "../../api";
import type { ExperimentBatch, ExperimentBatchPreview, Project } from "../../api";
import { DateStringPicker } from "../DateStringPicker";
import { AdvancedFields, FormActions, FormGrid, FormSection } from "../forms/FormLayout";


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


export function BatchWorkbench({ kind, projects }: { kind: "backtest" | "optimization" | "research"; projects: Project[] }) {
  const [form] = Form.useForm();
  const [preview, setPreview] = useState<ExperimentBatchPreview>();
  const [batches, setBatches] = useState<ExperimentBatch[]>([]);
  const [selected, setSelected] = useState<ExperimentBatch>();
  const [busy, setBusy] = useState(false);
  const symbolSource = Form.useWatch("symbolSource", form) || "symbols";
  const mode = Form.useWatch("mode", form) || MODES[kind][0].value;

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
    const applyExample = (event: Event) => {
      const detail = (event as CustomEvent).detail as { example?: { kind?: string; mode?: string }; project?: Project; launch?: { defaults?: Record<string, unknown> } };
      if (detail.example?.kind !== kind || !detail.project) return;
      const defaults = detail.launch?.defaults || {};
      form.setFieldsValue({
        ...defaults,
        mode: detail.example.mode || MODES[kind][0].value,
        projectIds: [detail.project.id],
        symbolSource: defaults.universeCode ? "universe" : "symbols",
        symbols: defaults.symbol || "000001",
        parameterGridJson: defaults.parameterGrid ? JSON.stringify(defaults.parameterGrid) : form.getFieldValue("parameterGridJson")
      });
      setPreview(undefined);
    };
    window.addEventListener("lean-example-instantiated", applyExample);
    return () => window.removeEventListener("lean-example-instantiated", applyExample);
  }, [form, kind]);
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
    return {
      ...values,
      kind,
      projectIds,
      symbols: values.symbolSource === "symbols" ? symbols : [],
      universeCode: values.symbolSource === "universe" || mode === "dynamic_universe" ? values.universeCode : undefined,
      asOfDate: values.asOfDate || values.start,
      parameterGrid,
      parameterGrids,
      factorNames: String(values.factorNames || "").split(/[\s,]+/).filter(Boolean)
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

  const activeProjectRequired = kind !== "research" || mode !== "analysis";
  const completed = (batch: ExperimentBatch) => batch.succeeded + batch.failed + batch.skipped + batch.cancelled;
  const ranking = useMemo(() => selected?.summary?.ranking || [], [selected]);

  return (
    <>
      <Card title={kind === "backtest" ? "批量回测" : kind === "optimization" ? "批量优化" : "快捷研究任务"} style={{ marginTop: 16 }}>
        <Form form={form} layout="vertical" onFinish={submit} initialValues={{
          name: kind === "backtest" ? "Batch Backtest" : kind === "optimization" ? "Batch Optimization" : "Research Analysis",
          mode: MODES[kind][0].value, symbolSource: "symbols", symbols: "000001", universeCode: "CSI300",
          start: dayjs().subtract(5, "year").format("YYYY-MM-DD"), end: dayjs().format("YYYY-MM-DD"), cash: 300000,
          maxCandidates: 200, trainYears: 3, testYears: 1, validationMonths: 6, stepYears: 1,
          adjustmentContract: "raw-v1", featurePipelineVersion: "features-v1", labelHorizonDays: 0,
          factorNames: "momentum,volatility", parameterGridJson: '{"fast":[5,10,20],"slow":[30,60]}'
        }}>
          <FormSection title="批次与标的">
          <FormGrid>
            <Form.Item className="form-field--wide" name="name" label="批次名称" rules={[{ required: true }]}><Input /></Form.Item>
            <Form.Item name="mode" label="运行模式"><Select options={MODES[kind]} onChange={() => setPreview(undefined)} /></Form.Item>
            {activeProjectRequired && <Form.Item className="form-field--wide" name="projectIds" label="项目" rules={[{ required: true }]}><Select mode="multiple" options={projects.map((project) => ({ value: project.id, label: project.display_name || project.name }))} /></Form.Item>}
            {kind !== "research" && <Form.Item name="symbolSource" label="标的来源"><Select options={[{ value: "symbols", label: "股票代码" }, { value: "universe", label: "PIT股票池" }]} /></Form.Item>}
            {kind !== "research" && symbolSource === "symbols" && mode !== "dynamic_universe" && <Form.Item className="form-field--wide" name="symbols" label="股票代码"><Input.TextArea rows={2} placeholder="000001,600519" /></Form.Item>}
            {kind !== "research" && (symbolSource === "universe" || mode === "dynamic_universe") && <Form.Item name="universeCode" label="股票池"><Select options={["CSI300", "CSI500", "CSI1000", "SSE50", "STAR50", "ALL_A"].map((value) => ({ value, label: value }))} /></Form.Item>}
            {kind === "research" && <Form.Item className="form-field--wide" name="factorNames" label="因子/研究项"><Input placeholder="momentum,volatility" /></Form.Item>}
          </FormGrid>
          </FormSection>
          {kind !== "research" && <FormSection title="回测范围">
          <FormGrid>
            <Form.Item name="start" label="开始日期"><DateStringPicker /></Form.Item>
            <Form.Item name="end" label="结束日期"><DateStringPicker /></Form.Item>
            <Form.Item name="cash" label="每个运行初始资金"><InputNumber min={1} style={{ width: "100%" }} /></Form.Item>
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
          <FormActions><Button onClick={runPreview}>预览展开</Button><Button type="primary" htmlType="submit" icon={<PlayCircleOutlined />} loading={busy}>确认并排队</Button></FormActions>
        </Form>
      </Card>
      <Card title="批次历史" style={{ marginTop: 16 }} extra={<Button icon={<ReloadOutlined />} onClick={reload}>刷新</Button>}>
        <Table<ExperimentBatch> rowKey="id" size="small" dataSource={batches} columns={[
          { title: "名称", dataIndex: "name" },
          { title: "模式", dataIndex: "mode", render: (value) => <Tag>{value}</Tag> },
          { title: "状态", dataIndex: "status", render: (value) => <Tag color={value === "success" ? "success" : value === "failed" ? "error" : value === "partial" ? "warning" : "processing"}>{value}</Tag> },
          { title: "进度", render: (_, row) => <Progress size="small" percent={row.total ? Math.round(completed(row) * 100 / row.total) : 0} /> },
          { title: "成功/失败", render: (_, row) => `${row.succeeded}/${row.failed}` },
          { title: "操作", render: (_, row) => <Space wrap>
            <Button size="small" onClick={() => open(row)}>详情</Button>
            <Popconfirm title="删除这个批次记录？" description="仅删除批次清单和批次快照；批次已经产生的回测/优化结果仍在各自页面管理。" okText="删除" okButtonProps={{ danger: true }} disabled={["queued", "running"].includes(row.status)} onConfirm={async () => { try { await api.deleteExperimentBatch(row.id); if (selected?.id === row.id) setSelected(undefined); message.success("批次记录已删除"); await reload(); } catch (error) { message.error((error as Error).message); } }}>
              <Button size="small" danger icon={<DeleteOutlined />} disabled={["queued", "running"].includes(row.status)} />
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
    </>
  );
}
