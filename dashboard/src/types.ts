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

export interface EquityHistoryResponse {
  equity_curve: EquityPoint[];
  per_account?: Record<string, EquityPoint[]>;
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
