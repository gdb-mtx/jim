import { useEffect, useState } from "react";
import PortfolioChart from "./components/PortfolioChart";
import MetricCard from "./components/MetricCard";
import StrategyPanel from "./components/StrategyPanel";
import LivePortfolio from "./components/LivePortfolio";
import ErrorBoundary from "./components/ErrorBoundary";
import ToastContainer, { showToast } from "./components/Toast";
import { fetchStrategies, fetchBacktest } from "./api";
import type { StrategyMetrics, BacktestResult } from "./types";
import "./index.css";

type Tab = "backtest" | "portfolio";

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
            {/* Metrics row */}
            {m && (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <MetricCard
                  label="Annual Return"
                  value={`${(m.annualized_return * 100).toFixed(1)}%`}
                  color={m.annualized_return >= 0 ? "green" : "red"}
                />
                <MetricCard
                  label="Sharpe Ratio"
                  value={m.sharpe_ratio.toFixed(2)}
                  subtext={m.sharpe_ratio >= 1 ? "Target met" : "Below 1.0 target"}
                  color={m.sharpe_ratio >= 1 ? "green" : "yellow"}
                />
                <MetricCard
                  label="Max Drawdown"
                  value={`${(m.max_drawdown * 100).toFixed(1)}%`}
                  color="red"
                />
                <MetricCard
                  label="Kelly (Quarter)"
                  value={`${(m.kelly_quarter * 100).toFixed(1)}%`}
                  subtext="Position size"
                  color="blue"
                />
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
