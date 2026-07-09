import { Alert, Button, Card, Form, Select, Space, Table, Tabs, Tag, message } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import ReactECharts from "echarts-for-react";
import { useCallback, useMemo, useState } from "react";

import { api } from "../api";
import type { BacktestCompareResult, BacktestRun } from "../api";
import { StatusTag } from "../components";
import { useAsyncData } from "../hooks";


function formatNumber(value: unknown, percent = false) {
  const number = typeof value === "number" ? value : Number(value);
  if (value == null || value === "" || !Number.isFinite(number)) return "-";
  return percent ? `${(number * 100).toFixed(2)}%` : number.toFixed(3);
}

function isTrue(value: unknown) {
  return value === true || String(value).toLowerCase() === "true";
}


function compareChart(result?: BacktestCompareResult, key: "equityCurve" | "drawdownCurve" = "equityCurve") {
  const items = result?.items ?? [];
  return {
    animation: false,
    tooltip: { trigger: "axis" },
    legend: { top: 8 },
    grid: { top: 48, left: 64, right: 24, bottom: 36 },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true },
    series: items.map((item) => ({
      name: `${item.symbol || ""} ${item.runId.slice(0, 8)}`,
      type: "line",
      showSymbol: false,
      data: (item[key] ?? []).map((point) => [point.time, point.value])
    }))
  };
}


export function CompareRunsPanel() {
  const loadRuns = useCallback(() => api.backtests({ status: "success" }), []);
  const runs = useAsyncData(loadRuns, []);
  const [result, setResult] = useState<BacktestCompareResult>();
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();
  const selected = Form.useWatch("runIds", form) || [];
  const runOptions = useMemo(
    () => runs.data.map((run: BacktestRun) => ({
      value: run.id,
      label: `${run.symbol} ${String(run.parameters?.start ?? "")} -> ${String(run.parameters?.end ?? "")} ${run.id.slice(0, 8)}`
    })),
    [runs.data]
  );

  async function submit(values: { runIds: string[] }) {
    setLoading(true);
    try {
      setResult(await api.compareBacktests({ runIds: values.runIds, includeCurves: true }));
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Card title="Compare Runs" extra={<Button icon={<ReloadOutlined />} onClick={runs.reload}>Refresh Runs</Button>}>
        <Form form={form} layout="vertical" onFinish={submit}>
          <Form.Item name="runIds" label="Backtest Runs" rules={[{ required: true }]}>
            <Select mode="multiple" options={runOptions} loading={runs.loading} placeholder="Select 2-20 successful runs" />
          </Form.Item>
          <Button type="primary" htmlType="submit" disabled={selected.length < 2} loading={loading}>Compare</Button>
        </Form>
      </Card>
      {result && (
        <>
          <Card title="Metrics" style={{ marginTop: 16 }}>
            <Table
              rowKey="runId"
              dataSource={result.items}
              size="small"
              columns={[
                { title: "Run", dataIndex: "runId", ellipsis: true },
                { title: "Symbol", dataIndex: "symbol" },
                { title: "Status", dataIndex: "status", render: (status) => <StatusTag status={status} /> },
                { title: "Validation", render: (_, item) => <Tag color={item.validation?.passed === false ? "red" : "green"}>{item.validation?.severity || "unknown"}</Tag> },
                { title: "Total Return", render: (_, item) => formatNumber(item.metrics.totalReturn, true) },
                { title: "Annual", render: (_, item) => formatNumber(item.metrics.annualReturn, true) },
                { title: "Drawdown", render: (_, item) => formatNumber(item.metrics.maxDrawdown, true) },
                {
                  title: "Sharpe",
                  render: (_, item) => (
                    <Space size={4}>
                      <span>{formatNumber(item.metrics.sharpeRatio)}</span>
                      {isTrue(item.metrics.shortWindowUnstable) && <Tag color="orange">short</Tag>}
                    </Space>
                  )
                },
                { title: "LEAN Sharpe", render: (_, item) => formatNumber(item.metrics.leanSharpeRatio) },
                { title: "Calmar", render: (_, item) => formatNumber(item.metrics.calmarRatio) },
                { title: "Orders", render: (_, item) => formatNumber(item.metrics.totalOrders) }
              ]}
            />
          </Card>
          {result.items.some((item) => item.error) && <Alert style={{ marginTop: 16 }} type="warning" showIcon message="Some selected runs are missing parsed results." />}
          <Card title="Curves" style={{ marginTop: 16 }}>
            <Tabs
              items={[
                { key: "equity", label: "Equity", children: <ReactECharts option={compareChart(result, "equityCurve")} style={{ height: 360 }} /> },
                { key: "drawdown", label: "Drawdown", children: <ReactECharts option={compareChart(result, "drawdownCurve")} style={{ height: 360 }} /> },
                { key: "ranking", label: "Rankings", children: <Space direction="vertical">{Object.entries(result.rankings).map(([key, values]) => <div key={key}><strong>{key}</strong>: {values.join(", ")}</div>)}</Space> }
              ]}
            />
          </Card>
        </>
      )}
    </>
  );
}
