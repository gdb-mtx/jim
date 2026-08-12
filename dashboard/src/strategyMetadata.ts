export type StrategyCategory = "live" | "portfolio" | "building_block" | "solo_wrapper";

export interface StrategyMeta {
  category: StrategyCategory;
  description: string;
  account?: number;
  accountLabel?: string;
  sortOrder: number;
}

export const STRATEGY_METADATA: Record<string, StrategyMeta> = {
  // ── Live Accounts ──────────────────────────────────────────────────
  combined_3account: {
    category: "live",
    description: "A1 (SM) + A2 (Trend+LowVol) — the live book after A3/A4 retirements (2026-07)",
    sortOrder: 0,
  },
  sm_filtered: {
    category: "live",
    description:
      "Top 15 S&P 500 stocks by 12-month momentum, halves exposure when SPY < 200d MA",
    account: 1,
    accountLabel: "Jim 0.1",
    sortOrder: 1,
  },
  trend_lowvol: {
    category: "live",
    description: "30% Multi-Asset Trend + 70% Low Volatility, volatility-scaled",
    account: 2,
    accountLabel: "Jim 0.2",
    sortOrder: 2,
  },
  crypto_momentum_filtered: {
    category: "building_block",
    description: "RETIRED 2026-07-13 — was: top 2 cryptos by 21d momentum, BTC 125d SMA filter + vol-scaling (edge decay + bug-era drag; HISTORY.md)",
    account: 4,
    accountLabel: "Jim 0.4 (retired)",
    sortOrder: 3,
  },

  // ── Portfolio Blends ───────────────────────────────────────────────
  blend_filtered: {
    category: "portfolio",
    description: "60% SM + 20% CS + 20% DM with SPY trend filter",
    sortOrder: 0,
  },
  blend_no_filter: {
    category: "portfolio",
    description: "60% SM + 20% CS + 20% DM without filter",
    sortOrder: 1,
  },

  // ── Building Blocks (individual strategies) ────────────────────────
  reversal_blend: {
    category: "building_block",
    description: "Retired 2026-04-21 — was Jim 0.3 (60% Short-Term Reversal + 40% Stock Momentum). Too correlated to A1 (0.88 OOS) to earn its weight.",
    sortOrder: 0,
  },
  stock_momentum: {
    category: "building_block",
    description: "Top 15 S&P 500 stocks ranked by 12-month return, ex last month",
    sortOrder: 1,
  },
  multi_asset_trend_solo: {
    category: "building_block",
    description: "Trend-following across 18 ETFs, goes to cash in downtrends",
    sortOrder: 2,
  },
  low_volatility_solo: {
    category: "building_block",
    description: "Lowest-beta S&P 500 stocks, defensive factor",
    sortOrder: 3,
  },
  short_term_reversal_solo: {
    category: "building_block",
    description: "Buys recent losers, sells recent winners, 5-day holding period",
    sortOrder: 4,
  },
  cross_sectional: {
    category: "building_block",
    description: "Rank ETFs by relative momentum, long top / short bottom",
    sortOrder: 5,
  },
  dual_momentum: {
    category: "building_block",
    description: "Antonacci: switches between stocks, bonds, and cash",
    sortOrder: 6,
  },
  ts_momentum: {
    category: "building_block",
    description: "Long/flat each ETF based on its own 12-month trend",
    sortOrder: 7,
  },
  multi_tf_momentum: {
    category: "building_block",
    description: "Blends 1/3/6/12 month lookback windows",
    sortOrder: 8,
  },
  crypto_momentum: {
    category: "building_block",
    description: "21-day crypto momentum rotation, top 2 of 9 coins, equal weight",
    sortOrder: 9,
  },

  // ── Solo Wrappers (portfolio-wrapped, some with SPY filter) ────────
  multi_asset_trend: {
    category: "solo_wrapper",
    description: "Multi-Asset Trend via portfolio system (no SPY filter)",
    sortOrder: 0,
  },
  low_volatility: {
    category: "solo_wrapper",
    description: "Low Volatility with SPY filter applied",
    sortOrder: 1,
  },
  short_term_reversal: {
    category: "solo_wrapper",
    description: "Short-Term Reversal with SPY filter applied",
    sortOrder: 2,
  },
};

export const SECTION_CONFIG: Record<
  StrategyCategory,
  { title: string; defaultExpanded: boolean; collapsible: boolean }
> = {
  live: { title: "Live Accounts", defaultExpanded: true, collapsible: false },
  portfolio: { title: "Portfolio Blends", defaultExpanded: false, collapsible: true },
  building_block: { title: "Building Blocks", defaultExpanded: false, collapsible: true },
  solo_wrapper: { title: "Solo + Filter", defaultExpanded: false, collapsible: true },
};

export const CATEGORY_ORDER: StrategyCategory[] = [
  "live",
  "portfolio",
  "building_block",
  "solo_wrapper",
];
