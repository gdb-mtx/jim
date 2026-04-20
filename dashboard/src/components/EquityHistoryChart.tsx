import { memo, useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  LineType,
} from "lightweight-charts";
import type { EquityHistoryResponse, PerformanceEntry, RebalanceHistoryEntry } from "../types";
import { fetchEquityHistory, fetchRebalanceHistory } from "../api";

type AccountView = 0 | 1 | 2 | 3 | 4;

// A3 retired 2026-04-20; its series is excluded so the live chart isn't polluted.
const SERIES_CONFIG = [
  { key: "combined", label: "Combined", color: "#7c4dff" },
  { key: "acct_1", label: "FIRE 0.1", color: "#00d4aa" },
  { key: "acct_2", label: "FIRE 0.2", color: "#4d8eff" },
  { key: "acct_4", label: "FIRE 0.4", color: "#ff6b9d" },
] as const;

const ACCT_SERIES = SERIES_CONFIG.filter((c) => c.key !== "combined");

const ACCT_COLOR: Record<number, string> = {
  1: "#00d4aa",
  2: "#4d8eff",
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
  handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
  handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: true },
} as const;

const priceFormatter = (price: number) =>
  "$" + price.toLocaleString(undefined, { maximumFractionDigits: 0 });

/** Convert rebalance history entries to TradingView chart markers.
 *
 * Filters out retired accounts (ACCT_COLOR is the active-account source of
 * truth) so weekly A3 rebalance markers don't appear on the live combined
 * curve after retirement. A3's final liquidation is also filtered. */
function toRebalanceMarkers(
  entries: RebalanceHistoryEntry[],
  accountView: AccountView,
): SeriesMarker<string>[] {
  // Group by date — multiple rebalances on same day become one marker
  const byDate = new Map<
    string,
    { totalOrders: number; hasFails: boolean; accounts: Set<number> }
  >();
  for (const e of entries) {
    if (!(e.account in ACCT_COLOR)) continue;
    const date = e.timestamp.slice(0, 10);
    const existing = byDate.get(date) ?? {
      totalOrders: 0,
      hasFails: false,
      accounts: new Set(),
    };
    existing.totalOrders += e.orders_submitted;
    if (e.orders_failed > 0) existing.hasFails = true;
    existing.accounts.add(e.account);
    byDate.set(date, existing);
  }

  const markers: SeriesMarker<string>[] = [];
  for (const [date, info] of byDate) {
    // Pick color: red for failures, account color for single account, purple for combined
    let color: string;
    if (info.hasFails) {
      color = "#ff6b6b";
    } else if (accountView > 0) {
      color = ACCT_COLOR[accountView] ?? "#00d4aa";
    } else if (info.accounts.size === 1) {
      const acct = [...info.accounts][0];
      color = ACCT_COLOR[acct] ?? "#7c4dff";
    } else {
      color = "#7c4dff";
    }

    markers.push({
      time: date,
      shape: "arrowUp",
      position: "belowBar",
      color,
      text: `R·${info.totalOrders}`,
      size: 1,
    });
  }

  // TradingView requires markers sorted by time
  markers.sort((a, b) => a.time.localeCompare(b.time));
  return markers;
}

interface Props {
  account: AccountView;
  refreshKey?: number;
}

export default memo(function EquityHistoryChart({ account, refreshKey }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const breakdownRef = useRef<HTMLDivElement>(null);
  const breakdownChartRef = useRef<IChartApi | null>(null);
  const breakdownSeriesRefs = useRef<Map<string, ISeriesApi<"Line">>>(
    new Map(),
  );
  const markerPluginRefs = useRef<Map<string, ISeriesMarkersPluginApi<string>>>(
    new Map(),
  );
  const perAccountData = useRef<Record<string, unknown[]> | null>(null);
  const [days, setDays] = useState(0);
  const [loading, setLoading] = useState(true);
  const [performance, setPerformance] = useState<PerformanceEntry[]>([]);

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
      if (cfg.key === "combined") {
        markerPluginRefs.current.set(
          "combined",
          createSeriesMarkers(series, []),
        );
      }
    }

    // Pre-create SPY benchmark series (red, thin), initially hidden
    const spySeries = chart.addSeries(LineSeries, {
      color: "#ff4444",
      lineWidth: 1,
      lineType: LineType.Curved,
      priceFormat: { type: "custom", formatter: priceFormatter },
      visible: false,
    });
    seriesRefs.current.set("spy", spySeries);

    // Pre-create individual account series (1 line), initially hidden
    const mainSeries = chart.addSeries(LineSeries, {
      color: "#00d4aa",
      lineWidth: 2,
      lineType: LineType.Curved,
      priceFormat: { type: "custom", formatter: priceFormatter },
      visible: false,
    });
    seriesRefs.current.set("main", mainSeries);
    markerPluginRefs.current.set("main", createSeriesMarkers(mainSeries, []));

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
      markerPluginRefs.current.forEach((p) => p.detach());
      markerPluginRefs.current.clear();
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

    Promise.all([
      fetchEquityHistory(account),
      fetchRebalanceHistory(200, account === 0 ? undefined : account),
    ])
      .then(([raw, rebalanceEntries]) => {
        const resp = raw as EquityHistoryResponse;
        const entries = rebalanceEntries as RebalanceHistoryEntry[];
        if (!chartRef.current) return;

        if (account === 0 && resp.per_account) {
          // Hide main series and clear its data
          const mainSeries = seriesRefs.current.get("main");
          if (mainSeries) {
            mainSeries.setData([]);
            mainSeries.applyOptions({ visible: false });
          }
          markerPluginRefs.current.get("main")?.setMarkers([]);
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

          // Show SPY benchmark if available
          const spySeries = seriesRefs.current.get("spy");
          if (spySeries) {
            if (resp.spy_benchmark?.length) {
              spySeries.setData(resp.spy_benchmark);
              spySeries.applyOptions({ visible: true });
            } else {
              spySeries.setData([]);
              spySeries.applyOptions({ visible: false });
            }
          }

          // Set rebalance markers on combined series
          markerPluginRefs.current
            .get("combined")
            ?.setMarkers(toRebalanceMarkers(entries, 0));

          // Store performance summary + per-account data
          setPerformance(resp.performance ?? []);
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
          markerPluginRefs.current.get("combined")?.setMarkers([]);
          // Hide SPY benchmark
          const spySeries = seriesRefs.current.get("spy");
          if (spySeries) {
            spySeries.setData([]);
            spySeries.applyOptions({ visible: false });
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

          // Set rebalance markers on main series
          markerPluginRefs.current
            .get("main")
            ?.setMarkers(toRebalanceMarkers(entries, account));

          // Clear breakdown chart + performance
          setPerformance([]);
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
  }, [account, refreshKey]);

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
      ? [SERIES_CONFIG[0], { key: "spy", label: "SPY", color: "#ff4444" }]
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
        <div className="flex h-[300px] items-center justify-center text-sm text-[#8a8aa5]">
          Loading equity data...
        </div>
      ) : days < 2 ? (
        <div className="flex h-[300px] items-center justify-center text-sm text-[#8a8aa5]">
          Equity tracking started. Check back tomorrow for your first chart.
        </div>
      ) : null}

      <div ref={containerRef} className={days < 2 && !loading ? "hidden" : ""} />

      {performance.length > 0 && (
        <div className="mt-4 border-t border-[#2a2a3e] pt-4">
          <h2 className="mb-3 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
            Performance vs SPY
          </h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[#8a8aa5]">
                <th className="pb-2 text-left font-medium">Account</th>
                <th className="pb-2 text-right font-medium">Return</th>
                <th className="pb-2 text-right font-medium">SPY</th>
                <th className="pb-2 text-right font-medium">Alpha</th>
              </tr>
            </thead>
            <tbody>
              {performance.map((p) => {
                const isCombined = p.account === 0;
                const color = isCombined ? "#7c4dff" : ACCT_COLOR[p.account] ?? "#8888a0";
                return (
                  <tr
                    key={p.account}
                    className={isCombined ? "border-t border-[#2a2a3e] font-semibold" : ""}
                  >
                    <td className="py-1.5 text-left">
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: color }}
                        />
                        <span className="text-[#c0c0d0]">{p.label}</span>
                      </span>
                    </td>
                    <td
                      className="py-1.5 text-right"
                      style={{ color: p.return_pct >= 0 ? "#00d4aa" : "#ff6b6b" }}
                    >
                      {p.return_pct >= 0 ? "+" : ""}{p.return_pct.toFixed(2)}%
                    </td>
                    <td
                      className="py-1.5 text-right"
                      style={
                        p.spy_return_pct === null
                          ? { color: "#5a5a70" }
                          : { color: p.spy_return_pct >= 0 ? "#00d4aa" : "#ff6b6b" }
                      }
                    >
                      {p.spy_return_pct === null
                        ? "—"
                        : `${p.spy_return_pct >= 0 ? "+" : ""}${p.spy_return_pct.toFixed(2)}%`}
                    </td>
                    <td
                      className="py-1.5 text-right"
                      style={
                        p.alpha_pct === null
                          ? { color: "#5a5a70" }
                          : { color: p.alpha_pct >= 0 ? "#00d4aa" : "#ff6b6b" }
                      }
                    >
                      {p.alpha_pct === null
                        ? "—"
                        : `${p.alpha_pct >= 0 ? "+" : ""}${p.alpha_pct.toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

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
        <p className="mt-2 text-right text-xs text-[#8a8aa5]">
          {days} trading days tracked
        </p>
      )}
    </div>
  );
})
