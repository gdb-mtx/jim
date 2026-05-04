import { memo, useEffect, useState } from "react";
import { fetchFilterStatus, fetchFilterMonitorState, fetchPlausibilityState } from "../api";
import type { FilterStatusResponse, FilterMonitorState, PlausibilityState, PlausibilityIssue } from "../types";

type AccountView = 0 | 1 | 2 | 3 | 4;

function formatPrice(n: number, prefix = "$") {
  return `${prefix}${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default memo(function FilterStatusBanner({
  account,
}: {
  account: AccountView;
}) {
  const [filters, setFilters] = useState<FilterStatusResponse | null>(null);
  const [monitorState, setMonitorState] = useState<FilterMonitorState | null>(null);
  const [plausibility, setPlausibility] = useState<PlausibilityState | null>(null);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const load = () => {
      fetchFilterStatus()
        .then((data) => { setFilters(data); setFetchError(false); })
        .catch(() => setFetchError(true));
      fetchFilterMonitorState()
        .then(setMonitorState)
        .catch(() => {});
      fetchPlausibilityState()
        .then(setPlausibility)
        .catch(() => {});
    };
    load();
    const interval = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [account]);

  if (!filters && !fetchError) return null;

  if (fetchError && !filters) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-[#ffc04d40] bg-[#ffc04d08] px-4 py-2.5">
        <span className="h-2 w-2 rounded-full bg-[#ffc04d]" />
        <span className="text-sm text-[#ffc04d]">Filter status unavailable</span>
      </div>
    );
  }

  if (!filters) return null;

  // SPY filter applies to active equity accounts (1, 2). A3 retired 2026-04-20.
  const showSpy = account === 0 || account === 1 || account === 2;
  const showBtc = account === 0 || account === 4;

  const spy = filters.spy;
  const btc = filters.btc;

  // Plausibility banner — filter to tickers relevant to the active view so
  // an SPY issue doesn't clutter Acct 4's crypto view (and vice versa).
  const relevantTickers = new Set<string>();
  if (showSpy) relevantTickers.add("SPY");
  if (showBtc) relevantTickers.add("BTC-USD");
  // On the Combined view, show everything:
  if (account === 0) {
    relevantTickers.add("SPY");
    relevantTickers.add("BTC-USD");
    relevantTickers.add("ETH-USD");
    relevantTickers.add("^VIX");
    relevantTickers.add("SHY");
  }
  const activeIssues: PlausibilityIssue[] = (plausibility?.active_issues ?? [])
    .filter((i) => relevantTickers.has(i.ticker));

  return (
    <div className="flex flex-col gap-3">
      {activeIssues.length > 0 && (
        <div className="rounded-xl border border-[#ff4d6a60] bg-[#ff4d6a10] px-4 py-3">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#ff4d6a]" />
            <span className="text-sm font-medium text-[#ff4d6a]">
              Data plausibility warning — filter decisions may be stale or wrong
            </span>
          </div>
          <ul className="ml-4 space-y-1 text-xs text-[#c0c0d4]">
            {activeIssues.map((iss) => (
              <li key={iss.ticker}>
                <span className="font-medium text-[#e8e8f0]">{iss.ticker}</span>
                {iss.unresolved_failure && iss.last_failure_at && (
                  <span>
                    {" — "}write-time failure {timeAgo(iss.last_failure_at)}
                    {iss.last_failure_obs_min !== undefined &&
                      iss.last_failure_obs_max !== undefined && (
                        <span className="text-[#8888a0]">
                          {" "}(range ${iss.last_failure_obs_min.toFixed(2)}-$
                          {iss.last_failure_obs_max.toFixed(2)})
                        </span>
                      )}
                  </span>
                )}
                {iss.recent_divergence && iss.last_divergence_at && (
                  <span>
                    {" — "}cache vs live divergence{" "}
                    {((iss.last_divergence_pct ?? 0) * 100).toFixed(1)}%{" "}
                    {timeAgo(iss.last_divergence_at)}
                    {iss.last_divergence_cached !== undefined &&
                      iss.last_divergence_live !== undefined && (
                        <span className="text-[#8888a0]">
                          {" "}(cached ${iss.last_divergence_cached.toFixed(2)} vs
                          live ${iss.last_divergence_live.toFixed(2)})
                        </span>
                      )}
                  </span>
                )}
                {iss.last_success_at && (
                  <span className="text-[#8888a0]">
                    {" · "}last successful fetch {timeAgo(iss.last_success_at)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-3">
        {showSpy && spy && !("error" in spy && spy.error) && (
        <div
          className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 ${
            spy.above_ma
              ? "border-[#2a2a3e] bg-[#1a1a2e]"
              : "border-[#ffc04d40] bg-[#ffc04d08]"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              spy.above_ma ? "bg-[#00d4aa]" : "bg-[#ffc04d]"
            }`}
          />
          <span className="text-sm text-[#8888a0]">
            SPY{" "}
            <span className="tabular-nums text-[#e8e8f0]">
              {formatPrice(spy.price)}
            </span>
            {" / "}
            <span className="tabular-nums">{formatPrice(spy.ma_200)}</span>
            {" MA "}
            {spy.above_ma ? (
              <span className="text-[#00d4aa]">— full exposure</span>
            ) : (
              <span className="text-[#ffc04d]">— 50% exposure</span>
            )}
          </span>
        </div>
      )}

      {showBtc && btc && !("error" in btc && btc.error) && (
        <div
          className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 ${
            btc.above_ma
              ? "border-[#2a2a3e] bg-[#1a1a2e]"
              : "border-[#ff4d6a40] bg-[#ff4d6a08]"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              btc.above_ma ? "bg-[#00d4aa]" : "bg-[#ff4d6a]"
            }`}
          />
          <span className="text-sm text-[#8888a0]">
            BTC{" "}
            <span className="tabular-nums text-[#e8e8f0]">
              {formatPrice(btc.price)}
            </span>
            {" / "}
            <span className="tabular-nums">{formatPrice(btc.ma_125 ?? btc.ma_200)}</span>
            {" MA "}
            {btc.above_ma ? (
              <span className="text-[#00d4aa]">— strategy active</span>
            ) : (
              <span className="text-[#ff4d6a]">— strategy in cash</span>
            )}
          </span>
        </div>
      )}

      {/* Filter monitor status */}
      {monitorState?.last_checked && (
        <div className="flex items-center gap-2 rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] px-4 py-2.5">
          <span className="h-2 w-2 rounded-full bg-[#4d8eff]" />
          <span className="text-sm text-[#8888a0]">
            Monitor checked {timeAgo(monitorState.last_checked)}
            {monitorState.recent_auto_rebalances.length > 0 && (
              <span className="text-[#4d8eff]">
                {" — last filter flip rebalanced "}
                {[...new Set(monitorState.recent_auto_rebalances.map((r) => r.account))]
                  .sort()
                  .map((a) => `Acct ${a}`)
                  .join(", ")}{" "}
                ({timeAgo(monitorState.recent_auto_rebalances[0].timestamp)})
              </span>
            )}
          </span>
        </div>
      )}
      </div>
    </div>
  );
})
