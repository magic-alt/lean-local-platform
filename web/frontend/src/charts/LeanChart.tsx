import ReactEChartsCore from "echarts-for-react/lib/core";
import type { EChartsReactProps } from "echarts-for-react/lib/types";
import * as echarts from "echarts/core";
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  VisualMapComponent
} from "echarts/components";
import { BarChart, CandlestickChart, HeatmapChart, LineChart } from "echarts/charts";
import { LabelLayout, UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  CandlestickChart,
  DataZoomComponent,
  GridComponent,
  HeatmapChart,
  LabelLayout,
  LegendComponent,
  LineChart,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  UniversalTransition,
  VisualMapComponent
]);

export function LeanChart({ option, opts, ...props }: EChartsReactProps) {
  const accessibleOption = {
    aria: { enabled: true },
    ...option
  };
  return (
    <ReactEChartsCore
      {...props}
      echarts={echarts}
      option={accessibleOption}
      opts={{ renderer: "canvas", ...opts }}
    />
  );
}
