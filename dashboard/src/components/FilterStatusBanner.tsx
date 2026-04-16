import { memo, useEffect, useState } from "react";
import { fetchFilterStatus, fetchFilterMonitorState } from "../api";
import type { FilterStatusResponse, FilterMonitorState } from "../types";

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
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    const load = () => {
      fetchFilterStatus()
        .then((data) => { setFilters(data); setFetchError(false); })
        .catch(() => setFetchError(true));
      fetchFilterMonitorState()
        .then(setMonitorState)
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

  const showSpy = account === 0 || (account >= 1 && account <= 3);
  const showBtc = account === 0 || account === 4;

  const spy = filters.spy;
  const btc = filters.btc;

  return (
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
            <span className="tabular-nums">{formatPrice(btc.ma_150 ?? btc.ma_200)}</span>
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
                {" — "}auto-rebalanced{" "}
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
  );
})
