import React, { memo, useEffect, useMemo, useState } from "react";
import { fetchOpsEvents } from "../../api";
import type { OpsEvent, OpsEventType, OpsEventsResponse } from "../../types";
import StatusDot, { type StatusTone } from "./StatusDot";

type AccountFilter = "all" | "1" | "2" | "3" | "4";
type TypeFilter = "all" | OpsEventType;

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function toneForEvent(e: OpsEvent): StatusTone {
  if (e.type === "filter_flip") return "purple";
  const details = e.details as Record<string, unknown>;
  const failed = Number(details.orders_failed ?? 0);
  const executeError = details.execute_error;
  if (executeError) return "red";
  if (failed > 0) return "amber";
  if (e.source === "halt_reset") return "blue";
  if (e.source === "scheduled") return "blue";
  return "green";
}

function sourceBadgeClasses(source: string): string {
  switch (source) {
    case "scheduled":
      return "bg-[#7c4dff20] text-[#7c4dff]";
    case "filter_monitor":
      return "bg-[#4d8eff20] text-[#4d8eff]";
    case "halt_reset":
      return "bg-[#ffc04d20] text-[#ffc04d]";
    case "liquidate_account":
      return "bg-[#ff4d6a20] text-[#ff4d6a]";
    case "manual":
    default:
      return "bg-[#8888a020] text-[#8888a0]";
  }
}

export default memo(function EventTimeline() {
  const [data, setData] = useState<OpsEventsResponse | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [accountFilter, setAccountFilter] = useState<AccountFilter>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const load = () => {
      fetchOpsEvents(100, typeFilter === "all" ? undefined : { type: typeFilter })
        .then((d) => {
          setData(d);
          setFetchError(null);
        })
        .catch((e) => setFetchError((e as Error).message));
    };
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
    // Re-fetch on type-filter change; account filter is client-side only.
  }, [typeFilter]);

  const filtered = useMemo(() => {
    if (!data) return [];
    if (accountFilter === "all") return data.events;
    const acctNum = parseInt(accountFilter, 10);
    return data.events.filter(
      (e) => e.account === acctNum || e.account === null,
    );
  }, [data, accountFilter]);

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium tracking-wide text-[#8888a0] uppercase">
          Event Timeline
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Selector<TypeFilter>
            label="Type"
            value={typeFilter}
            onChange={setTypeFilter}
            options={[
              { value: "all", label: "All" },
              { value: "rebalance", label: "Rebalances" },
              { value: "filter_flip", label: "Filter flips" },
            ]}
          />
          <Selector<AccountFilter>
            label="Account"
            value={accountFilter}
            onChange={setAccountFilter}
            options={[
              { value: "all", label: "All" },
              { value: "1", label: "A1" },
              { value: "2", label: "A2" },
              { value: "3", label: "A3" },
              { value: "4", label: "A4" },
            ]}
          />
        </div>
      </div>

      {fetchError && (
        <p className="mb-2 text-xs text-[#ff4d6a]">
          Fetch failed — {fetchError}
        </p>
      )}

      {!data && !fetchError && (
        <p className="py-6 text-center text-sm text-[#8888a0] animate-pulse">
          Loading...
        </p>
      )}

      {data && filtered.length === 0 && (
        <p className="py-6 text-center text-sm text-[#8888a0]">
          No events match the current filter.
        </p>
      )}

      {data && filtered.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2a2a3e] text-left text-xs font-medium tracking-wide text-[#8888a0] uppercase">
                <th className="pb-1.5 pr-3"></th>
                <th className="pb-1.5 pr-3">When</th>
                <th className="pb-1.5 pr-3">Type</th>
                <th className="pb-1.5 pr-3">Source</th>
                <th className="pb-1.5 pr-3">Acct</th>
                <th className="pb-1.5 pr-3">Summary</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => {
                const isExpanded = expanded === i;
                const tone = toneForEvent(e);
                const isDryRun = Boolean(e.is_dry_run);
                return (
                  <React.Fragment key={`${e.timestamp}-${i}`}>
                    <tr
                      className={`border-b border-[#2a2a3e]/50 cursor-pointer hover:bg-[#2a2a3e20] ${
                        isDryRun ? "opacity-60" : ""
                      }`}
                      onClick={() => setExpanded(isExpanded ? null : i)}
                    >
                      <td className="py-2 pr-3">
                        <StatusDot tone={isDryRun ? "gray" : tone} />
                      </td>
                      <td className="py-2 pr-3 tabular-nums text-[#c0c0d0]">
                        {formatTimestamp(e.timestamp)}
                      </td>
                      <td className="py-2 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                            e.type === "filter_flip"
                              ? "bg-[#7c4dff20] text-[#7c4dff]"
                              : "bg-[#2a2a3e] text-[#c0c0d0]"
                          }`}
                        >
                          {e.type}
                        </span>
                        {isDryRun && (
                          <span
                            className="ml-1.5 rounded bg-[#8888a020] px-1.5 py-0.5 text-xs font-medium text-[#8888a0]"
                            title="Run did not persist state — dry-run or debug harness"
                          >
                            DRY RUN
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        <span
                          className={`rounded px-1.5 py-0.5 text-xs font-medium ${sourceBadgeClasses(
                            e.source,
                          )}`}
                        >
                          {e.source}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-[#c0c0d0]">
                        {e.account !== null ? `A${e.account}` : "—"}
                      </td>
                      <td className="py-2 pr-3 text-[#e8e8f0]">{e.summary}</td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={6} className="px-3 pb-3 pt-1">
                          <div className="rounded-lg border border-[#2a2a3e] bg-[#12121a] p-3">
                            <pre className="overflow-x-auto text-xs text-[#c0c0d0]">
                              {JSON.stringify(e.details, null, 2)}
                            </pre>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <p className="mt-3 text-xs text-[#8a8aa5]">
          {filtered.length} shown · {data.total} total
        </p>
      )}
    </div>
  );
});

function Selector<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-[#8888a0]">
      {label}
      <select
        className="rounded border border-[#2a2a3e] bg-[#12121a] px-2 py-1 text-[#e8e8f0]"
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
