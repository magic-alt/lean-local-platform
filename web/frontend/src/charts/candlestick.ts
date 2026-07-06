import type { DataQueryRow } from "../api";

export function candlestickOption(rows: DataQueryRow[], symbol: string) {
  const dates = rows.map((row) => row.timestamp.slice(0, 10));
  const upColor = "#cf1322";
  const downColor = "#389e0d";
  return {
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
    legend: { top: 8, data: [symbol, "Volume"] },
    grid: [
      { left: 54, right: 24, top: 48, height: 320 },
      { left: 54, right: 24, top: 400, height: 96 }
    ],
    xAxis: [
      { type: "category", data: dates, boundaryGap: true, axisLine: { onZero: false }, min: "dataMin", max: "dataMax" },
      { type: "category", gridIndex: 1, data: dates, boundaryGap: true, axisLabel: { show: false }, axisTick: { show: false }, min: "dataMin", max: "dataMax" }
    ],
    yAxis: [
      { scale: true, splitArea: { show: true } },
      { scale: true, gridIndex: 1, splitNumber: 2, axisLabel: { formatter: "{value}" } }
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], bottom: 8, start: 0, end: 100 }
    ],
    series: [
      {
        name: symbol,
        type: "candlestick",
        data: rows.map((row) => [row.open, row.close, row.low, row.high]),
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor
        }
      },
      {
        name: "Volume",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: rows.map((row) => ({
          value: row.volume,
          itemStyle: { color: row.close >= row.open ? upColor : downColor }
        }))
      }
    ]
  };
}
