"""Backtest endpoints — run backtests and return equity curves."""

from fastapi import APIRouter, Query
from data.pipeline import download_prices, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from strategies.trend_following import TimeSeriesMomentum, MultiTimeframeMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum
from strategies.multi_asset_trend import MultiAssetTrend
from strategies.low_volatility import LowVolatility
from strategies.mean_reversion import ShortTermReversal
from strategies.portfolio import PORTFOLIOS, run_portfolio, run_combined_portfolio
from backtesting.metrics import full_report
import pandas as pd

router = APIRouter()

# ETF-based strategies
ETF_STRATEGIES = {
    "ts_momentum": TimeSeriesMomentum,
    "multi_tf_momentum": MultiTimeframeMomentum,
    "cross_sectional": CrossSectionalMomentum,
    "dual_momentum": DualMomentum,
    "multi_asset_trend_solo": MultiAssetTrend,
}

# Stock-based strategies (use S&P 500 universe)
STOCK_STRATEGIES = {
    "stock_momentum": StockMomentum,
    "low_volatility_solo": LowVolatility,
    "short_term_reversal_solo": ShortTermReversal,
}

STRATEGIES = {**ETF_STRATEGIES, **STOCK_STRATEGIES}
ALL_STRATEGY_IDS = {**STRATEGIES, **{pid: None for pid in PORTFOLIOS}, "combined_3account": None}

# Expanded ETF universe + SHY (cash proxy for dual momentum)
DEFAULT_SYMBOLS = EXPANDED_UNIVERSE + ["SHY"]


def _run_strategy(strategy_id: str, start: str, end: str | None = None):
    """Run a strategy and return (strategy_name, returns Series)."""
    if strategy_id in STOCK_STRATEGIES:
        # Stock strategies use S&P 500 universe
        prices = download_sp500_prices(start=start)
        strategy = STOCK_STRATEGIES[strategy_id]()
        # Inject VIX for regime filter
        vix = download_vix()
        strategy.set_vix(vix)
        returns = strategy.generate_returns(prices)
    else:
        # ETF strategies use the smaller universe
        prices = download_prices(DEFAULT_SYMBOLS, start=start, end=end)
        strategy = ETF_STRATEGIES[strategy_id]()
        returns = strategy.generate_returns(prices)

    return strategy, returns


@router.get("/run/{strategy_id}")
async def run_backtest(
    strategy_id: str,
    start: str = Query(default="2010-01-01"),
    end: str = Query(default=None),
):
    """Run a backtest and return equity curve + metrics."""
    if strategy_id not in ALL_STRATEGY_IDS:
        return {"error": f"Unknown strategy: {strategy_id}"}

    # Combined 3-account, portfolio, or individual strategy
    if strategy_id == "combined_3account":
        strategy_name, returns = run_combined_portfolio(start, end)
    elif strategy_id in PORTFOLIOS:
        strategy_name, returns = run_portfolio(strategy_id, start, end)
    else:
        strategy, returns = _run_strategy(strategy_id, start, end)
        strategy_name = strategy.name

        # Trim warmup period: find first date with non-zero returns
        non_zero = returns[returns != 0]
        if len(non_zero) > 0:
            returns = returns.loc[non_zero.index[0]:]

    # Build equity curve (rebased to $10k from active start)
    equity = (1 + returns).cumprod() * 10000
    equity_data = [
        {"time": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
        for d, v in zip(equity.index, equity.values)
    ]

    report = full_report(returns, name=strategy_name)

    # SPY buy-and-hold benchmark for the same active period
    spy_prices = download_prices(["SPY"], start=start, end=end)
    spy_returns = spy_prices.pct_change().dropna().squeeze()
    first_date = returns.index[0]
    last_date = returns.index[-1]
    spy_aligned = spy_returns.loc[first_date:last_date]
    spy_equity = (1 + spy_aligned).cumprod() * 10000
    spy_data = [
        {"time": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
        for d, v in zip(spy_equity.index, spy_equity.values)
    ]

    return {
        "strategy": strategy_name,
        "equity_curve": equity_data,
        "spy_curve": spy_data,
        "metrics": report,
    }


@router.get("/equity/{strategy_id}")
async def get_equity_curve(
    strategy_id: str,
    start: str = Query(default="2010-01-01"),
):
    """Get just the equity curve data for charting."""
    if strategy_id not in STRATEGIES:
        return {"error": f"Unknown strategy: {strategy_id}"}

    strategy, returns = _run_strategy(strategy_id, start)

    # Trim warmup period
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    equity = (1 + returns).cumprod() * 10000

    return [
        {"time": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
        for d, v in zip(equity.index, equity.values)
    ]
