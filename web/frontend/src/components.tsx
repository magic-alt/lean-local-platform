import { Card, Empty, Table, Tag } from "antd";
import ReactECharts from "echarts-for-react";
import { BacktestRun, ChartData, OrderMarkerPoint, RunStatus } from "./api";

export function StatusTag({ status }: { status: string }) {
  const colors: Record<string, string> = {
    created: "default",
    queued: "default",
    running: "processing",
    success: "success",
    succeeded: "success",
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
        { title: "Period", render: (_, run) => `${run.parameters.start} -> ${run.parameters.end}` },
        { title: "Net Profit", render: (_, run) => run.statistics?.["Net Profit"] ?? "-" },
        { title: "Sharpe", render: (_, run) => run.statistics?.["Sharpe Ratio"] ?? "-" },
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
      {chartData.series.price.length > 0 && (
        <Card title="Asset Plot" style={{ marginTop: 16 }}>
          <div data-testid="price-chart" data-point-count={chartData.series.price.length}>
            <ReactECharts
              style={{ height: 360 }}
              option={lineWithOrdersOption(
                "Price With Orders",
                [{ name: "Close", points: chartData.series.price }],
                chartData,
                "priceValue"
              )}
            />
          </div>
        </Card>
      )}
      <div className="two-column">
        {(chartData.series.emaFast.length > 0 || chartData.series.emaSlow.length > 0) && (
          <Card title="EMA">
            <ReactECharts
              style={{ height: 320 }}
              option={lineOption("EMA", [
                { name: "Fast", points: chartData.series.emaFast },
                { name: "Slow", points: chartData.series.emaSlow }
              ])}
            />
          </Card>
        )}
        <Card title="Drawdown">
          <div data-testid="drawdown-chart" data-point-count={chartData.series.drawdown.length}>
            <ReactECharts
              style={{ height: 320 }}
              option={lineOption("Drawdown", [{ name: "Drawdown", points: chartData.series.drawdown }])}
            />
          </div>
        </Card>
      </div>
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
