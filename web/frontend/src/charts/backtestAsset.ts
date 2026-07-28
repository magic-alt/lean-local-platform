import type { ChartData, ChartPoint, OrderMarkerPoint } from "../api";
import { formatInteger, formatNumber } from "../utils/display";

const upColor = "#cf1322";
const downColor = "#389e0d";
const overlayChartPattern = /(EMA|SMA|Bollinger|Donchian|Moving Average|Price)/i;

function day(value: string) {
  return value.slice(0, 10);
}

function fallbackCandles(points: ChartPoint[]) {
  return points.map((point) => ({
    time: point.time,
    open: point.value,
    high: point.value,
    low: point.value,
    close: point.value,
    volume: 0,
  }));
}

function orderMarkPoints(markers: OrderMarkerPoint[]) {
  return markers
    .filter((marker) => marker.time && (marker.fillPrice ?? marker.priceValue ?? marker.price) != null)
    .map((marker) => {
      const fillPrice = marker.fillPrice ?? marker.fill_price ?? marker.priceValue ?? marker.price;
      return {
        name: marker.side,
        coord: [day(marker.time), fillPrice],
        value: `${marker.side} ${formatInteger(Math.abs(marker.quantity))}`,
        symbol: "triangle",
        symbolSize: 15,
        symbolRotate: marker.side === "SELL" ? 180 : 0,
        itemStyle: { color: marker.side === "BUY" ? "#1677ff" : "#722ed1" },
        label: { show: false },
        tooltip: {
          formatter: [
            `${marker.side} ${marker.symbolDisplay || [marker.symbol, marker.securityName].filter(Boolean).join(" ")}`,
            `Date: ${day(marker.time)}`,
            `Quantity: ${formatInteger(Math.abs(marker.quantity))}`,
            `Fill: ${formatNumber(fillPrice)}`,
            marker.tag ? `Tag: ${marker.tag}` : "",
          ].filter(Boolean).join("<br/>"),
        },
      };
    });
}

export function backtestAssetChartHeight(chartData: ChartData) {
  const panels = new Set(
    (chartData.indicators ?? [])
      .filter((indicator) => !overlayChartPattern.test(indicator.chart))
      .map((indicator) => indicator.chart),
  );
  return 500 + panels.size * 130;
}

export function backtestAssetOption(chartData: ChartData) {
  const candles = chartData.candles?.length
    ? chartData.candles
    : fallbackCandles(chartData.series.price ?? []);
  const dates = candles.map((point) => day(point.time));
  const candleDates = new Set(dates);
  const indicators = chartData.indicators ?? [];
  const overlays = indicators.filter((indicator) => overlayChartPattern.test(indicator.chart));
  const panelNames = Array.from(new Set(
    indicators
      .filter((indicator) => !overlayChartPattern.test(indicator.chart))
      .map((indicator) => indicator.chart),
  ));
  const grids: any[] = [
    { left: 58, right: 24, top: 52, height: 300 },
    { left: 58, right: 24, top: 374, height: 82 },
  ];
  panelNames.forEach((_, index) => {
    grids.push({ left: 58, right: 24, top: 486 + index * 130, height: 94 });
  });
  const axisCount = grids.length;
  const xAxes = grids.map((_, index) => ({
    type: "category",
    gridIndex: index,
    data: dates,
    boundaryGap: true,
    axisLine: { onZero: false },
    axisLabel: { show: index === axisCount - 1 },
    axisTick: { show: index === axisCount - 1 },
    min: "dataMin",
    max: "dataMax",
  }));
  const yAxes: any[] = [
    { scale: true, splitArea: { show: true }, name: "Price", axisLabel: { formatter: (value: unknown) => formatNumber(value, 2) } },
    { scale: true, gridIndex: 1, splitNumber: 2, name: "Volume", axisLabel: { formatter: (value: unknown) => formatNumber(value, 0) } },
  ];
  panelNames.forEach((name, index) => {
    yAxes.push({
      scale: true,
      gridIndex: index + 2,
      name,
      min: /^RSI$/i.test(name) ? 0 : undefined,
      max: /^RSI$/i.test(name) ? 100 : undefined,
      axisLabel: { formatter: (value: unknown) => formatNumber(value, 2) },
    });
  });
  const series: any[] = [
    {
      name: "Price",
      type: "candlestick",
      data: candles.map((point) => [point.open, point.close, point.low, point.high]),
      itemStyle: {
        color: upColor,
        color0: downColor,
        borderColor: upColor,
        borderColor0: downColor,
      },
      markPoint: { data: orderMarkPoints(chartData.orderMarkers ?? chartData.order_markers ?? []) },
    },
    {
      name: "Volume",
      type: "bar",
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: candles.map((point) => ({
        value: point.volume,
        itemStyle: { color: point.close >= point.open ? upColor : downColor },
      })),
    },
  ];
  overlays.forEach((indicator) => {
    series.push({
      name: `${indicator.chart} ${indicator.name}`,
      type: "line",
      showSymbol: false,
      smooth: false,
      data: indicator.points
        .filter((point) => candleDates.has(day(point.time)))
        .map((point) => [day(point.time), point.value]),
    });
  });
  panelNames.forEach((chart, panelIndex) => {
    indicators.filter((indicator) => indicator.chart === chart).forEach((indicator) => {
      series.push({
        name: `${indicator.chart} ${indicator.name}`,
        type: "line",
        xAxisIndex: panelIndex + 2,
        yAxisIndex: panelIndex + 2,
        showSymbol: false,
        smooth: false,
        data: indicator.points
          .filter((point) => candleDates.has(day(point.time)))
          .map((point) => [day(point.time), point.value]),
      });
    });
  });
  const allAxisIndexes = grids.map((_, index) => index);
  return {
    animation: false,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      valueFormatter: (value: unknown) => Array.isArray(value)
        ? value.map((item) => formatNumber(item)).join(" / ")
        : formatNumber(value),
    },
    axisPointer: { link: [{ xAxisIndex: allAxisIndexes }] },
    legend: { type: "scroll", top: 8, left: 58, right: 24 },
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    dataZoom: [
      { type: "inside", xAxisIndex: allAxisIndexes, start: 0, end: 100 },
      { type: "slider", xAxisIndex: allAxisIndexes, bottom: 8, start: 0, end: 100 },
    ],
    series,
  };
}
