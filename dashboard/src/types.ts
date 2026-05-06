export interface EquityPoint {
  time: string;
  value: number;
}

export interface StrategyMetrics {
  name: string;
  id?: string;
  status: string;
  annualized_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  validation_passed: boolean;
}

export interface SliceMetrics {
  n_days: number;
  period_start: string;
  period_end: string;
  cagr: number;
  max_drawdown: number;
  calmar_ratio: number;
  sharpe_ratio: number;
}

export interface BacktestResult {
  strategy: string;
  equity_curve: EquityPoint[];
  spy_curve?: EquityPoint[];
  metrics: {
    name: string;
    annualized_return: number;
    sharpe_ratio: number;
    max_drawdown: number;
    calmar_ratio: number;
    win_rate: number;
    profit_factor: number;
    kelly_criterion: number;
    kelly_half: number;
    kelly_quarter: number;
  };
  is_metrics?: SliceMetrics | null;
  oos_metrics?: SliceMetrics | null;
  oos_start?: string | null;
  train_end?: string;
}

export interface AccountInfo {
  account: number;
  name: string;
  strategy: string;
  label: string;
}

export interface PortfolioSummary {
  account_id: string;
  account_number: number;
  account_label: string;
  default_strategy: string;
  status: string;
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  last_equity: number;
  daily_pnl: number;
  is_paper: boolean;
  positions_count: number;
  total_unrealized_pl: number;
  market_open: boolean;
}

export interface Position {
  symbol: string;
  qty: number;
  side: string;
  market_value: number;
  cost_basis: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  change_today: number;
  non_tradeable?: boolean;
}

export interface Order {
  order_id: string;
  symbol: string;
  qty: string;
  filled_qty: string;
  side: string;
  type: string;
  status: string;
  submitted_at: string;
  filled_at: string | null;
  filled_avg_price: number | null;
}

export interface PerformanceEntry {
  account: number;
  label: string;
  return_pct: number;
  spy_return_pct: number | null;
  alpha_pct: number | null;
}

export interface EquityHistoryResponse {
  equity_curve: EquityPoint[];
  per_account?: Record<string, EquityPoint[]>;
  spy_benchmark?: EquityPoint[];
  performance?: PerformanceEntry[];
  days: number;
}

export interface CorrelationReport {
  matrix: Record<string, number> | null;
  rolling: Record<string, EquityPoint[]>;
  alert_pairs: string[];
  data_days: number;
  confidence: "low" | "medium" | "high" | null;
  alert_threshold: number;
  backtest_expected: Record<string, number>;
}

// Risk / drawdown types. Schema reshape 2026-04-21 (AUDIT_MONTH2 C5):
//   - halted: catastrophe halt at -35% (manual reset)
//   - alert_active: -10% drawdown alert (non-blocking)
//   - strategy-level fields removed (was dead code per R3)
export interface AccountRiskStatus {
  account: number;
  label: string;
  halted: boolean;
  alert_active: boolean;
  equity_peak: number;
  error?: string;
}

export interface RiskStatusResponse {
  any_halted: boolean;
  any_alert: boolean;
  thresholds: { alert: number; halt: number };
  accounts: Record<string, AccountRiskStatus>;
}

// Rebalance types
export interface RebalanceOrder {
  symbol: string;
  qty: number;
  side: "buy" | "sell";
  type: string;
  current_qty?: number;
  target_qty?: number;
  action?: "new" | "increase" | "decrease" | "exit";
}

export interface RebalancePreview {
  account: number;
  strategy_id: string;
  portfolio_value: number;
  target_weights: Record<string, number>;
  target_positions: Record<string, number>;
  current_positions: Record<string, number>;
  orders: RebalanceOrder[];
  num_buys: number;
  num_sells: number;
  risk_check: Record<string, unknown>;
  spy_filter_active: boolean;
  spy_filter_scalar: number;
  btc_filter_active: boolean;
  btc_filter_scalar: number;
  prices?: Record<string, number>;
  missing_prices?: string[];
  price_error?: boolean;
}

export interface RebalanceExecuteResult {
  account: number;
  strategy_id: string;
  portfolio_value: number;
  orders_submitted: number;
  orders_failed: number;
  orders: Record<string, unknown>[];
  spy_filter_active: boolean;
  spy_filter_scalar: number;
  btc_filter_active: boolean;
  btc_filter_scalar: number;
  message?: string;
}

export interface RebalanceHistoryOrder {
  symbol: string;
  side: string;
  qty: number;
  status: string;
  error: string | null;
}

export interface RebalanceHistoryEntry {
  timestamp: string;
  account: number;
  strategy_id: string;
  source: string;
  portfolio_value: number;
  orders_submitted: number;
  orders_failed: number;
  spy_filter_active: boolean;
  spy_filter_scalar: number;
  btc_filter_active?: boolean;
  btc_filter_scalar?: number;
  orders: RebalanceHistoryOrder[];
}

// Regime filter status
export interface FilterInfo {
  price: number;
  ma_200?: number; // SPY uses 200d MA
  ma_125?: number; // BTC uses 125d MA (robust-opt 2026-04-18, from 200d → 125d)
  above_ma: boolean;
  filter_scalar: number;
  error?: string;
}

export interface FilterStatusResponse {
  spy: FilterInfo;
  btc: FilterInfo;
}

export interface DataCacheInfo {
  name: string;
  file: string;
  age_h: number | null;
  threshold_h: number;
  stale: boolean;
  missing: boolean;
}

export interface DataFreshnessResponse {
  any_stale: boolean;
  caches: DataCacheInfo[];
}

export interface FilterMonitorState {
  spy_scalar: number;
  btc_scalar: number;
  spy_price: number;
  spy_ma200: number;
  btc_price: number;
  btc_ma125: number;
  last_checked: string;
  last_spy_flip: string | null;
  last_btc_flip: string | null;
  recent_auto_rebalances: Array<{
    timestamp: string;
    account: number;
    strategy_id: string;
    orders_submitted: number;
    source: string;
  }>;
}

export interface PlausibilityIssue {
  ticker: string;
  unresolved_failure: boolean;
  recent_divergence: boolean;
  last_success_at?: string;
  last_success_n_obs?: number;
  last_failure_at?: string;
  last_failure_reason?: string;
  last_failure_obs_min?: number;
  last_failure_obs_max?: number;
  last_failure_n_obs?: number;
  last_divergence_at?: string;
  last_divergence_cached?: number;
  last_divergence_live?: number;
  last_divergence_pct?: number;
  last_divergence_threshold_pct?: number;
}

export interface PlausibilityState {
  state: Record<string, Omit<PlausibilityIssue, "ticker" | "unresolved_failure" | "recent_divergence">>;
  active_issues: PlausibilityIssue[];
  has_active: boolean;
}

// -----------------------------------------------------------------------
// Ops dashboard types — automation surface shown on the /ops tab.
// Backend: api/routes/ops.py
// -----------------------------------------------------------------------

export interface OpsSchedulerJob {
  id: string;
  label?: string;        // launchd plist label (scheduled_rebalance jobs)
  name: string;
  next_run_time: string | null;
  last_started: string | null;
  last_finished: string | null;
  last_status: "running" | "success" | "partial" | "skipped" | "failed" | null;
  error: string | null;
}

export interface OpsLaunchdFlip {
  filter: string;       // "spy" | "btc"
  from: number;
  to: number;
  direction: string;    // "BULLISH" | "DEFENSIVE" | "CASH"
}

export interface OpsLaunchdAccount {
  account: number;
  status: string;       // "executed" | "dry_run" | "no_trades" | "halted" | ...
  orders: number;
}

export interface OpsLaunchdEntry {
  label: string;        // plist identifier
  source: string;       // source tag the plist emits (e.g. "launchd-crypto")
  expected_scope: string;
  last_run: string | null;       // ISO (naive local-time) of the start line
  last_run_relative: string | null;
  next_run: string | null;       // ISO UTC of the next expected fire (computed from plist schedule)
  outcome: "no_change" | "flip" | "first_run" | "error" | null;
  scope: string | null;
  flips: OpsLaunchdFlip[];
  accounts: OpsLaunchdAccount[];
}

export interface OpsSchedulerResponse {
  // Daily rebalance jobs fired by launchd. Last-run derived from
  // rebalance_log.jsonl. Replaces the in-process APScheduler block,
  // retired 2026-05-05 after long-uptime drift.
  scheduled_rebalance: {
    jobs: OpsSchedulerJob[];
  };
  launchd: OpsLaunchdEntry[];
  launchd_error?: string;
}

export interface OpsFiltersResponse {
  spy_scalar?: number;
  btc_scalar?: number;
  spy_price?: number;
  spy_ma200?: number;
  btc_price?: number;
  btc_ma125?: number;
  last_checked?: string;
  last_checked_relative: string | null;
  last_spy_flip?: string | null;
  last_btc_flip?: string | null;
  plausibility: PlausibilityState;
}

export interface OpsValidationAccount {
  account: number;
  name: string;
  status: "pass" | "marginal" | "fail" | "retired" | "unvalidated";
  last_run: string;
  expires: string;
  days_remaining: number | null;
  report_path: string | null;
  oos_cagr?: number;
  oos_maxdd?: number;
  oos_calmar?: number;
  oos_is_cagr_ratio?: number;
  reason?: string;
  retired_at?: string;
  retired_reason?: string;
}

export interface OpsValidationResponse {
  accounts: OpsValidationAccount[];
}

export type OpsEventType = "rebalance" | "filter_flip";

export interface OpsEvent {
  timestamp: string;
  type: OpsEventType;
  source: string;
  account: number | null;
  summary: string;
  // True for filter_flip events whose underlying filter_check.py run
  // was a --dry-run (or the 2026-04-22 sandbox harness that produced
  // `blocked_by_harness` status). Always false for rebalance events.
  // Frontend renders these dimmed with a "DRY RUN" badge so phantom
  // flips don't compete visually with real production flips.
  is_dry_run?: boolean;
  details: Record<string, unknown>;
}

export interface OpsEventsResponse {
  events: OpsEvent[];
  total: number;
}
