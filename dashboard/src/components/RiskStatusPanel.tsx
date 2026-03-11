import { memo, useEffect, useState } from "react";
import { fetchRiskStatus, resetCircuitBreaker } from "../api";
import type { RiskStatusResponse, AccountRiskStatus } from "../types";
import { showToast } from "./Toast";

type AccountView = 0 | 1 | 2 | 3 | 4;

export default memo(function RiskStatusPanel({ account }: { account: AccountView }) {
  const [risk, setRisk] = useState<RiskStatusResponse | null>(null);

  const load = () => {
    fetchRiskStatus().then(setRisk).catch(() => {});
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, []);

  if (!risk) return null;

  // Filter accounts based on view
  const accounts = Object.values(risk.accounts).filter(
    (a) => account === 0 || a.account === account
  );

  const anyHalted = accounts.some((a) => a.halted || a.halted_strategies.length > 0);

  const handleReset = async (acct: AccountRiskStatus, strategy?: string) => {
    const target = strategy || "portfolio-level circuit breaker";
    if (!window.confirm(`Reset ${target} for ${acct.label} (Account ${acct.account})? Only do this after investigating the drawdown cause.`)) {
      return;
    }
    try {
      const result = await resetCircuitBreaker(acct.account, strategy);
      showToast(`Reset ${result.reset} — can_trade: ${result.can_trade}`, "info");
      load();
    } catch (e) {
      showToast(`Reset failed: ${(e as Error).message}`);
    }
  };

  if (!anyHalted) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-[#00d4aa]" />
        <span className="text-sm text-[#8888a0]">All circuit breakers OK</span>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#ff4d6a40] bg-[#ff4d6a08] p-4">
      <h2 className="mb-3 text-sm font-medium tracking-wide uppercase text-[#ff4d6a]">
        Circuit Breaker Alert
      </h2>
      <div className="space-y-2">
        {accounts
          .filter((a) => a.halted || a.halted_strategies.length > 0)
          .map((a) => (
            <div
              key={a.account}
              className="flex items-center justify-between rounded-lg border border-[#ff4d6a20] bg-[#ff4d6a08] px-3 py-2"
            >
              <div className="flex items-center gap-3">
                <span className="h-2 w-2 rounded-full bg-[#ff4d6a]" />
                <span className="text-sm font-medium text-[#e8e8f0]">
                  {a.label} (Account {a.account})
                </span>
                {a.halted && (
                  <span className="rounded bg-[#ff4d6a20] px-1.5 py-0.5 text-xs font-medium text-[#ff4d6a]">
                    PORTFOLIO HALTED
                  </span>
                )}
                {a.halted_strategies.map((s) => (
                  <span
                    key={s}
                    className="rounded bg-[#ffc04d20] px-1.5 py-0.5 text-xs font-medium text-[#ffc04d]"
                  >
                    {s} halted
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                {a.halted && (
                  <button
                    onClick={() => handleReset(a)}
                    className="rounded px-2 py-1 text-xs bg-[#ff4d6a20] text-[#ff4d6a] hover:bg-[#ff4d6a30]"
                  >
                    Reset Portfolio
                  </button>
                )}
                {a.halted_strategies.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleReset(a, s)}
                    className="rounded px-2 py-1 text-xs bg-[#ffc04d20] text-[#ffc04d] hover:bg-[#ffc04d30]"
                  >
                    Reset {s}
                  </button>
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
})
