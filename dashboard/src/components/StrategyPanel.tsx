import type { StrategyMetrics } from "../types";

interface Props {
  strategies: StrategyMetrics[];
  selected: string | null;
  onSelect: (id: string) => void;
}

const strategyIds: Record<string, string> = {
  "Time-Series Momentum": "ts_momentum",
  "Multi-Timeframe Momentum": "multi_tf_momentum",
  "Cross-Sectional Momentum": "cross_sectional",
  "Dual Momentum": "dual_momentum",
  "Stock Momentum (S&P 500)": "stock_momentum",
};

export default function StrategyPanel({ strategies, selected, onSelect }: Props) {
  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <h2 className="mb-3 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
        Strategies
      </h2>
      <div className="space-y-2">
        {strategies.map((s) => {
          const id = s.id ?? strategyIds[s.name] ?? s.name;
          const isSelected = selected === id;
          const returnColor = s.annualized_return >= 0 ? "text-[#00d4aa]" : "text-[#ff4d6a]";

          return (
            <button
              key={s.name}
              onClick={() => onSelect(id)}
              className={`w-full rounded-lg border p-3 text-left transition-all ${
                isSelected
                  ? "border-[#4d8eff] bg-[#4d8eff10]"
                  : "border-[#2a2a3e] bg-[#12121a] hover:border-[#3a3a4e]"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-[#e8e8f0]">{s.name}</span>
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    s.validation_passed
                      ? "bg-[#00d4aa20] text-[#00d4aa]"
                      : "bg-[#ffc04d20] text-[#ffc04d]"
                  }`}
                >
                  {s.validation_passed ? "Validated" : "Testing"}
                </span>
              </div>
              <div className="mt-2 flex gap-4 text-xs text-[#8888a0]">
                <span>
                  Return:{" "}
                  <span className={returnColor}>
                    {(s.annualized_return * 100).toFixed(1)}%
                  </span>
                </span>
                <span>Sharpe: {s.sharpe_ratio.toFixed(2)}</span>
                <span>
                  MaxDD:{" "}
                  <span className="text-[#ff4d6a]">
                    {(s.max_drawdown * 100).toFixed(1)}%
                  </span>
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
