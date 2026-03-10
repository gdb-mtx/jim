import { useState } from "react";
import type { StrategyMetrics } from "../types";
import {
  STRATEGY_METADATA,
  SECTION_CONFIG,
  CATEGORY_ORDER,
  type StrategyCategory,
  type StrategyMeta,
} from "../strategyMetadata";
import Tooltip from "./Tooltip";

interface Props {
  strategies: StrategyMetrics[];
  selected: string | null;
  onSelect: (id: string) => void;
}

// ── Chevron icon (no dependency) ─────────────────────────────────────
function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-4 w-4 text-[#8888a0] transition-transform duration-200 ${
        expanded ? "rotate-180" : ""
      }`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

// ── Single strategy card ─────────────────────────────────────────────
function StrategyCard({
  s,
  meta,
  isSelected,
  onSelect,
}: {
  s: StrategyMetrics;
  meta: StrategyMeta | undefined;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const id = s.id ?? s.name;
  const isLive = meta?.category === "live";
  const isCombined = id === "combined_3account";
  const isSoloWrapper = meta?.category === "solo_wrapper";
  const returnColor =
    s.annualized_return >= 0 ? "text-[#00d4aa]" : "text-[#ff4d6a]";

  return (
    <button
      onClick={onSelect}
      className={`w-full rounded-lg border p-3 text-left transition-all ${
        isCombined ? "border-l-2 border-l-[#7c4dff] " : ""
      }${
        isSelected
          ? "border-[#4d8eff] bg-[#4d8eff10]"
          : "border-[#2a2a3e] bg-[#12121a] hover:border-[#3a3a4e]"
      }${isSoloWrapper ? " opacity-70" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-1.5 pt-0.5">
          {isLive && (
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#00d4aa]" />
          )}
          {meta ? (
            <Tooltip text={meta.description}>
              <span className="text-sm font-medium leading-tight text-[#e8e8f0]">
                {s.name}
              </span>
            </Tooltip>
          ) : (
            <span className="text-sm font-medium leading-tight text-[#e8e8f0]">
              {s.name}
            </span>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
          {isCombined && (
            <span className="rounded bg-[#7c4dff20] px-1.5 py-0.5 text-xs font-medium text-[#7c4dff]">
              All
            </span>
          )}
          {meta?.account && (
            <span className="rounded bg-[#4d8eff20] px-1.5 py-0.5 text-xs font-medium text-[#4d8eff]">
              Acct {meta.account}
            </span>
          )}
          <span
            className={`rounded-full px-2 py-0.5 text-xs ${
              s.validation_passed
                ? "bg-[#00d4aa20] text-[#00d4aa]"
                : "bg-[#ffc04d20] text-[#ffc04d]"
            }`}
          >
            {s.validation_passed ? "Validated" : "Testing"}
          </span>
        </div>
      </div>
      <div className="mt-2 flex gap-4 text-xs text-[#8888a0]">
        <span>
          Return:{" "}
          <span className={returnColor}>
            {(s.annualized_return * 100).toFixed(1)}%
          </span>
        </span>
        <span>Sharpe: {s.sharpe_ratio.toFixed(2)}</span>
        <span>
          MaxDD:{" "}
          <span className="text-[#ff4d6a]">
            {(s.max_drawdown * 100).toFixed(1)}%
          </span>
        </span>
      </div>
    </button>
  );
}

// ── Collapsible section ──────────────────────────────────────────────
function StrategySection({
  category,
  strategies,
  selected,
  onSelect,
}: {
  category: StrategyCategory;
  strategies: StrategyMetrics[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const config = SECTION_CONFIG[category];
  const [expanded, setExpanded] = useState(config.defaultExpanded);

  if (strategies.length === 0) return null;

  const headerColor =
    category === "live" ? "text-[#00d4aa]" : "text-[#8888a0]";

  return (
    <div>
      <button
        onClick={() => config.collapsible && setExpanded(!expanded)}
        className={`flex w-full items-center justify-between py-2 ${
          config.collapsible ? "cursor-pointer" : "cursor-default"
        }`}
      >
        <span
          className={`text-xs font-medium tracking-wide uppercase ${headerColor}`}
        >
          {config.title}{" "}
          <span className="text-[#5a5a70]">({strategies.length})</span>
        </span>
        {config.collapsible && <Chevron expanded={expanded} />}
      </button>
      {expanded && (
        <div className="space-y-2 pb-3">
          {strategies.map((s) => {
            const id = s.id ?? s.name;
            const meta = STRATEGY_METADATA[id];
            return (
              <StrategyCard
                key={id}
                s={s}
                meta={meta}
                isSelected={selected === id}
                onSelect={() => onSelect(id)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────
export default function StrategyPanel({
  strategies,
  selected,
  onSelect,
}: Props) {
  // Group strategies by category
  const grouped: Record<StrategyCategory, StrategyMetrics[]> = {
    live: [],
    portfolio: [],
    building_block: [],
    solo_wrapper: [],
  };

  for (const s of strategies) {
    const id = s.id ?? s.name;
    const meta = STRATEGY_METADATA[id];
    const category = meta?.category ?? "building_block";
    grouped[category].push(s);
  }

  // Sort within each group by sortOrder
  for (const cat of CATEGORY_ORDER) {
    grouped[cat].sort((a, b) => {
      const idA = a.id ?? a.name;
      const idB = b.id ?? b.name;
      const orderA = STRATEGY_METADATA[idA]?.sortOrder ?? 99;
      const orderB = STRATEGY_METADATA[idB]?.sortOrder ?? 99;
      return orderA - orderB;
    });
  }

  return (
    <div className="rounded-xl border border-[#2a2a3e] bg-[#1a1a2e] p-4">
      <h2 className="mb-1 text-sm font-medium tracking-wide text-[#8888a0] uppercase">
        Strategies
      </h2>
      <div className="divide-y divide-[#2a2a3e]">
        {CATEGORY_ORDER.map((cat) => (
          <StrategySection
            key={cat}
            category={cat}
            strategies={grouped[cat]}
            selected={selected}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
