import { memo, useCallback, useEffect, useState } from "react";
import { fetchDataFreshness, refreshCache } from "../api";
import type { DataFreshnessResponse } from "../types";
import Tooltip from "./Tooltip";

function formatAge(age_h: number | null): string {
  if (age_h === null) return "missing";
  if (age_h < 1) return `${Math.round(age_h * 60)}m`;
  if (age_h < 48) return `${age_h.toFixed(1)}h`;
  return `${Math.round(age_h / 24)}d`;
}

export default memo(function DataFreshnessPill() {
  const [data, setData] = useState<DataFreshnessResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const poll = useCallback(async () => {
    try {
      const d = await fetchDataFreshness();
      setData(d);
    } catch {}
  }, []);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [poll]);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshCache();
    } finally {
      await poll();
      setRefreshing(false);
    }
  }, [poll]);

  if (!data) return null;

  const stale = data.any_stale;
  const dotColor = refreshing
    ? "bg-[#ffc04d]"
    : stale
      ? "bg-[#ff4d6a]"
      : "bg-[#00d4aa]";
  const borderColor = stale ? "border-[#ff4d6a40]" : "border-[#2a2a3e]";
  const bgColor = stale ? "bg-[#ff4d6a08]" : "bg-[#1a1a2e]";

  const tooltip = data.caches
    .map((c) => {
      const flags: string[] = [];
      if (c.mtime_stale) flags.push("MTIME-STALE");
      if (c.content_stale) flags.push("CONTENT-STALE");
      const tail = flags.length ? ` (${flags.join(", ")})` : "";
      const bar = c.latest_bar ? ` latest: ${c.latest_bar}` : "";
      return `${c.name}: ${formatAge(c.age_h)}${bar}${tail}`;
    })
    .join("\n");

  return (
    <Tooltip text={tooltip}>
      <div
        className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 ${borderColor} ${bgColor}`}
      >
        <span
          className={`h-2 w-2 rounded-full ${dotColor}${refreshing ? " animate-pulse" : ""}`}
        />
        <span className="text-sm text-[#8888a0]">
          Data{" "}
          <span className="text-[#e8e8f0]">
            {refreshing ? "refreshing…" : stale ? "stale" : "fresh"}
          </span>
        </span>
        {stale && !refreshing && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleRefresh();
            }}
            className="ml-0.5 text-sm text-[#8888a0] hover:text-[#e8e8f0] transition-colors"
            title="Force-refresh all data caches"
          >
            ↻
          </button>
        )}
      </div>
    </Tooltip>
  );
});
