import { memo, useEffect, useState } from "react";
import { fetchRebalanceHistory } from "../api";
import type { RebalanceHistoryEntry } from "../types";

type AccountView = 0 | 1 | 2 | 3 | 4;

const ACCOUNT_LABELS: Record<number, string> = {
  1: "0.1",
  2: "0.2",
  3: "0.3",
  4: "0.4",
};

function formatTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatUsd(n: number) {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

export default memo(function RebalanceHistory({
  account,
}: {
  account: AccountView;
}) {
  const [entries, setEntries] = useState<RebalanceHistoryEntry[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchRebalanceHistory(50)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered =
    account === 0
      ? entries
      : entries.filter((e) => e.account === account);

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <h2 className="mb-3 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
        Rebalance History
      </h2>

      {loading ? (
        <p className="py-8 text-center text-sm text-[#8888a0] animate-pulse">
          Loading...
        </p>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-sm text-[#8888a0]">
          No rebalance events yet
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                <th className="pb-2 pr-4">Time</th>
                <th className="pb-2 pr-4">Acct</th>
                <th className="pb-2 pr-4">Strategy</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4 text-right">Value</th>
                <th className="pb-2 pr-4 text-right">Orders</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <>
                  <tr
                    key={`row-${i}`}
                    className="border-b border-[#2a2a3e]/50 cursor-pointer hover:bg-[#2a2a3e20]"
                    onClick={() => setExpanded(expanded === i ? null : i)}
                  >
                    <td className="py-2.5 pr-4 tabular-nums text-[#8888a0]">
                      {formatTime(e.timestamp)}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className="rounded bg-[#4d8eff20] px-1.5 py-0.5 text-xs font-medium text-[#4d8eff]">
                        {ACCOUNT_LABELS[e.account] || "?"}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-[#e8e8f0]">
                      {e.strategy_id}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          e.source === "scheduled"
                            ? "bg-[#7c4dff20] text-[#7c4dff]"
                            : "bg-[#4d8eff20] text-[#4d8eff]"
                        }`}
                      >
                        {e.source}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                      {formatUsd(e.portfolio_value)}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                      {e.orders_submitted}
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          e.orders_failed > 0
                            ? "bg-[#ff4d6a20] text-[#ff4d6a]"
                            : "bg-[#00d4aa20] text-[#00d4aa]"
                        }`}
                      >
                        {e.orders_failed > 0
                          ? `${e.orders_failed} failed`
                          : "OK"}
                      </span>
                      {e.spy_filter_active && (
                        <span className="ml-1.5 rounded bg-[#ffc04d20] px-1.5 py-0.5 text-xs font-medium text-[#ffc04d]">
                          SPY filter
                        </span>
                      )}
                      {e.btc_filter_active && (
                        <span className="ml-1.5 rounded bg-[#ff4d6a20] px-1.5 py-0.5 text-xs font-medium text-[#ff4d6a]">
                          BTC filter
                        </span>
                      )}
                    </td>
                  </tr>
                  {expanded === i && e.orders.length > 0 && (
                    <tr key={`detail-${i}`}>
                      <td colSpan={7} className="px-4 pb-3 pt-1">
                        <div className="rounded-lg border border-[#2a2a3e] bg-[#12121a] p-3">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-[#8888a0]">
                                <th className="pb-1 pr-3">Symbol</th>
                                <th className="pb-1 pr-3">Side</th>
                                <th className="pb-1 pr-3 text-right">Qty</th>
                                <th className="pb-1 pr-3">Status</th>
                                <th className="pb-1">Error</th>
                              </tr>
                            </thead>
                            <tbody>
                              {e.orders.map((o, j) => (
                                <tr
                                  key={j}
                                  className="border-t border-[#2a2a3e]/30"
                                >
                                  <td className="py-1 pr-3 text-[#e8e8f0]">
                                    {o.symbol}
                                  </td>
                                  <td className="py-1 pr-3">
                                    <span
                                      className={`rounded px-1 py-0.5 text-xs font-medium ${
                                        o.side === "buy"
                                          ? "bg-[#00d4aa20] text-[#00d4aa]"
                                          : "bg-[#ff4d6a20] text-[#ff4d6a]"
                                      }`}
                                    >
                                      {o.side.toUpperCase()}
                                    </span>
                                  </td>
                                  <td className="py-1 pr-3 text-right tabular-nums text-[#e8e8f0]">
                                    {o.qty}
                                  </td>
                                  <td className="py-1 pr-3 text-[#8888a0]">
                                    {o.status}
                                  </td>
                                  <td className="py-1 text-[#ff4d6a]">
                                    {o.error || ""}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
})
