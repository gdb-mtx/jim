import { useEffect, useState } from "react";
import {
  fetchPortfolio,
  fetchPositions,
  fetchOrders,
  fetchCombinedPortfolio,
} from "../api";
import type { PortfolioSummary, Position, Order } from "../types";
import EquityHistoryChart from "./EquityHistoryChart";
import CorrelationPanel from "./CorrelationPanel";

type AccountView = 0 | 1 | 2 | 3 | 4; // 0 = combined

const ACCOUNTS: { id: AccountView; name: string; label: string }[] = [
  { id: 0, name: "Combined", label: "All Accounts" },
  { id: 1, name: "FIRE 0.1", label: "Momentum" },
  { id: 2, name: "FIRE 0.2", label: "Trend + Low-Vol" },
  { id: 3, name: "FIRE 0.3", label: "Reversal Blend" },
  { id: 4, name: "FIRE 0.4", label: "Crypto" },
];

interface CombinedData {
  equity: number;
  cash: number;
  daily_pnl: number;
  total_unrealized_pl: number;
  positions_count: number;
  positions: (Position & { account: number })[];
  market_open: boolean;
}

function formatUsd(n: number) {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

function plColor(n: number) {
  if (n > 0) return "text-[#00d4aa]";
  if (n < 0) return "text-[#ff4d6a]";
  return "text-[#8888a0]";
}

const ACCOUNT_LABELS: Record<number, string> = {
  1: "0.1",
  2: "0.2",
  3: "0.3",
  4: "0.4",
};

export default function LivePortfolio() {
  const [account, setAccount] = useState<AccountView>(0);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [combined, setCombined] = useState<CombinedData | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [combinedPositions, setCombinedPositions] = useState<
    (Position & { account: number })[]
  >([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  const refreshSingle = (acct: number) => {
    setLoading(true);
    Promise.all([
      fetchPortfolio(acct),
      fetchPositions(acct),
      fetchOrders(acct),
    ])
      .then(([s, p, o]) => {
        setSummary(s);
        setPositions(p);
        setOrders(o);
        setError(false);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  };

  const refreshCombined = () => {
    setLoading(true);
    // Fetch combined summary + orders from all accounts
    Promise.all([
      fetchCombinedPortfolio(),
      fetchOrders(1).catch((e) => { console.warn("Orders acct 1:", e.message); return []; }),
      fetchOrders(2).catch((e) => { console.warn("Orders acct 2:", e.message); return []; }),
      fetchOrders(3).catch((e) => { console.warn("Orders acct 3:", e.message); return []; }),
      fetchOrders(4).catch((e) => { console.warn("Orders acct 4:", e.message); return []; }),
    ])
      .then(([c, o1, o2, o3, o4]) => {
        setCombined(c);
        setCombinedPositions(c.positions || []);
        // Merge and sort orders by time
        const allOrders = [...o1, ...o2, ...o3, ...o4].sort(
          (a: Order, b: Order) =>
            new Date(b.submitted_at).getTime() -
            new Date(a.submitted_at).getTime()
        );
        setOrders(allOrders);
        setError(false);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  };

  useEffect(() => {
    if (account === 0) {
      refreshCombined();
      const interval = setInterval(refreshCombined, 30000);
      return () => clearInterval(interval);
    } else {
      refreshSingle(account);
      const interval = setInterval(() => refreshSingle(account), 30000);
      return () => clearInterval(interval);
    }
  }, [account]);

  const switchAccount = (acct: AccountView) => {
    setSummary(null);
    setCombined(null);
    setPositions([]);
    setCombinedPositions([]);
    setOrders([]);
    setAccount(acct);
  };

  // Determine current view data
  const isCombined = account === 0;
  const viewData = isCombined
    ? combined
      ? {
          equity: combined.equity,
          cash: combined.cash,
          daily_pnl: combined.daily_pnl,
          total_unrealized_pl: combined.total_unrealized_pl,
          market_open: combined.market_open,
        }
      : null
    : summary
      ? {
          equity: summary.equity,
          cash: summary.cash,
          daily_pnl: summary.daily_pnl,
          total_unrealized_pl: summary.total_unrealized_pl,
          market_open: summary.market_open,
        }
      : null;

  const viewPositions = isCombined ? combinedPositions : positions;

  if (error) {
    return (
      <div className="space-y-4">
        <AccountTabs account={account} onSwitch={switchAccount} />
        <div className="rounded-xl border border-[#ff4d6a40] bg-[#ff4d6a10] p-6 text-sm text-[#ff4d6a]">
          Could not connect to Alpaca. Make sure the backend is running and
          credentials are configured.
        </div>
      </div>
    );
  }

  if (!viewData || loading) {
    return (
      <div className="space-y-4">
        <AccountTabs account={account} onSwitch={switchAccount} />
        <div className="flex h-[200px] items-center justify-center rounded-xl border border-[#2a2a3e] bg-[#1a1a2e]">
          <p className="animate-pulse text-[#8888a0]">Loading portfolio...</p>
        </div>
      </div>
    );
  }

  const invested = viewData.equity - viewData.cash;

  return (
    <div className="space-y-6">
      {/* Account switcher */}
      <AccountTabs account={account} onSwitch={switchAccount} />

      {/* Account summary cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            Equity
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(viewData.equity)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            Cash
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(viewData.cash)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            Invested
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(invested)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            Day P&L
          </p>
          <p
            className={`mt-1 text-2xl font-semibold tabular-nums ${plColor(viewData.daily_pnl)}`}
          >
            {formatUsd(viewData.daily_pnl)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            Unrealized P&L
          </p>
          <p
            className={`mt-1 text-2xl font-semibold tabular-nums ${plColor(viewData.total_unrealized_pl)}`}
          >
            {formatUsd(viewData.total_unrealized_pl)}
          </p>
        </div>
      </div>

      {/* Live equity chart */}
      <EquityHistoryChart account={account} />

      {/* Correlation monitor (combined view only) */}
      {isCombined && <CorrelationPanel />}

      {/* Positions table */}
      <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
            Positions ({viewPositions.length})
          </h2>
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${viewData.market_open ? "bg-[#00d4aa]" : "bg-[#8888a0]"}`}
            />
            <span className="text-xs text-[#8888a0]">
              {viewData.market_open ? "Market Open" : "Market Closed"}
            </span>
          </div>
        </div>
        {viewPositions.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#8888a0]">
            No open positions
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                  <th className="pb-2 pr-4">Symbol</th>
                  {isCombined && <th className="pb-2 pr-4">Acct</th>}
                  <th className="pb-2 pr-4 text-right">Qty</th>
                  <th className="pb-2 pr-4 text-right">Entry</th>
                  <th className="pb-2 pr-4 text-right">Current</th>
                  <th className="pb-2 pr-4 text-right">Mkt Value</th>
                  <th className="pb-2 pr-4 text-right">P&L</th>
                  <th className="pb-2 text-right">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {[...viewPositions]
                  .sort((a, b) => b.market_value - a.market_value)
                  .map((p, i) => (
                    <tr
                      key={
                        isCombined
                          ? `${(p as Position & { account: number }).account}-${p.symbol}`
                          : p.symbol
                      }
                      className="border-b border-[#2a2a3e]/50"
                    >
                      <td className="py-2.5 pr-4 font-medium text-[#e8e8f0]">
                        {p.symbol}
                      </td>
                      {isCombined && (
                        <td className="py-2.5 pr-4">
                          <span className="rounded bg-[#4d8eff20] px-1.5 py-0.5 text-xs font-medium text-[#4d8eff]">
                            {ACCOUNT_LABELS[
                              (p as Position & { account: number }).account
                            ] || "?"}
                          </span>
                        </td>
                      )}
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {p.qty}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#8888a0]">
                        {formatUsd(p.avg_entry_price)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {formatUsd(p.current_price)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {formatUsd(p.market_value)}
                      </td>
                      <td
                        className={`py-2.5 pr-4 text-right tabular-nums ${plColor(p.unrealized_pl)}`}
                      >
                        {formatUsd(p.unrealized_pl)}
                      </td>
                      <td
                        className={`py-2.5 text-right tabular-nums ${plColor(p.unrealized_plpc)}`}
                      >
                        {(p.unrealized_plpc * 100).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-[#2a2a3e]">
                  <td className="pt-2.5 pr-4 font-medium text-[#e8e8f0]">
                    Total
                  </td>
                  {isCombined && <td className="pt-2.5 pr-4" />}
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4 text-right tabular-nums font-medium text-[#e8e8f0]">
                    {formatUsd(
                      viewPositions.reduce((s, p) => s + p.market_value, 0)
                    )}
                  </td>
                  <td
                    className={`pt-2.5 pr-4 text-right tabular-nums font-medium ${plColor(viewData.total_unrealized_pl)}`}
                  >
                    {formatUsd(viewData.total_unrealized_pl)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>

      {/* Recent orders */}
      <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
        <h2 className="mb-3 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Recent Orders
        </h2>
        {orders.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#8888a0]">
            No orders yet
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                  <th className="pb-2 pr-4">Time</th>
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Side</th>
                  <th className="pb-2 pr-4 text-right">Qty</th>
                  <th className="pb-2 pr-4 text-right">Fill Price</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {orders.slice(0, 20).map((o) => (
                  <tr
                    key={o.order_id}
                    className="border-b border-[#2a2a3e]/50"
                  >
                    <td className="py-2.5 pr-4 tabular-nums text-[#8888a0]">
                      {o.filled_at
                        ? new Date(o.filled_at).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : new Date(o.submitted_at).toLocaleString("en-US", {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                    </td>
                    <td className="py-2.5 pr-4 font-medium text-[#e8e8f0]">
                      {o.symbol}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          o.side === "buy"
                            ? "bg-[#00d4aa20] text-[#00d4aa]"
                            : "bg-[#ff4d6a20] text-[#ff4d6a]"
                        }`}
                      >
                        {o.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                      {o.filled_qty || o.qty}
                    </td>
                    <td className="py-2.5 pr-4 text-right tabular-nums text-[#8888a0]">
                      {o.filled_avg_price
                        ? formatUsd(o.filled_avg_price)
                        : "\u2014"}
                    </td>
                    <td className="py-2.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          o.status === "filled"
                            ? "bg-[#00d4aa20] text-[#00d4aa]"
                            : o.status === "canceled" || o.status === "expired"
                              ? "bg-[#8888a020] text-[#8888a0]"
                              : "bg-[#ffc04d20] text-[#ffc04d]"
                        }`}
                      >
                        {o.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function AccountTabs({
  account,
  onSwitch,
}: {
  account: AccountView;
  onSwitch: (acct: AccountView) => void;
}) {
  return (
    <div className="flex rounded-lg border border-[#2a2a3e] bg-[#12121a] p-1 w-fit">
      {ACCOUNTS.map((acct) => (
        <button
          key={acct.id}
          onClick={() => onSwitch(acct.id)}
          className={`rounded-md px-4 py-2 text-xs font-medium transition-all ${
            account === acct.id
              ? acct.id === 0
                ? "bg-[#7c4dff] text-white"
                : "bg-[#4d8eff] text-white"
              : "text-[#8888a0] hover:text-[#e8e8f0]"
          }`}
        >
          <span className="font-semibold">{acct.name}</span>
          <span className="ml-1.5 opacity-70">{acct.label}</span>
        </button>
      ))}
    </div>
  );
}
