import { memo, useEffect, useMemo, useState } from "react";
import { fetchRebalancePreview, executeRebalance } from "../api";
import type { RebalanceOrder, RebalancePreview } from "../types";
import { showToast } from "./Toast";

type State = "idle" | "previewing" | "previewed" | "executing" | "executed";
type Action = "new" | "increase" | "decrease" | "exit";

const ACTION_CONFIG: Record<Action, { label: string; color: string; bg: string }> = {
  new:      { label: "NEW",      color: "#00d4aa", bg: "#00d4aa20" },
  increase: { label: "INCREASE", color: "#4d8eff", bg: "#4d8eff20" },
  decrease: { label: "DECREASE", color: "#ffc04d", bg: "#ffc04d20" },
  exit:     { label: "EXIT",     color: "#ff4d6a", bg: "#ff4d6a20" },
};

const ACTION_ORDER: Action[] = ["new", "exit", "increase", "decrease"];

function formatUsd(n: number) {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

function OrdersTable({
  orders,
  prices,
}: {
  orders: RebalanceOrder[];
  prices?: Record<string, number>;
}) {
  const grouped = useMemo(() => {
    const groups: Record<Action, RebalanceOrder[]> = {
      new: [],
      increase: [],
      decrease: [],
      exit: [],
    };
    for (const o of orders) {
      const action = (o.action ?? (o.side === "buy" ? "increase" : "decrease")) as Action;
      groups[action].push(o);
    }
    // Sort each group by symbol
    for (const g of Object.values(groups)) {
      g.sort((a, b) => a.symbol.localeCompare(b.symbol));
    }
    return groups;
  }, [orders]);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
            <th className="pb-2 pr-4">Symbol</th>
            <th className="pb-2 pr-4">Action</th>
            <th className="pb-2 pr-4 text-right">Current</th>
            <th className="pb-2 pr-4 text-center">→</th>
            <th className="pb-2 pr-4 text-right">Target</th>
            <th className="pb-2 pr-4 text-right">Change</th>
            <th className="pb-2 text-right">Est. Value</th>
          </tr>
        </thead>
        <tbody>
          {ACTION_ORDER.map((action) => {
            const group = grouped[action];
            if (group.length === 0) return null;
            const cfg = ACTION_CONFIG[action];
            return group.map((o, i) => {
              const currentQty = o.current_qty ?? 0;
              const targetQty = o.target_qty ?? 0;
              const change = o.side === "buy" ? o.qty : -o.qty;
              const price = prices?.[o.symbol] ?? 0;
              const dollarImpact = Math.abs(o.qty * price);
              return (
                <tr
                  key={`${action}-${o.symbol}`}
                  className="border-b border-[#2a2a3e]/50"
                >
                  <td className="py-2 pr-4 font-medium text-[#e8e8f0]">
                    {i === 0 && group.length > 1 ? (
                      <span
                        className="mr-2 text-[10px] font-normal uppercase tracking-wider"
                        style={{ color: cfg.color + "80" }}
                      >
                        {cfg.label}
                      </span>
                    ) : null}
                    {o.symbol}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      className="rounded px-1.5 py-0.5 text-xs font-medium"
                      style={{ backgroundColor: cfg.bg, color: cfg.color }}
                    >
                      {cfg.label}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums text-[#8888a0]">
                    {currentQty}
                  </td>
                  <td className="py-2 pr-4 text-center text-[#5a5a70]">→</td>
                  <td className="py-2 pr-4 text-right tabular-nums text-[#e8e8f0]">
                    {targetQty}
                  </td>
                  <td
                    className="py-2 pr-4 text-right tabular-nums font-medium"
                    style={{ color: change > 0 ? "#00d4aa" : "#ff4d6a" }}
                  >
                    {change > 0 ? `+${change}` : change}
                  </td>
                  <td className="py-2 text-right tabular-nums text-[#8888a0]">
                    {price > 0 ? formatUsd(dollarImpact) : "—"}
                  </td>
                </tr>
              );
            });
          })}
        </tbody>
      </table>
    </div>
  );
}

export default memo(function RebalancePanel({
  account,
  strategyId,
  onExecuted,
}: {
  account: number;
  strategyId: string;
  onExecuted?: () => void;
}) {
  const [state, setState] = useState<State>("idle");
  const [preview, setPreview] = useState<RebalancePreview | null>(null);
  const [result, setResult] = useState<{
    submitted: number;
    failed: number;
  } | null>(null);
  const [execError, setExecError] = useState<string | null>(null);

  // Reset state when account or strategy changes
  useEffect(() => {
    setState("idle");
    setPreview(null);
    setResult(null);
    setExecError(null);
  }, [account, strategyId]);

  const handlePreview = async () => {
    setState("previewing");
    setExecError(null);
    try {
      const data = await fetchRebalancePreview(strategyId, account);
      setPreview(data);
      setState("previewed");
    } catch (e) {
      showToast(`Preview failed: ${(e as Error).message}`);
      setState("idle");
    }
  };

  const handleExecute = async () => {
    if (!preview) return;
    if (
      !window.confirm(
        `Execute rebalance for Account ${account}? This will submit ${preview.orders.length} orders to Alpaca.`
      )
    ) {
      return;
    }
    setState("executing");
    try {
      const data = await executeRebalance(strategyId, account);
      setResult({
        submitted: data.orders_submitted,
        failed: data.orders_failed,
      });
      setState("executed");
      if (data.orders_failed > 0) {
        showToast(
          `Rebalance: ${data.orders_failed} of ${data.orders_submitted} orders failed`,
          "warning"
        );
      } else {
        showToast(
          `Rebalance complete: ${data.orders_submitted} orders submitted`,
          "info"
        );
      }
      onExecuted?.();
      setTimeout(() => {
        setState("idle");
        setPreview(null);
        setResult(null);
      }, 5000);
    } catch (e) {
      const msg = (e as Error).message;
      setExecError(msg);
      if (msg.toLowerCase().includes("already in progress")) {
        showToast(msg, "warning");
      } else {
        showToast(msg, "error");
      }
      setState("previewed");
    }
  };

  const handleCancel = () => {
    setState("idle");
    setPreview(null);
  };

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
            Rebalance
          </h2>
          <p className="mt-0.5 text-xs text-[#5a5a70]">{strategyId}</p>
        </div>

        {state === "idle" && (
          <button
            onClick={handlePreview}
            className="rounded-lg bg-[#4d8eff] px-4 py-2 text-sm font-medium text-white hover:bg-[#4d8eff]/80"
          >
            Preview Rebalance
          </button>
        )}
        {state === "previewing" && (
          <span className="text-sm text-[#8888a0] animate-pulse">
            Computing...
          </span>
        )}
        {state === "executed" && result && (
          <span className="text-sm text-[#00d4aa]">
            {result.submitted} orders submitted
            {result.failed > 0 && (
              <span className="text-[#ff4d6a]">
                {" "}
                ({result.failed} failed)
              </span>
            )}
          </span>
        )}
      </div>

      {/* Preview details */}
      {state === "previewed" && preview && (
        <div className="mt-4 space-y-3">
          {/* Summary row */}
          <div className="flex flex-wrap gap-4 text-sm">
            <span className="text-[#8888a0]">
              Portfolio:{" "}
              <span className="text-[#e8e8f0]">
                {formatUsd(preview.portfolio_value)}
              </span>
            </span>
            {ACTION_ORDER.map((action) => {
              const count = preview.orders.filter((o) => o.action === action).length;
              if (count === 0) return null;
              const cfg = ACTION_CONFIG[action];
              return (
                <span key={action} className="text-[#8888a0]">
                  {cfg.label[0] + cfg.label.slice(1).toLowerCase()}:{" "}
                  <span style={{ color: cfg.color }}>{count}</span>
                </span>
              );
            })}
          </div>

          {/* SPY filter warning */}
          {preview.spy_filter_active && (
            <div className="rounded-lg border border-[#ffc04d40] bg-[#ffc04d08] px-3 py-2 text-xs text-[#ffc04d]">
              SPY trend filter active — exposure reduced to{" "}
              {(preview.spy_filter_scalar * 100).toFixed(0)}%
            </div>
          )}

          {/* BTC filter warning */}
          {preview.btc_filter_active && (
            <div className="rounded-lg border border-[#ff4d6a40] bg-[#ff4d6a08] px-3 py-2 text-xs text-[#ff4d6a]">
              BTC trend filter active — {preview.btc_filter_scalar === 0 ? "100% cash (0% exposure)" : `exposure reduced to ${(preview.btc_filter_scalar * 100).toFixed(0)}%`}
            </div>
          )}

          {/* Missing prices warning */}
          {preview.missing_prices && preview.missing_prices.length > 0 && (
            <div className="rounded-lg border border-[#ffc04d40] bg-[#ffc04d08] px-3 py-2 text-xs text-[#ffc04d]">
              Missing prices for: {preview.missing_prices.join(", ")} — these symbols will be excluded from target positions
            </div>
          )}

          {/* Execution error */}
          {execError && (
            <div className="rounded-lg border border-[#ff4d6a40] bg-[#ff4d6a08] px-3 py-2 text-xs text-[#ff4d6a]">
              Execution failed: {execError}
            </div>
          )}

          {/* Orders table */}
          {preview.orders.length === 0 ? (
            <p className="py-4 text-center text-sm text-[#00d4aa]">
              Portfolio already at target — no trades needed
            </p>
          ) : (
            <OrdersTable orders={preview.orders} prices={preview.prices} />
          )}

          {/* Action buttons */}
          <div className="flex justify-end gap-3 pt-1">
            <button
              onClick={handleCancel}
              disabled={state === "executing"}
              className="rounded-lg border border-[#2a2a3e] px-4 py-2 text-sm text-[#8888a0] hover:text-[#e8e8f0]"
            >
              Cancel
            </button>
            {preview.orders.length > 0 && (
              <button
                onClick={handleExecute}
                disabled={state === "executing"}
                className="rounded-lg bg-[#ff4d6a] px-4 py-2 text-sm font-medium text-white hover:bg-[#ff4d6a]/80 disabled:opacity-50"
              >
                {state === "executing"
                  ? "Executing..."
                  : `Confirm & Execute (${preview.orders.length} orders)`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
})
