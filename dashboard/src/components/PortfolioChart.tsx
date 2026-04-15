import { useEffect, useRef } from "react";
import { createChart, LineSeries, type IChartApi, type ISeriesApi, LineType } from "lightweight-charts";
import type { EquityPoint } from "../types";

interface Props {
  data: EquityPoint[];
  spyData?: EquityPoint[];
  title?: string;
}

export default function PortfolioChart({ data, spyData, title = "Equity Curve" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const spySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#1a1a2e" },
        textColor: "#8888a0",
        fontFamily: "Inter, sans-serif",
      },
      grid: {
        vertLines: { color: "#2a2a3e" },
        horzLines: { color: "#2a2a3e" },
      },
      width: containerRef.current.clientWidth,
      height: 400,
      timeScale: {
        borderColor: "#2a2a3e",
      },
      rightPriceScale: {
        borderColor: "#2a2a3e",
      },
      crosshair: {
        horzLine: { color: "#4d8eff44" },
        vertLine: { color: "#4d8eff44" },
      },
      handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: true },
    });

    // Strategy equity line (green)
    const series = chart.addSeries(LineSeries, {
      color: "#00d4aa",
      lineWidth: 2,
      lineType: LineType.Curved,
      priceFormat: {
        type: "custom",
        formatter: (price: number) => "$" + price.toLocaleString(),
      },
    });

    // SPY benchmark line (red, thinner)
    const spySeries = chart.addSeries(LineSeries, {
      color: "#ff4d6a",
      lineWidth: 1,
      lineType: LineType.Curved,
      priceFormat: {
        type: "custom",
        formatter: (price: number) => "$" + price.toLocaleString(),
      },
    });

    chartRef.current = chart;
    seriesRef.current = series;
    spySeriesRef.current = spySeries;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      seriesRef.current.setData(data);
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);

  useEffect(() => {
    if (spySeriesRef.current) {
      if (spyData && spyData.length > 0) {
        spySeriesRef.current.setData(spyData);
      } else {
        spySeriesRef.current.setData([]);
      }
    }
  }, [spyData]);

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          {title}
        </h2>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded bg-[#00d4aa]" />
            <span className="text-[#8888a0]">Strategy</span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded bg-[#ff4d6a]" />
            <span className="text-[#8888a0]">SPY</span>
          </span>
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
