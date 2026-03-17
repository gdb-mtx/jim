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
  spy_return_pct: number;
  alpha_pct: number;
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

// Risk / Circuit Breaker types
export interface AccountRiskStatus {
  account: number;
  label: string;
  halted: boolean;
  equity_peak: number;
  halted_strategies: string[];
  strategy_peaks?: Record<string, number>;
  error?: string;
}

export interface RiskStatusResponse {
  any_halted: boolean;
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
  ma_200: number;
  above_ma: boolean;
  filter_scalar: number;
  error?: string;
}

export interface FilterStatusResponse {
  spy: FilterInfo;
  btc: FilterInfo;
}
