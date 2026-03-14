import { memo, useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  LineType,
} from "lightweight-charts";
import type { EquityHistoryResponse } from "../types";
import { fetchEquityHistory } from "../api";

type AccountView = 0 | 1 | 2 | 3 | 4;

const SERIES_CONFIG = [
  { key: "combined", label: "Combined", color: "#7c4dff" },
  { key: "acct_1", label: "FIRE 0.1", color: "#00d4aa" },
  { key: "acct_2", label: "FIRE 0.2", color: "#4d8eff" },
  { key: "acct_3", label: "FIRE 0.3", color: "#ffc04d" },
  { key: "acct_4", label: "FIRE 0.4", color: "#ff6b9d" },
] as const;

const ACCT_SERIES = SERIES_CONFIG.filter((c) => c.key !== "combined");

const ACCT_COLOR: Record<number, string> = {
  1: "#00d4aa",
  2: "#4d8eff",
  3: "#ffc04d",
  4: "#ff6b9d",
};

const CHART_OPTS = {
  layout: {
    background: { color: "#1a1a2e" },
    textColor: "#8888a0",
    fontFamily: "Inter, sans-serif",
  },
  grid: {
    vertLines: { color: "#2a2a3e" },
    horzLines: { color: "#2a2a3e" },
  },
  timeScale: { borderColor: "#2a2a3e" },
  rightPriceScale: { borderColor: "#2a2a3e" },
  crosshair: {
    horzLine: { color: "#4d8eff44" },
    vertLine: { color: "#4d8eff44" },
  },
} as const;

const priceFormatter = (price: number) =>
  "$" + price.toLocaleString(undefined, { maximumFractionDigits: 0 });

interface Props {
  account: AccountView;
}

export default memo(function EquityHistoryChart({ account }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const breakdownRef = useRef<HTMLDivElement>(null);
  const breakdownChartRef = useRef<IChartApi | null>(null);
  const breakdownSeriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(
    new Map(),
  );
  const perAccountData = useRef<Record<string, unknown[]> | null>(null);
  const [days, setDays] = useState(0);
  const [loading, setLoading] = useState(true);

  // Create main chart and pre-create all series once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      ...CHART_OPTS,
      width: containerRef.current.clientWidth,
      height: 300,
    });

    chartRef.current = chart;

    // Pre-create combined view series (5 lines), initially hidden
    for (const cfg of SERIES_CONFIG) {
      const series = chart.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: cfg.key === "combined" ? 2 : 1,
        lineType: LineType.Curved,
        priceFormat: { type: "custom", formatter: priceFormatter },
        visible: false,
      });
      seriesRefs.current.set(cfg.key, series);
    }

    // Pre-create individual account series (1 line), initially hidden
    const mainSeries = chart.addSeries(LineSeries, {
      color: "#00d4aa",
      lineWidth: 2,
      lineType: LineType.Curved,
      priceFormat: { type: "custom", formatter: priceFormatter },
      visible: false,
    });
    seriesRefs.current.set("main", mainSeries);

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
      if (breakdownRef.current && breakdownChartRef.current) {
        breakdownChartRef.current.applyOptions({
          width: breakdownRef.current.clientWidth,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      seriesRefs.current.clear();
      breakdownChartRef.current?.remove();
      breakdownSeriesRefs.current.clear();
    };
  }, []);

  /** Lazily create the breakdown chart on first use */
  function ensureBreakdownChart() {
    if (breakdownChartRef.current) return breakdownChartRef.current;
    if (!breakdownRef.current) return null;

    const bc = createChart(breakdownRef.current, {
      ...CHART_OPTS,
      width: breakdownRef.current.clientWidth,
      height: 250,
    });
    breakdownChartRef.current = bc;

    for (const cfg of ACCT_SERIES) {
      const s = bc.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 2,
        lineType: LineType.Curved,
        priceFormat: { type: "custom", formatter: priceFormatter },
        visible: false,
      });
      breakdownSeriesRefs.current.set(cfg.key, s);
    }

    return bc;
  }

  // Fetch data and update series visibility when account changes
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || seriesRefs.current.size === 0) return;

    setLoading(true);

    fetchEquityHistory(account)
      .then((raw) => {
        const resp = raw as EquityHistoryResponse;
        if (!chartRef.current) return;

        if (account === 0 && resp.per_account) {
          // Hide main series and clear its data
          const mainSeries = seriesRefs.current.get("main");
          if (mainSeries) {
            mainSeries.setData([]);
            mainSeries.applyOptions({ visible: false });
          }
          // Show only the combined line; hide + clear individual account lines
          for (const cfg of SERIES_CONFIG) {
            const series = seriesRefs.current.get(cfg.key);
            if (!series) continue;
            if (cfg.key === "combined") {
              series.setData(resp.equity_curve ?? []);
              series.applyOptions({ visible: true });
            } else {
              series.setData([]);
              series.applyOptions({ visible: false });
            }
          }

          // Store per-account data for the breakdown chart effect
          perAccountData.current = resp.per_account;
        } else {
          // Hide combined series and clear their data
          for (const cfg of SERIES_CONFIG) {
            const series = seriesRefs.current.get(cfg.key);
            if (series) {
              series.setData([]);
              series.applyOptions({ visible: false });
            }
          }
          // Show main series with data
          const mainSeries = seriesRefs.current.get("main");
          if (mainSeries) {
            mainSeries.setData(resp.equity_curve ?? []);
            mainSeries.applyOptions({
              visible: true,
              color: ACCT_COLOR[account] ?? "#00d4aa",
            });
          }
          // Clear breakdown chart
          perAccountData.current = null;
          for (const cfg of ACCT_SERIES) {
            const s = breakdownSeriesRefs.current.get(cfg.key);
            if (s) {
              s.setData([]);
              s.applyOptions({ visible: false });
            }
          }
        }

        setDays(resp.days ?? 0);
        chart.priceScale("right").setAutoScale(true);
        chart.timeScale().fitContent();
      })
      .catch(() => setDays(0))
      .finally(() => setLoading(false));
  }, [account]);

  // Create/populate breakdown chart once container is visible (after DOM commit)
  const showBreakdown = account === 0 && days >= 2 && !loading;
  useEffect(() => {
    if (!showBreakdown || !perAccountData.current) return;
    const bc = ensureBreakdownChart();
    if (!bc) return;
    const data = perAccountData.current;
    for (const cfg of ACCT_SERIES) {
      const s = breakdownSeriesRefs.current.get(cfg.key);
      if (!s) continue;
      s.setData((data[cfg.key] as { time: string; value: number }[]) ?? []);
      s.applyOptions({ visible: true });
    }
    if (breakdownRef.current) {
      bc.applyOptions({ width: breakdownRef.current.clientWidth });
    }
    bc.priceScale("right").setAutoScale(true);
    bc.timeScale().fitContent();
  }, [showBreakdown]);

  // Legend items for current view
  const legend =
    account === 0
      ? [SERIES_CONFIG[0]]
      : [{ key: "main", label: `FIRE 0.${account}`, color: ACCT_COLOR[account] ?? "#00d4aa" }];

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

      <div
        className={
          showBreakdown
            ? "mt-4 border-t border-[#2a2a3e] pt-4"
            : "hidden"
        }
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
            Account Breakdown
          </h2>
          <div className="flex items-center gap-4 text-xs">
            {ACCT_SERIES.map((l) => (
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
        <div ref={breakdownRef} />
      </div>

      {days >= 2 && (
        <p className="mt-2 text-right text-xs text-[#5a5a70]">
          {days} trading days tracked
        </p>
      )}
    </div>
  );
})
