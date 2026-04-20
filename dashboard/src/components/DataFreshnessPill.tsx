import { memo, useEffect, useState } from "react";
import { fetchDataFreshness } from "../api";
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

  useEffect(() => {
    let cancelled = false;
    function refresh() {
      fetchDataFreshness()
        .then((d) => {
          if (!cancelled) setData(d);
        })
        .catch(() => {});
    }
    refresh();
    const interval = setInterval(refresh, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (!data) return null;

  const stale = data.any_stale;
  const dotColor = stale ? "bg-[#ff4d6a]" : "bg-[#00d4aa]";
  const borderColor = stale ? "border-[#ff4d6a40]" : "border-[#2a2a3e]";
  const bgColor = stale ? "bg-[#ff4d6a08]" : "bg-[#1a1a2e]";

  const tooltip = data.caches
    .map(
      (c) =>
        `${c.name}: ${formatAge(c.age_h)}${c.stale ? " (STALE)" : ""}`
    )
    .join("\n");

  return (
    <Tooltip text={tooltip}>
      <div
        className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 ${borderColor} ${bgColor}`}
      >
        <span className={`h-2 w-2 rounded-full ${dotColor}`} />
        <span className="text-sm text-[#8888a0]">
          Data{" "}
          <span className="text-[#e8e8f0]">
            {stale ? "stale" : "fresh"}
          </span>
        </span>
      </div>
    </Tooltip>
  );
});
