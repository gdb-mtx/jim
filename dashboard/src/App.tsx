import { useEffect, useState } from "react";
import PortfolioChart from "./components/PortfolioChart";
import MetricCard from "./components/MetricCard";
import StrategyPanel from "./components/StrategyPanel";
import LivePortfolio from "./components/LivePortfolio";
import OpsPage from "./pages/OpsPage";
import ErrorBoundary from "./components/ErrorBoundary";
import ToastContainer, { showToast } from "./components/Toast";
import { fetchStrategies, fetchBacktest } from "./api";
import type { StrategyMetrics, BacktestResult } from "./types";
import "./index.css";

type Tab = "backtest" | "portfolio" | "ops";

function App() {
  const [tab, setTab] = useState<Tab>("portfolio");
  const [strategies, setStrategies] = useState<StrategyMetrics[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tryConnect = async (retries = 5, delay = 1000) => {
      for (let i = 0; i < retries; i++) {
        try {
          const data = await fetchStrategies();
          if (!cancelled) {
            setStrategies(data);
            setApiError(false);
            // Default Backtest tab to the combined 3-account strategy so the
            // chart renders on first load. Only seed if the user hasn't
            // picked anything yet.
            setSelected((prev) => {
              if (prev) return prev;
              const hasCombined = data.some((s) => (s.id ?? s.name) === "combined_3account");
              return hasCombined ? "combined_3account" : (data[0]?.id ?? data[0]?.name ?? null);
            });
          }
          return;
        } catch (e) {
          if (i < retries - 1) {
            await new Promise((r) => setTimeout(r, delay));
          } else if (!cancelled) {
            setApiError(true);
            showToast(`Backend unreachable: ${(e as Error).message}`, "warning");
          }
        }
      }
    };
    tryConnect();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetchBacktest(selected)
      .then((data) => {
        setBacktest(data);
        setLoading(false);
      })
      .catch((e) => {
        setLoading(false);
        showToast(`Backtest failed: ${e.message}`);
      });
  }, [selected]);

  const m = backtest?.metrics;

  return (
    <div className="min-h-screen bg-[#0a0a0f] p-6">
      {/* Header */}
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-[#e8e8f0]">
            FIRE
          </h1>
          <p className="text-sm text-[#8888a0]">
            Quantitative Trading Dashboard
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* Tab switcher */}
          <div className="flex rounded-lg border border-[#2a2a3e] bg-[#12121a] p-0.5">
            <button
              onClick={() => setTab("portfolio")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                tab === "portfolio"
                  ? "bg-[#4d8eff] text-white"
                  : "text-[#8888a0] hover:text-[#e8e8f0]"
              }`}
            >
              Live Portfolio
            </button>
            <button
              onClick={() => setTab("backtest")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                tab === "backtest"
                  ? "bg-[#4d8eff] text-white"
                  : "text-[#8888a0] hover:text-[#e8e8f0]"
              }`}
            >
              Backtests
            </button>
            <button
              onClick={() => setTab("ops")}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition-all ${
                tab === "ops"
                  ? "bg-[#4d8eff] text-white"
                  : "text-[#8888a0] hover:text-[#e8e8f0]"
              }`}
            >
              Ops
            </button>
          </div>
          <span className="rounded-full bg-[#00d4aa20] px-3 py-1 text-xs font-medium text-[#00d4aa]">
            Paper Trading
          </span>
        </div>
      </header>

      {apiError && (
        <div className="mb-6 rounded-lg border border-[#ffc04d40] bg-[#ffc04d10] p-4 text-sm text-[#ffc04d]">
          API not connected. Start the backend with:{" "}
          <code className="rounded bg-[#0a0a0f] px-2 py-0.5 text-xs">
            uv run uvicorn api.main:app --reload
          </code>
        </div>
      )}

      <ErrorBoundary>
      {/* Live Portfolio view */}
      {tab === "portfolio" && (
        <LivePortfolio />
      )}

      {/* Ops view */}
      {tab === "ops" && (
        <OpsPage />
      )}

      {/* Backtest view */}
      {tab === "backtest" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {/* Left sidebar — Strategy list */}
          <div className="lg:col-span-1">
            <StrategyPanel
              strategies={strategies}
              selected={selected}
              onSelect={setSelected}
            />
          </div>

          {/* Main content */}
          <div className="space-y-6 lg:col-span-3">
            {/* Metrics table — Full / In-Sample / Out-of-Sample */}
            {m && backtest && (
              <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
                <div className="mb-3 flex items-start justify-between gap-4">
                  <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
                    Performance — Full / In-Sample / Out-of-Sample
                  </h2>
                  <p className="max-w-md text-right text-xs leading-snug text-[#8a8aa5]">
                    IS = design window (through {backtest.train_end ?? "2022-12-31"}).
                    OOS = held-out test (2023-01-01 onward), the number the validation gate actually checks.
                  </p>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-[#8a8aa5]">
                      <th className="pb-2 text-left font-medium">Period</th>
                      <th className="pb-2 text-right font-medium">CAGR</th>
                      <th className="pb-2 text-right font-medium">MaxDD</th>
                      <th className="pb-2 text-right font-medium">Calmar</th>
                      <th className="pb-2 text-right font-medium">Sharpe</th>
                      <th className="pb-2 text-right font-medium">Days</th>
                    </tr>
                  </thead>
                  <tbody>
                    {([
                      { key: "full", label: "Full sample", cagr: m.annualized_return, maxdd: m.max_drawdown, calmar: m.calmar_ratio, sharpe: m.sharpe_ratio, days: backtest.equity_curve.length, range: `${backtest.equity_curve[0]?.time} → ${backtest.equity_curve[backtest.equity_curve.length-1]?.time}` },
                      backtest.is_metrics ? { key: "is", label: "In-sample (design)", cagr: backtest.is_metrics.cagr, maxdd: backtest.is_metrics.max_drawdown, calmar: backtest.is_metrics.calmar_ratio, sharpe: backtest.is_metrics.sharpe_ratio, days: backtest.is_metrics.n_days, range: `${backtest.is_metrics.period_start} → ${backtest.is_metrics.period_end}` } : null,
                      backtest.oos_metrics ? { key: "oos", label: "Out-of-sample", cagr: backtest.oos_metrics.cagr, maxdd: backtest.oos_metrics.max_drawdown, calmar: backtest.oos_metrics.calmar_ratio, sharpe: backtest.oos_metrics.sharpe_ratio, days: backtest.oos_metrics.n_days, range: `${backtest.oos_metrics.period_start} → ${backtest.oos_metrics.period_end}` } : null,
                    ].filter(Boolean) as Array<{key:string; label:string; cagr:number; maxdd:number; calmar:number; sharpe:number; days:number; range:string}>).map((row) => (
                      <tr
                        key={row.key}
                        className={row.key === "oos" ? "border-t border-[#2a2a3e] font-semibold" : row.key === "is" ? "" : "border-b border-[#2a2a3e]/50"}
                        title={row.range}
                      >
                        <td className="py-1.5 text-left text-[#c0c0d0]">{row.label}</td>
                        <td className="py-1.5 text-right" style={{ color: row.cagr >= 0 ? "#00d4aa" : "#ff6b6b" }}>
                          {row.cagr >= 0 ? "+" : ""}{(row.cagr * 100).toFixed(2)}%
                        </td>
                        <td className="py-1.5 text-right text-[#ff6b6b]">{(row.maxdd * 100).toFixed(2)}%</td>
                        <td className="py-1.5 text-right text-[#c0c0d0]">{row.calmar.toFixed(2)}</td>
                        <td className="py-1.5 text-right text-[#8888a0]">{row.sharpe.toFixed(2)}</td>
                        <td className="py-1.5 text-right text-[#8a8aa5]">{row.days}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Chart */}
            {loading && (
              <div className="flex h-[400px] items-center justify-center rounded-xl border border-[#2a2a3e] bg-[#1a1a2e]">
                <p className="animate-pulse text-[#8888a0]">
                  Running backtest...
                </p>
              </div>
            )}
            {backtest && !loading && (
              <PortfolioChart
                data={backtest.equity_curve}
                spyData={backtest.spy_curve}
                oosStart={backtest.oos_start ?? null}
                title={`${backtest.strategy} — Equity Curve ($10k start)`}
              />
            )}
            {!selected && !loading && (
              <div className="flex h-[400px] items-center justify-center rounded-xl border border-[#2a2a3e] bg-[#1a1a2e]">
                <p className="text-[#8888a0]">
                  Select a strategy to view its backtest
                </p>
              </div>
            )}

            {/* Detailed metrics */}
            {m && (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
                <MetricCard label="Win Rate" value={`${(m.win_rate * 100).toFixed(1)}%`} />
                <MetricCard label="Profit Factor" value={m.profit_factor.toFixed(2)} />
                <MetricCard label="Calmar Ratio" value={m.calmar_ratio.toFixed(2)} />
                <MetricCard
                  label="Kelly Full"
                  value={`${(m.kelly_criterion * 100).toFixed(1)}%`}
                />
                <MetricCard
                  label="Kelly Half"
                  value={`${(m.kelly_half * 100).toFixed(1)}%`}
                />
              </div>
            )}
          </div>
        </div>
      )}
      </ErrorBoundary>

      {/* Footer */}
      <footer className="mt-12 text-center text-xs text-[#8888a050]">
        FIRE Quantitative Trading System &mdash; Built with Claude Code
      </footer>

      <ToastContainer />
    </div>
  );
}

export default App;
