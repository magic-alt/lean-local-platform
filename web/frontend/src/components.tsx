import { Button, Card, Empty, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import ReactECharts from "echarts-for-react";
import { useState } from "react";
import { BacktestRun, ChartData, OrderMarkerPoint, RunStatus } from "./api";
import { backtestAssetChartHeight, backtestAssetOption } from "./charts/backtestAsset";
import { formatInteger, formatNumber } from "./utils/display";

export function StatusTag({ status }: { status: string }) {
  const colors: Record<string, string> = {
    created: "default",
    queued: "default",
    checking: "processing",
    running: "processing",
    success: "success",
    succeeded: "success",
    available: "success",
    empty: "cyan",
    partial: "warning",
    retryable: "warning",
    skipped: "default",
    denied: "error",
    unknown: "default",
    failed: "error",
    interrupted: "warning",
    cancelled: "warning"
  };
  return <Tag data-testid={`status-tag-${status}`} color={colors[status] ?? "default"}>{status}</Tag>;
}

export function lineOption(title: string, datasets: Array<{ name: string; points: { time: string; value: number }[] }>) {
  return {
    animation: false,
    title: { text: title, left: 8, top: 4, textStyle: { color: "#172033", fontSize: 13, fontWeight: 700 } },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", label: { backgroundColor: "#102a43" } },
      valueFormatter: (value: unknown) => formatNumber(value),
    },
    legend: { top: 28, right: 18 },
    grid: { left: 70, right: 28, top: 68, bottom: 68 },
    toolbox: {
      right: 12,
      top: 2,
      feature: { dataZoom: {}, restore: {}, saveAsImage: { pixelRatio: 2 } },
    },
    xAxis: {
      type: "time",
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b" },
    },
    yAxis: {
      type: "value",
      scale: true,
      splitLine: { lineStyle: { color: "#e8eef4", type: "dashed" } },
      axisLabel: { color: "#64748b", formatter: (value: unknown) => formatNumber(value, 2) },
    },
    dataZoom: [
      { type: "inside", start: 0, end: 100 },
      { type: "slider", height: 20, bottom: 12, start: 0, end: 100 },
    ],
    series: datasets.map((dataset) => ({
      name: dataset.name,
      type: "line",
      showSymbol: false,
      smooth: false,
      lineStyle: { width: 2 },
      emphasis: { focus: "series" },
      data: dataset.points.map((point) => [point.time, point.value])
    }))
  };
}

function orderMarkerPoints(
  chartData: ChartData,
  valueKey: "equityValue" | "priceValue"
) {
  const markers = chartData.orderMarkers ?? chartData.order_markers ?? [];
  return markers
    .filter((marker): marker is OrderMarkerPoint => marker.side != null && marker.time != null && marker[valueKey] != null)
    .map((marker) => ({
      name: marker.side,
      coord: [marker.time, marker[valueKey] as number],
      value: `${marker.side} ${marker.quantity}`,
      symbol: "triangle",
      symbolSize: 13,
      symbolRotate: marker.side === "SELL" ? 180 : 0,
      itemStyle: { color: marker.side === "BUY" ? "#16a34a" : "#dc2626" },
      label: { show: false },
      tooltip: {
        formatter: [
          `${marker.side} ${marker.symbol}`,
          `Time: ${marker.time}`,
          `Quantity: ${formatInteger(marker.quantity)}`,
          `Fill: ${formatNumber(marker.fillPrice)}`,
          marker.tag ? `Tag: ${marker.tag}` : ""
        ].filter(Boolean).join("<br/>")
      }
    }));
}

function lineWithOrdersOption(
  title: string,
  datasets: Array<{ name: string; points: { time: string; value: number }[] }>,
  chartData: ChartData,
  valueKey: "equityValue" | "priceValue"
) {
  const option: any = lineOption(title, datasets);
  const markers = orderMarkerPoints(chartData, valueKey);
  if (markers.length > 0 && option.series.length > 0) {
    option.series[0].markPoint = { data: markers };
  }
  return option;
}

export function RunsTable({
  runs,
  onOpen,
  onDelete,
}: {
  runs: BacktestRun[];
  onOpen: (id: string) => void;
  onDelete?: (run: BacktestRun) => Promise<void>;
}) {
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [deleting, setDeleting] = useState(false);
  const trusted = (run: BacktestRun) =>
    ["success", "succeeded"].includes(run.status) && run.validation?.passed !== false;
  const canDelete = (run: BacktestRun) => !["created", "queued", "checking", "running"].includes(run.status);
  async function deleteSelected() {
    if (!onDelete) return;
    const targets = runs.filter((run) => selected.includes(run.id) && canDelete(run));
    setDeleting(true);
    try {
      for (const run of targets) await onDelete(run);
      setSelected([]);
      message.success(`${targets.length} backtest${targets.length === 1 ? "" : "s"} deleted`);
    } catch (error) {
      message.error((error as Error).message);
    } finally {
      setDeleting(false);
    }
  }
  return (
    <div className="resource-table">
      {onDelete && selected.length > 0 && (
        <div className="table-selection-bar">
          <span>{selected.length} selected</span>
          <Popconfirm
            title={`Delete ${selected.length} selected backtests?`}
            description="Only completed or cancelled backtests can be deleted. Results, reports and managed artifacts are removed together."
            okText="Delete selected"
            okButtonProps={{ danger: true }}
            onConfirm={deleteSelected}
          >
            <Button danger size="small" loading={deleting}>Delete selected</Button>
          </Popconfirm>
        </div>
      )}
      <Table
        data-testid="runs-table"
        rowKey="id"
        dataSource={runs}
        size="small"
        tableLayout="fixed"
        rowSelection={onDelete ? {
          selectedRowKeys: selected,
          onChange: setSelected,
          getCheckboxProps: (run) => ({ disabled: !canDelete(run) }),
        } : undefined}
        pagination={{ pageSize: 8, showSizeChanger: true, pageSizeOptions: [8, 20, 50] }}
        locale={{ emptyText: <Empty description="No backtests found" /> }}
        columns={[
          {
            title: "Backtest",
            width: "24%",
            render: (_, run) => <div className="table-primary-cell">
              <Typography.Text strong>{run.name || run.symbol || "Unnamed backtest"}</Typography.Text>
              <Typography.Text type="secondary" copyable={{ text: run.id }}>{run.id}</Typography.Text>
              <span>{run.symbol}</span>
            </div>
          },
          {
            title: "Market",
            width: "12%",
            render: (_, run) => <div className="table-primary-cell">
              <span>{run.asset_class ?? run.parameters.assetClass ?? "equity"}</span>
              <Typography.Text type="secondary">{run.venue ?? run.parameters.venue ?? run.parameters.market ?? "-"}</Typography.Text>
            </div>
          },
          {
            title: "Status",
            width: "14%",
            render: (_, run) => <div className="table-primary-cell">
              <StatusTag status={run.status as RunStatus} />
              {run.failure && <Typography.Text type="danger">{run.failure.stage}: {run.failure.code}</Typography.Text>}
            </div>
          },
          {
            title: "Period",
            width: "15%",
            render: (_, run) => <div className="table-primary-cell"><span>{run.parameters.start}</span><Typography.Text type="secondary">to {run.parameters.end}</Typography.Text></div>
          },
          {
            title: "Result",
            width: "15%",
            render: (_, run) => trusted(run)
              ? <div className="table-primary-cell"><span>Return {run.statistics?.["Net Profit"] ?? "-"}</span><Typography.Text type="secondary">Sharpe {run.statistics?.["Sharpe Ratio"] ?? "-"}</Typography.Text></div>
              : <Typography.Text type="secondary">Metrics unavailable</Typography.Text>
          },
          { title: "Duration", width: "9%", render: (_, run) => run.duration_seconds == null ? "-" : `${run.duration_seconds}s` },
          {
            title: "Actions",
            width: onDelete ? "16%" : "10%",
            render: (_, run) => <Space wrap>
              <Button type="link" size="small" data-testid={`open-run-${run.id}`} onClick={() => onOpen(run.id)}>Open</Button>
              {onDelete && <Popconfirm
                title="Delete this backtest?"
                description="Its result, generated reports and managed artifacts will also be deleted."
                okText="Delete"
                okButtonProps={{ danger: true }}
                disabled={!canDelete(run)}
                onConfirm={async () => {
                  try {
                    await onDelete(run);
                    message.success("Backtest deleted");
                  } catch (error) {
                    message.error((error as Error).message);
                  }
                }}
              >
                <Button danger size="small" disabled={!canDelete(run)}>Delete</Button>
              </Popconfirm>}
            </Space>
          }
        ]}
      />
    </div>
  );
}

export function BacktestCharts({ chartData }: { chartData: ChartData }) {
  return (
    <>
      <Card title="Equity vs Benchmark" style={{ marginTop: 16 }}>
        <div data-testid="equity-chart" data-point-count={chartData.series.equity.length}>
          <ReactECharts
            style={{ height: 380 }}
            option={lineWithOrdersOption(
              "Equity",
              [
                { name: "Equity", points: chartData.series.equity },
                { name: "Benchmark", points: chartData.series.benchmark }
              ],
              chartData,
              "equityValue"
            )}
          />
        </div>
      </Card>
      {((chartData.candles?.length ?? 0) > 0 || chartData.series.price.length > 0) && (
        <Card title="Asset Price, Orders & Indicators" style={{ marginTop: 16 }}>
          <div data-testid="price-chart" data-point-count={chartData.candles?.length ?? chartData.series.price.length}>
            <ReactECharts
              style={{ height: backtestAssetChartHeight(chartData) }}
              option={backtestAssetOption(chartData)}
            />
          </div>
        </Card>
      )}
      <Card title="Orders" style={{ marginTop: 16 }}>
        <Table
          data-testid="orders-table"
          rowKey={(row) => `${row.time}-${row.side}-${row.quantity}`}
          dataSource={chartData.orders}
          size="small"
          scroll={{ x: 720 }}
          pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: (total) => `${total} orders` }}
          columns={[
            { title: "Time", dataIndex: "time" },
            { title: "Side", dataIndex: "side" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "Quantity", dataIndex: "quantity", align: "right", render: (value) => <span className="numeric-cell">{formatInteger(value)}</span> },
            { title: "Price", dataIndex: "price", align: "right", render: (value) => <span className="numeric-cell">{formatNumber(value)}</span> },
            { title: "Tag", dataIndex: "tag", ellipsis: true }
          ]}
        />
      </Card>
    </>
  );
}
