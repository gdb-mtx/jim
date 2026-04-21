import { memo, useEffect, useState } from "react";
import { fetchRiskStatus, resetCircuitBreaker } from "../api";
import type { RiskStatusResponse, AccountRiskStatus } from "../types";
import { showToast } from "./Toast";

type AccountView = 0 | 1 | 2 | 3 | 4;

function pctLabel(x: number): string {
  return `${(x * 100).toFixed(0)}%`;
}

export default memo(function RiskStatusPanel({ account }: { account: AccountView }) {
  const [risk, setRisk] = useState<RiskStatusResponse | null>(null);
  const [fetchError, setFetchError] = useState(false);

  const load = () => {
    fetchRiskStatus()
      .then((data) => { setRisk(data); setFetchError(false); })
      .catch(() => setFetchError(true));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  if (!risk && !fetchError) return null;

  if (fetchError && !risk) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#ffc04d40] bg-[#ffc04d08] px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-[#ffc04d]" />
        <span className="text-sm text-[#ffc04d]">Risk status unavailable — API error</span>
      </div>
    );
  }

  if (!risk) return null;

  const accounts = Object.values(risk.accounts).filter(
    (a) => account === 0 || a.account === account
  );

  const anyHalted = accounts.some((a) => a.halted);
  const anyAlert = accounts.some((a) => a.alert_active && !a.halted);

  const handleReset = async (acct: AccountRiskStatus) => {
    const confirmed = window.confirm(
      `Reset catastrophe halt for ${acct.label} (Account ${acct.account})?\n\n` +
      `Only do this after investigating the drawdown cause. The halt exists ` +
      `as a catastrophe backstop — if it tripped, something is very wrong.`
    );
    if (!confirmed) return;
    try {
      const result = await resetCircuitBreaker(acct.account);
      showToast(`Reset Account ${result.account} — can_trade: ${result.can_trade}`, "info");
      load();
    } catch (e) {
      showToast(`Reset failed: ${(e as Error).message}`);
    }
  };

  // Green pill: no halts, no alerts
  if (!anyHalted && !anyAlert) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] px-4 py-3">
        <span className="h-2 w-2 rounded-full bg-[#00d4aa]" />
        <span className="text-sm text-[#8888a0]">
          Drawdown OK — alert at {pctLabel(risk.thresholds.alert)}, halt at {pctLabel(risk.thresholds.halt)}
        </span>
        {fetchError && (
          <span className="ml-2 text-xs text-[#ffc04d]">(stale — API error)</span>
        )}
      </div>
    );
  }

  // Alerts only (amber, informational) — render when no halts are active
  if (!anyHalted && anyAlert) {
    return (
      <div className="rounded-xl border border-[#ffc04d40] bg-[#ffc04d08] p-4">
        <h2 className="mb-2 text-sm font-medium tracking-wide uppercase text-[#ffc04d]">
          Drawdown Alert
        </h2>
        <p className="mb-3 text-xs text-[#8888a0]">
          Account(s) below -{pctLabel(risk.thresholds.alert)}. Informational —
          trading continues. Halt only triggers at -{pctLabel(risk.thresholds.halt)}.
        </p>
        <div className="space-y-2">
          {accounts.filter((a) => a.alert_active).map((a) => (
            <div
              key={a.account}
              className="flex items-center gap-3 rounded-lg border border-[#ffc04d20] bg-[#ffc04d08] px-3 py-2"
            >
              <span className="h-2 w-2 rounded-full bg-[#ffc04d]" />
              <span className="text-sm font-medium text-[#e8e8f0]">
                {a.label} (Account {a.account})
              </span>
              <span className="rounded bg-[#ffc04d20] px-1.5 py-0.5 text-xs font-medium text-[#ffc04d]">
                ALERT ACTIVE
              </span>
              {a.equity_peak > 0 && (
                <span className="text-xs text-[#8888a0]">
                  peak ${a.equity_peak.toLocaleString()}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Catastrophe halt (red, blocking)
  return (
    <div className="rounded-xl border border-[#ff4d6a40] bg-[#ff4d6a08] p-4">
      <h2 className="mb-2 text-sm font-medium tracking-wide uppercase text-[#ff4d6a]">
        Catastrophe Halt
      </h2>
      <p className="mb-3 text-xs text-[#8888a0]">
        Drawdown hit -{pctLabel(risk.thresholds.halt)} kill-switch. Trading
        blocked until manual reset. Investigate before resuming.
      </p>
      <div className="space-y-2">
        {accounts.filter((a) => a.halted).map((a) => (
          <div
            key={a.account}
            className="flex items-center justify-between rounded-lg border border-[#ff4d6a20] bg-[#ff4d6a08] px-3 py-2"
          >
            <div className="flex items-center gap-3">
              <span className="h-2 w-2 rounded-full bg-[#ff4d6a]" />
              <span className="text-sm font-medium text-[#e8e8f0]">
                {a.label} (Account {a.account})
              </span>
              <span className="rounded bg-[#ff4d6a20] px-1.5 py-0.5 text-xs font-medium text-[#ff4d6a]">
                HALTED
              </span>
              {a.equity_peak > 0 && (
                <span className="text-xs text-[#8888a0]">
                  peak ${a.equity_peak.toLocaleString()}
                </span>
              )}
            </div>
            <button
              onClick={() => handleReset(a)}
              className="rounded px-2 py-1 text-xs bg-[#ff4d6a20] text-[#ff4d6a] hover:bg-[#ff4d6a30]"
            >
              Reset Halt
            </button>
          </div>
        ))}
      </div>
    </div>
  );
})
