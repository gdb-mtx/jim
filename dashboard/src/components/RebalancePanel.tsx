import { memo, useState } from "react";
import { fetchRebalancePreview, executeRebalance } from "../api";
import type { RebalancePreview } from "../types";
import { showToast } from "./Toast";

type State = "idle" | "previewing" | "previewed" | "executing" | "executed";

function formatUsd(n: number) {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  });
}

export default memo(function RebalancePanel({
  account,
  strategyId,
}: {
  account: number;
  strategyId: string;
}) {
  const [state, setState] = useState<State>("idle");
  const [preview, setPreview] = useState<RebalancePreview | null>(null);
  const [result, setResult] = useState<{
    submitted: number;
    failed: number;
  } | null>(null);

  const handlePreview = async () => {
    setState("previewing");
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
      setTimeout(() => {
        setState("idle");
        setPreview(null);
        setResult(null);
      }, 5000);
    } catch (e) {
      const msg = (e as Error).message;
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
            <span className="text-[#8888a0]">
              Buys:{" "}
              <span className="text-[#00d4aa]">{preview.num_buys}</span>
            </span>
            <span className="text-[#8888a0]">
              Sells:{" "}
              <span className="text-[#ff4d6a]">{preview.num_sells}</span>
            </span>
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

          {/* Orders table */}
          {preview.orders.length === 0 ? (
            <p className="py-4 text-center text-sm text-[#00d4aa]">
              Portfolio already at target — no trades needed
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                    <th className="pb-2 pr-4">Symbol</th>
                    <th className="pb-2 pr-4">Side</th>
                    <th className="pb-2 pr-4 text-right">Qty</th>
                    <th className="pb-2 text-right">Type</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.orders.map((o, i) => (
                    <tr
                      key={i}
                      className="border-b border-[#2a2a3e]/50"
                    >
                      <td className="py-2 pr-4 font-medium text-[#e8e8f0]">
                        {o.symbol}
                      </td>
                      <td className="py-2 pr-4">
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
                      <td className="py-2 pr-4 text-right tabular-nums text-[#e8e8f0]">
                        {o.qty}
                      </td>
                      <td className="py-2 text-right text-[#8888a0]">
                        {o.type}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
