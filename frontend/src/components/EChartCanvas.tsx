import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import * as echarts from "echarts/core";
import type { ECharts, EChartsCoreOption as EChartsOption } from "echarts/core";
import { BarChart, GraphChart, HeatmapChart, LineChart, PieChart } from "echarts/charts";
import {
  AriaComponent, DataZoomComponent, GridComponent, LegendComponent,
  GraphicComponent, MarkPointComponent, TitleComponent, ToolboxComponent, TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  AriaComponent, BarChart, CanvasRenderer, DataZoomComponent, GraphChart,
  GraphicComponent, GridComponent, HeatmapChart, LegendComponent, LineChart, MarkPointComponent,
  PieChart, TitleComponent, ToolboxComponent, TooltipComponent, VisualMapComponent,
]);

export interface EChartCanvasHandle {
  exportPng: (filename: string) => void;
  resize: () => void;
}

interface EChartCanvasProps {
  option: EChartsOption;
  width?: number;
  height?: number;
  fit?: boolean;
  className?: string;
}

export const EChartCanvas = forwardRef<EChartCanvasHandle, EChartCanvasProps>(
  function EChartCanvas({ option, width = 960, height = 520, fit = false, className = "" }, ref) {
    const elementRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<ECharts | null>(null);

    useEffect(() => {
      if (!elementRef.current) return;
      const chart = echarts.init(elementRef.current, undefined, {
        renderer: "canvas",
        devicePixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      });
      chartRef.current = chart;
      chart.setOption(option, { notMerge: true });

      const observer = new ResizeObserver(() => chart.resize());
      observer.observe(elementRef.current);
      return () => {
        observer.disconnect();
        chart.dispose();
        chartRef.current = null;
      };
    }, []);

    useEffect(() => {
      chartRef.current?.setOption(option, { notMerge: true });
    }, [option]);

    useImperativeHandle(ref, () => ({
      exportPng(filename: string) {
        const chart = chartRef.current;
        if (!chart) return;
        const anchor = document.createElement("a");
        anchor.href = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
        anchor.download = filename.endsWith(".png") ? filename : `${filename}.png`;
        anchor.click();
      },
      resize() {
        chartRef.current?.resize();
      },
    }));

    return (
      <div className={`max-w-full overflow-x-auto overscroll-x-contain ${className}`}>
        <div
          ref={elementRef}
          role="img"
          aria-label="PatentAgent 数据可视化"
          style={{
            width: fit ? "100%" : `${width}px`,
            minWidth: fit ? 0 : `${width}px`,
            height: `${height}px`,
          }}
        />
      </div>
    );
  },
);
