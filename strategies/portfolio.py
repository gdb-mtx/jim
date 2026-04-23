"""Re-export shim — split into portfolio_config (live) + portfolio_backtest (research).

See DEPLOYMENT_PLAN.md §Phase 0. This shim preserves the existing import path
so callers can migrate at their own pace; new code should import directly from
the split modules.

Live-path code (execution/, scripts/filter_check.py, api/routes/) should
import from `strategies.portfolio_config` only. Research code may import from
either module — `portfolio_backtest` re-uses `portfolio_config` internally.
"""

from strategies.portfolio_config import (
    PORTFOLIOS,
    ETF_STRATEGIES,
    STOCK_STRATEGIES,
    CRYPTO_STRATEGIES,
    compute_spy_trend_filter,
    compute_btc_trend_filter,
)
from strategies.portfolio_backtest import (
    apply_vol_scaling,
    _generate_strategy_returns,
    run_portfolio,
    run_equity_core,
    run_combined_portfolio,
    LIVE_ACCOUNT_STRATEGIES,
    EQUITY_CORE_STRATEGIES,
)

__all__ = [
    "PORTFOLIOS",
    "ETF_STRATEGIES",
    "STOCK_STRATEGIES",
    "CRYPTO_STRATEGIES",
    "compute_spy_trend_filter",
    "compute_btc_trend_filter",
    "apply_vol_scaling",
    "run_portfolio",
    "run_equity_core",
    "run_combined_portfolio",
    "LIVE_ACCOUNT_STRATEGIES",
    "EQUITY_CORE_STRATEGIES",
]
