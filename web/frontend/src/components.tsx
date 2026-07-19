import { Card, Empty, Table, Tag } from "antd";
import ReactECharts from "echarts-for-react";
import { BacktestRun, ChartData, OrderMarkerPoint, RunStatus } from "./api";
import { backtestAssetChartHeight, backtestAssetOption } from "./charts/backtestAsset";

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
    title: { text: title, left: 8, top: 4, textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis" },
    legend: { top: 28 },
    grid: { left: 54, right: 22, top: 68, bottom: 36 },
    xAxis: { type: "time" },
    yAxis: { type: "value", scale: true },
    series: datasets.map((dataset) => ({
      name: dataset.name,
      type: "line",
      showSymbol: false,
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
          `Quantity: ${marker.quantity}`,
          `Fill: ${marker.fillPrice}`,
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

export function RunsTable({ runs, onOpen }: { runs: BacktestRun[]; onOpen: (id: string) => void }) {
  const trusted = (run: BacktestRun) =>
    ["success", "succeeded"].includes(run.status) && run.validation?.passed !== false;
  return (
    <Table
      data-testid="runs-table"
      rowKey="id"
      dataSource={runs}
      size="small"
      pagination={{ pageSize: 8 }}
      locale={{ emptyText: <Empty description="No backtests found" /> }}
      columns={[
        { title: "Name", dataIndex: "name", ellipsis: true },
        { title: "Run", dataIndex: "id", ellipsis: true },
        { title: "Symbol", dataIndex: "symbol" },
        { title: "Asset", render: (_, run) => run.asset_class ?? run.parameters.assetClass ?? "equity" },
        { title: "Venue", render: (_, run) => run.venue ?? run.parameters.venue ?? run.parameters.market ?? "-" },
        { title: "Status", dataIndex: "status", render: (status: RunStatus) => <StatusTag status={status} /> },
        { title: "Failure", render: (_, run) => run.failure ? `${run.failure.stage}: ${run.failure.code}` : "-" },
        { title: "Period", render: (_, run) => `${run.parameters.start} -> ${run.parameters.end}` },
        { title: "Net Profit", render: (_, run) => trusted(run) ? run.statistics?.["Net Profit"] ?? "-" : "untrusted" },
        { title: "Sharpe", render: (_, run) => trusted(run) ? run.statistics?.["Sharpe Ratio"] ?? "-" : "untrusted" },
        { title: "Duration", render: (_, run) => run.duration_seconds == null ? "-" : `${run.duration_seconds}s` },
        { title: "Action", render: (_, run) => <a data-testid={`open-run-${run.id}`} onClick={() => onOpen(run.id)}>Open</a> }
      ]}
    />
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
          pagination={false}
          columns={[
            { title: "Time", dataIndex: "time" },
            { title: "Side", dataIndex: "side" },
            { title: "Symbol", dataIndex: "symbol" },
            { title: "Quantity", dataIndex: "quantity" },
            { title: "Price", dataIndex: "price" },
            { title: "Tag", dataIndex: "tag", ellipsis: true }
          ]}
        />
      </Card>
    </>
  );
}
