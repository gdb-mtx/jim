import { useEffect, useState } from "react";
import { fetchPortfolio, fetchPositions, fetchOrders } from "../api";
import type { PortfolioSummary, Position, Order } from "../types";

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

export default function LivePortfolio() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState(false);

  const refresh = () => {
    Promise.all([fetchPortfolio(), fetchPositions(), fetchOrders()])
      .then(([s, p, o]) => {
        setSummary(s);
        setPositions(p);
        setOrders(o);
        setError(false);
      })
      .catch(() => setError(true));
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className="rounded-xl border border-[#ff4d6a40] bg-[#ff4d6a10] p-6 text-sm text-[#ff4d6a]">
        Could not connect to Alpaca. Make sure the backend is running.
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-xl border border-[#2a2a3e] bg-[#1a1a2e]">
        <p className="animate-pulse text-[#8888a0]">Loading portfolio...</p>
      </div>
    );
  }

  const invested = summary.equity - summary.cash;

  return (
    <div className="space-y-6">
      {/* Account summary cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">Equity</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(summary.equity)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">Cash</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(summary.cash)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">Invested</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-[#e8e8f0]">
            {formatUsd(invested)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">Day P&L</p>
          <p className={`mt-1 text-2xl font-semibold tabular-nums ${plColor(summary.daily_pnl)}`}>
            {formatUsd(summary.daily_pnl)}
          </p>
        </div>
        <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
          <p className="text-xs font-medium tracking-wide text-[#8888a0] uppercase">Unrealized P&L</p>
          <p className={`mt-1 text-2xl font-semibold tabular-nums ${plColor(summary.total_unrealized_pl)}`}>
            {formatUsd(summary.total_unrealized_pl)}
          </p>
        </div>
      </div>

      {/* Positions table */}
      <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
            Positions ({positions.length})
          </h2>
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${summary.market_open ? "bg-[#00d4aa]" : "bg-[#8888a0]"}`} />
            <span className="text-xs text-[#8888a0]">
              {summary.market_open ? "Market Open" : "Market Closed"}
            </span>
          </div>
        </div>
        {positions.length === 0 ? (
          <p className="py-8 text-center text-sm text-[#8888a0]">No open positions</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4 text-right">Qty</th>
                  <th className="pb-2 pr-4 text-right">Entry</th>
                  <th className="pb-2 pr-4 text-right">Current</th>
                  <th className="pb-2 pr-4 text-right">Mkt Value</th>
                  <th className="pb-2 pr-4 text-right">P&L</th>
                  <th className="pb-2 text-right">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {positions
                  .sort((a, b) => b.market_value - a.market_value)
                  .map((p) => (
                    <tr key={p.symbol} className="border-b border-[#2a2a3e]/50">
                      <td className="py-2.5 pr-4 font-medium text-[#e8e8f0]">{p.symbol}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">{p.qty}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#8888a0]">
                        {formatUsd(p.avg_entry_price)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {formatUsd(p.current_price)}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {formatUsd(p.market_value)}
                      </td>
                      <td className={`py-2.5 pr-4 text-right tabular-nums ${plColor(p.unrealized_pl)}`}>
                        {formatUsd(p.unrealized_pl)}
                      </td>
                      <td className={`py-2.5 text-right tabular-nums ${plColor(p.unrealized_plpc)}`}>
                        {(p.unrealized_plpc * 100).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-[#2a2a3e]">
                  <td className="pt-2.5 pr-4 font-medium text-[#e8e8f0]">Total</td>
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4" />
                  <td className="pt-2.5 pr-4 text-right tabular-nums font-medium text-[#e8e8f0]">
                    {formatUsd(positions.reduce((s, p) => s + p.market_value, 0))}
                  </td>
                  <td className={`pt-2.5 pr-4 text-right tabular-nums font-medium ${plColor(summary.total_unrealized_pl)}`}>
                    {formatUsd(summary.total_unrealized_pl)}
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
          <p className="py-8 text-center text-sm text-[#8888a0]">No orders yet</p>
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
                  <tr key={o.order_id} className="border-b border-[#2a2a3e]/50">
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
                    <td className="py-2.5 pr-4 font-medium text-[#e8e8f0]">{o.symbol}</td>
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
                      {o.filled_avg_price ? formatUsd(o.filled_avg_price) : "—"}
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
