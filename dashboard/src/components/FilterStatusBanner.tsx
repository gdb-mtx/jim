import { memo, useEffect, useState } from "react";
import { fetchFilterStatus } from "../api";
import type { FilterStatusResponse } from "../types";

type AccountView = 0 | 1 | 2 | 3 | 4;

function formatPrice(n: number, prefix = "$") {
  return `${prefix}${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export default memo(function FilterStatusBanner({
  account,
}: {
  account: AccountView;
}) {
  const [filters, setFilters] = useState<FilterStatusResponse | null>(null);

  useEffect(() => {
    fetchFilterStatus().then(setFilters).catch(() => {});
    const interval = setInterval(() => {
      fetchFilterStatus().then(setFilters).catch(() => {});
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [account]);

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
            <span className="tabular-nums">{formatPrice(btc.ma_200)}</span>
            {" MA "}
            {btc.above_ma ? (
              <span className="text-[#00d4aa]">— strategy active</span>
            ) : (
              <span className="text-[#ff4d6a]">— strategy in cash</span>
            )}
          </span>
        </div>
      )}
    </div>
  );
})
