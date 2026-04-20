import { memo, useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  LineType,
} from "lightweight-charts";
import type { CorrelationReport, EquityPoint } from "../types";
import { fetchCorrelation } from "../api";

// Active-account pairs only (A3 retired 2026-04-20). Live book: A1, A2, A4.
const PAIR_CONFIG = [
  { key: "acct_1_acct_2", label: "Acct 1 \u00d7 2", color: "#00d4aa" },
  { key: "acct_1_acct_4", label: "Acct 1 \u00d7 4", color: "#4d8eff" },
  { key: "acct_2_acct_4", label: "Acct 2 \u00d7 4", color: "#ffc04d" },
] as const;

/** Interpolate green→yellow→red based on correlation value. */
function corrColor(value: number): string {
  const t = Math.max(0, Math.min(1, (value - 0.2) / 0.7)); // 0.2→0, 0.9→1
  if (t < 0.5) {
    // green → yellow
    const u = t * 2;
    const r = Math.round(0 + u * 255);
    const g = Math.round(212 + u * (192 - 212));
    const b = Math.round(170 - u * 170);
    return `rgb(${r},${g},${b})`;
  }
  // yellow → red
  const u = (t - 0.5) * 2;
  const r = Math.round(255);
  const g = Math.round(192 - u * 115);
  const b = Math.round(0 + u * 77);
  return `rgb(${r},${g},${b})`;
}

function ConfidenceBadge({ confidence, days }: { confidence: string | null; days: number }) {
  if (!confidence) return null;
  const isLow = confidence === "low";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs ${
        isLow
          ? "bg-[#ffc04d20] text-[#ffc04d]"
          : "bg-[#2a2a3e] text-[#8888a0]"
      }`}
    >
      {isLow ? `Low confidence (${days} days)` : `${days} days of data`}
    </span>
  );
}

function CorrelationMatrix({
  matrix,
  expected,
}: {
  matrix: Record<string, number>;
  expected: Record<string, number>;
}) {
  // Active accounts only. A3 retired 2026-04-20.
  const accountIds = [1, 2, 4] as const;
  const accounts = accountIds.map((n) => `Acct ${n}`);

  function getValue(i: number, j: number): number | null {
    if (i === j) return 1.0;
    const a = Math.min(accountIds[i], accountIds[j]);
    const b = Math.max(accountIds[i], accountIds[j]);
    return matrix[`acct_${a}_acct_${b}`] ?? null;
  }

  function getExpected(i: number, j: number): number | null {
    if (i === j) return null;
    const a = Math.min(accountIds[i], accountIds[j]);
    const b = Math.max(accountIds[i], accountIds[j]);
    return expected[`acct_${a}_acct_${b}`] ?? null;
  }

  return (
    <div>
      <h3 className="mb-2 text-xs font-medium text-[#8888a0] uppercase">
        Correlation Matrix
      </h3>
      <div className="overflow-hidden rounded-lg border border-[#2a2a3e]">
        <table className="w-full text-center text-xs">
          <thead>
            <tr className="border-b border-[#2a2a3e] bg-[#12121a]">
              <th className="px-3 py-2 text-[#8a8aa5]" />
              {accounts.map((a) => (
                <th key={a} className="px-3 py-2 font-medium text-[#8888a0]">
                  {a}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {accounts.map((row, i) => (
              <tr key={row} className="border-b border-[#2a2a3e] last:border-0">
                <td className="px-3 py-2 font-medium text-[#8888a0]">{row}</td>
                {accounts.map((_, j) => {
                  const val = getValue(i, j);
                  const exp = getExpected(i, j);
                  const isDiag = i === j;
                  return (
                    <td
                      key={j}
                      className="px-3 py-2"
                      style={{
                        color: isDiag ? "#5a5a70" : corrColor(val ?? 0),
                      }}
                    >
                      <div className="font-mono font-medium">
                        {val !== null ? val.toFixed(2) : "—"}
                      </div>
                      {exp !== null && (
                        <div className="text-xs text-[#8a8aa5]">
                          exp {exp.toFixed(2)}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RollingChart({ rolling }: { rolling: Record<string, EquityPoint[]> }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<ISeriesApi<"Line">[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#12121a" },
        textColor: "#8888a0",
        fontFamily: "Inter, sans-serif",
      },
      grid: {
        vertLines: { color: "#2a2a3e" },
        horzLines: { color: "#2a2a3e" },
      },
      width: containerRef.current.clientWidth,
      height: 200,
      timeScale: { borderColor: "#2a2a3e" },
      rightPriceScale: {
        borderColor: "#2a2a3e",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      crosshair: {
        horzLine: { color: "#4d8eff44" },
        vertLine: { color: "#4d8eff44" },
      },
      handleScroll: { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false },
      handleScale: { mouseWheel: false, pinch: false, axisPressedMouseMove: true },
    });
    chartRef.current = chart;

    // Add pair lines
    for (const cfg of PAIR_CONFIG) {
      const series = chart.addSeries(LineSeries, {
        color: cfg.color,
        lineWidth: 1,
        lineType: LineType.Curved,
        priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(2) },
      });
      const data = rolling[cfg.key] ?? [];
      series.setData(data);
      seriesRefs.current.push(series);
    }

    // Alert threshold dashed line at 0.80
    const thresholdSeries = chart.addSeries(LineSeries, {
      color: "#ff4d6a",
      lineWidth: 1,
      lineStyle: 2, // Dashed
      priceFormat: { type: "custom", formatter: (v: number) => v.toFixed(2) },
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // Build threshold line from earliest to latest date across all pairs
    const allDates = Object.values(rolling)
      .flat()
      .map((p) => p.time)
      .sort();
    if (allDates.length >= 2) {
      thresholdSeries.setData([
        { time: allDates[0], value: 0.8 },
        { time: allDates[allDates.length - 1], value: 0.8 },
      ]);
    }

    chart.timeScale().fitContent();

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      seriesRefs.current = [];
    };
  }, [rolling]);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-medium text-[#8888a0] uppercase">
          Rolling 21-Day Correlation
        </h3>
        <div className="flex items-center gap-3 text-xs">
          {PAIR_CONFIG.map((cfg) => (
            <span key={cfg.key} className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3 rounded"
                style={{ backgroundColor: cfg.color }}
              />
              <span className="text-[#8a8aa5]">{cfg.label}</span>
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span className="inline-block h-0.5 w-3 rounded border-t border-dashed border-[#ff4d6a]" />
            <span className="text-[#8a8aa5]">Alert</span>
          </span>
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  );
}

export default memo(function CorrelationPanel() {
  const [report, setReport] = useState<CorrelationReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCorrelation()
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
    // Correlation changes slowly — refresh every 5 minutes
    const interval = setInterval(() => {
      fetchCorrelation().then(setReport).catch(() => {});
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
        <p className="text-sm text-[#8a8aa5]">Loading correlation data...</p>
      </div>
    );
  }

  if (!report) return null;

  // Not enough data yet
  if (report.data_days < 20 || !report.matrix) {
    return (
      <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
        <h2 className="mb-2 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Correlation Monitor
        </h2>
        <p className="text-sm text-[#8a8aa5]">
          Correlation monitoring requires at least 20 trading days. Currently at{" "}
          <span className="font-medium text-[#8888a0]">{report.data_days}</span>{" "}
          days.
        </p>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[#2a2a3e]">
          <div
            className="h-full rounded-full bg-[#4d8eff]"
            style={{ width: `${Math.min(100, (report.data_days / 20) * 100)}%` }}
          />
        </div>
      </div>
    );
  }

  const hasAlert = report.alert_pairs.length > 0;

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Correlation Monitor
        </h2>
        <ConfidenceBadge confidence={report.confidence} days={report.data_days} />
      </div>

      {/* Alert banner */}
      {hasAlert && (
        <div className="mb-3 rounded-lg border border-[#ffc04d40] bg-[#ffc04d10] px-3 py-2 text-xs text-[#ffc04d]">
          High correlation detected (
          {report.alert_pairs
            .map((p) => PAIR_CONFIG.find((c) => c.key === p)?.label ?? p)
            .join(", ")}
          ) — factor diversification may be degrading.
        </div>
      )}

      {/* Matrix + Chart */}
      <div className="space-y-4">
        <CorrelationMatrix
          matrix={report.matrix}
          expected={report.backtest_expected}
        />

        {/* Only show rolling chart if there's enough data for the rolling window */}
        {Object.values(report.rolling).some((arr) => arr.length > 0) && (
          <RollingChart rolling={report.rolling} />
        )}
      </div>
    </div>
  );
})
