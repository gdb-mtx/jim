import { memo, useEffect, useState } from "react";
import { fetchOpsFilters } from "../../api";
import type { OpsFiltersResponse, PlausibilityIssue } from "../../types";
import StatusDot from "./StatusDot";

function formatPrice(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  return `$${n.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "never";
  const diff = Date.now() - new Date(iso).getTime();
  if (isNaN(diff) || diff < 0) return "just now";
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default memo(function FilterStatePanel() {
  const [data, setData] = useState<OpsFiltersResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      fetchOpsFilters()
        .then((d) => {
          setData(d);
          setFetchError(null);
        })
        .catch((e) => setFetchError((e as Error).message));
    };
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, []);

  const spyAboveMa =
    data?.spy_price !== undefined &&
    data?.spy_ma200 !== undefined &&
    data.spy_price > data.spy_ma200;
  const btcAboveMa =
    data?.btc_price !== undefined &&
    data?.btc_ma125 !== undefined &&
    data.btc_price > data.btc_ma125;

  const activeIssues: PlausibilityIssue[] = data?.plausibility?.active_issues ?? [];

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Filter State
        </h2>
        {data?.last_checked_relative && (
          <span className="text-xs text-[#8888a0]">
            last check {data.last_checked_relative}
          </span>
        )}
        {fetchError && (
          <span className="text-xs text-[#ff4d6a]">
            Fetch failed — {fetchError}
          </span>
        )}
      </div>

      {!data && !fetchError && (
        <p className="py-6 text-center text-sm text-[#8888a0] animate-pulse">
          Loading...
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-3">
          {/* Plausibility banner — only renders when something is actually off */}
          {activeIssues.length > 0 && (
            <div className="rounded-lg border border-[#ff4d6a60] bg-[#ff4d6a10] px-4 py-3">
              <div className="mb-1.5 flex items-center gap-2">
                <StatusDot tone="red" />
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
                      </span>
                    )}
                    {iss.recent_divergence && iss.last_divergence_at && (
                      <span>
                        {" — "}cache vs live divergence{" "}
                        {((iss.last_divergence_pct ?? 0) * 100).toFixed(1)}%{" "}
                        {timeAgo(iss.last_divergence_at)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Two-column layout: SPY | BTC */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <FilterCard
              label="SPY / 200d MA filter"
              scalar={data.spy_scalar}
              price={data.spy_price}
              ma={data.spy_ma200}
              aboveMa={spyAboveMa}
              lastChange={data.last_spy_change}
              toneAbove="green"
              toneBelow="amber"
              exposureAbove="full exposure (1.0×)"
              exposureBelow="half exposure (0.5×)"
            />
            <FilterCard
              label="BTC / 125d MA filter"
              scalar={data.btc_scalar}
              price={data.btc_price}
              ma={data.btc_ma125}
              aboveMa={btcAboveMa}
              lastChange={data.last_btc_change}
              toneAbove="green"
              toneBelow="red"
              exposureAbove="strategy active (1.0×)"
              exposureBelow="strategy in cash (0.0×)"
            />
          </div>
        </div>
      )}
    </div>
  );
});

function FilterCard({
  label,
  scalar,
  price,
  ma,
  aboveMa,
  lastChange,
  toneAbove,
  toneBelow,
  exposureAbove,
  exposureBelow,
}: {
  label: string;
  scalar: number | undefined;
  price: number | undefined;
  ma: number | undefined;
  aboveMa: boolean | undefined;
  lastChange: string | null | undefined;
  toneAbove: "green" | "amber" | "red";
  toneBelow: "green" | "amber" | "red";
  exposureAbove: string;
  exposureBelow: string;
}) {
  const tone = aboveMa === undefined ? "gray" : aboveMa ? toneAbove : toneBelow;
  const exposure = aboveMa ? exposureAbove : exposureBelow;

  return (
    <div className="rounded-lg border border-[#2a2a3e] bg-[#12121a] p-3">
      <div className="mb-2 flex items-center gap-2">
        <StatusDot tone={tone as "green" | "amber" | "red" | "gray"} size="md" />
        <span className="text-sm font-medium text-[#e8e8f0]">{label}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-[#8888a0]">Price</span>
        <span className="text-right tabular-nums text-[#e8e8f0]">
          {formatPrice(price)}
        </span>
        <span className="text-[#8888a0]">Moving avg</span>
        <span className="text-right tabular-nums text-[#e8e8f0]">
          {formatPrice(ma)}
        </span>
        <span className="text-[#8888a0]">Scalar</span>
        <span className="text-right tabular-nums text-[#e8e8f0]">
          {scalar !== undefined ? scalar.toFixed(2) : "—"}×
        </span>
        <span className="text-[#8888a0]">Last flip</span>
        <span className="text-right text-[#c0c0d0]">
          {timeAgo(lastChange)}
        </span>
      </div>
      <p className="mt-2 text-xs text-[#8a8aa5]">{exposure}</p>
    </div>
  );
}
