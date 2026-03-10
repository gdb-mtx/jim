import { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  LineType,
} from "lightweight-charts";
import type { EquityPoint } from "../types";
import { fetchEquityHistory } from "../api";

type AccountView = 0 | 1 | 2 | 3 | 4;

const SERIES_CONFIG = [
  { key: "combined", label: "Combined", color: "#7c4dff" },
  { key: "acct_1", label: "FIRE 0.1", color: "#00d4aa" },
  { key: "acct_2", label: "FIRE 0.2", color: "#4d8eff" },
  { key: "acct_3", label: "FIRE 0.3", color: "#ffc04d" },
  { key: "acct_4", label: "FIRE 0.4", color: "#ff6b9d" },
] as const;

interface Props {
  account: AccountView;
}

export default function EquityHistoryChart({ account }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const [days, setDays] = useState(0);
  const [loading, setLoading] = useState(true);

  // Create chart once
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
      height: 300,
      timeScale: { borderColor: "#2a2a3e" },
      rightPriceScale: { borderColor: "#2a2a3e" },
      crosshair: {
        horzLine: { color: "#4d8eff44" },
        vertLine: { color: "#4d8eff44" },
      },
    });

    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      seriesRefs.current.clear();
    };
  }, []);

  // Fetch data and update series when account changes
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove old series
    for (const [, series] of seriesRefs.current) {
      chart.removeSeries(series);
    }
    seriesRefs.current.clear();

    setLoading(true);

    fetchEquityHistory(account)
      .then((resp) => {
        if (!chartRef.current) return;

        const priceFormatter = (price: number) =>
          "$" + price.toLocaleString(undefined, { maximumFractionDigits: 0 });

        if (account === 0 && resp.per_account) {
          // Combined view: show all 4 lines
          for (const cfg of SERIES_CONFIG) {
            const data: EquityPoint[] = resp.per_account?.[cfg.key] ?? resp.equity_curve;
            if (cfg.key === "combined") {
              // Combined uses the top-level equity_curve
              const series = chart.addSeries(LineSeries, {
                color: cfg.color,
                lineWidth: 2,
                lineType: LineType.Curved,
                priceFormat: { type: "custom", formatter: priceFormatter },
              });
              series.setData(resp.equity_curve ?? []);
              seriesRefs.current.set(cfg.key, series);
            } else {
              const series = chart.addSeries(LineSeries, {
                color: cfg.color,
                lineWidth: 1,
                lineType: LineType.Curved,
                priceFormat: { type: "custom", formatter: priceFormatter },
              });
              series.setData(data);
              seriesRefs.current.set(cfg.key, series);
            }
          }
        } else {
          // Individual account: single green line
          const series = chart.addSeries(LineSeries, {
            color: "#00d4aa",
            lineWidth: 2,
            lineType: LineType.Curved,
            priceFormat: { type: "custom", formatter: priceFormatter },
          });
          series.setData(resp.equity_curve ?? []);
          seriesRefs.current.set("main", series);
        }

        setDays(resp.days ?? 0);
        chart.timeScale().fitContent();
      })
      .catch(() => setDays(0))
      .finally(() => setLoading(false));
  }, [account]);

  // Legend items for current view
  const legend =
    account === 0
      ? SERIES_CONFIG
      : [{ key: "main", label: `FIRE 0.${account}`, color: "#00d4aa" }];

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Live Equity
        </h2>
        <div className="flex items-center gap-4 text-xs">
          {legend.map((l) => (
            <span key={l.key} className="flex items-center gap-1.5">
              <span
                className="inline-block h-0.5 w-4 rounded"
                style={{ backgroundColor: l.color }}
              />
              <span className="text-[#8888a0]">{l.label}</span>
            </span>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex h-[300px] items-center justify-center text-sm text-[#5a5a70]">
          Loading equity data...
        </div>
      ) : days < 2 ? (
        <div className="flex h-[300px] items-center justify-center text-sm text-[#5a5a70]">
          Equity tracking started. Check back tomorrow for your first chart.
        </div>
      ) : null}

      <div ref={containerRef} className={days < 2 && !loading ? "hidden" : ""} />

      {days >= 2 && (
        <p className="mt-2 text-right text-xs text-[#5a5a70]">
          {days} trading days tracked
        </p>
      )}
    </div>
  );
}
