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

export interface PortfolioSummary {
  total_value: number;
  cash: number;
  positions: unknown[];
  daily_pnl: number;
  total_pnl: number;
  drawdown: number;
  status: string;
}
