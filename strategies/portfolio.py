"""
Combined Portfolio Strategy with SPY Trend Filter.

Blends multiple strategy return streams and applies a market regime
overlay using SPY's 200-day moving average.

The SPY trend filter is the single most effective risk overlay we've found:
- When SPY > 200-day MA: full exposure (bull market)
- When SPY < 200-day MA: reduce exposure by 50% (bear market)

This simple rule cuts max drawdown nearly in half while actually improving
returns (avoiding the worst of crashes more than compensates for the drag
during whipsaws).

Academic basis:
- Faber (2007): "A Quantitative Approach to Tactical Asset Allocation"
- 200-day MA is the most studied trend filter in finance
"""

import numpy as np
import pandas as pd
from data.pipeline import download_prices, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from strategies.trend_following import TimeSeriesMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum


# Preset portfolio configurations
PORTFOLIOS = {
    "sm_filtered": {
        "name": "Stock Momentum + SPY Filter",
        "weights": {"stock_momentum": 1.0},
        "spy_filter": True,
    },
    "blend_filtered": {
        "name": "Blended Portfolio + SPY Filter",
        "weights": {
            "stock_momentum": 0.60,
            "cross_sectional": 0.20,
            "dual_momentum": 0.20,
        },
        "spy_filter": True,
    },
    "blend_no_filter": {
        "name": "Blended Portfolio",
        "weights": {
            "stock_momentum": 0.60,
            "cross_sectional": 0.20,
            "dual_momentum": 0.20,
        },
        "spy_filter": False,
    },
}

# Strategy classes keyed by ID
ETF_STRATEGIES = {
    "ts_momentum": TimeSeriesMomentum,
    "cross_sectional": CrossSectionalMomentum,
    "dual_momentum": DualMomentum,
}

STOCK_STRATEGIES = {
    "stock_momentum": StockMomentum,
}


def _generate_strategy_returns(
    strategy_id: str,
    etf_prices: pd.DataFrame,
    stock_prices: pd.DataFrame | None = None,
    vix: pd.Series | None = None,
) -> pd.Series:
    """Generate returns for a single strategy."""
    if strategy_id in STOCK_STRATEGIES:
        strategy = STOCK_STRATEGIES[strategy_id]()
        if vix is not None:
            strategy.set_vix(vix)
        returns = strategy.generate_returns(stock_prices)
    else:
        strategy = ETF_STRATEGIES[strategy_id]()
        returns = strategy.generate_returns(etf_prices)

    # Trim warmup
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    return returns


def compute_spy_trend_filter(
    start: str = "2010-01-01",
    ma_period: int = 200,
    reduction: float = 0.5,
) -> pd.Series:
    """Compute SPY trend filter: 1.0 when above MA, `reduction` when below.

    Args:
        start: Start date for SPY data (needs extra history for MA warmup)
        ma_period: Moving average period (default 200 days)
        reduction: Position scalar when below MA (0.5 = half exposure)

    Returns:
        Series of scalars (1.0 or reduction) indexed by date
    """
    # Download extra history for MA warmup
    spy_prices = download_prices(["SPY"], start="2008-01-01")
    spy_close = spy_prices.squeeze()
    spy_ma = spy_close.rolling(ma_period).mean()

    above_ma = spy_close > spy_ma
    scalar = pd.Series(np.where(above_ma, 1.0, reduction), index=spy_close.index)

    return scalar


def run_portfolio(
    portfolio_id: str,
    start: str = "2010-01-01",
    end: str | None = None,
) -> tuple[str, pd.Series]:
    """Run a combined portfolio and return (name, returns Series).

    Args:
        portfolio_id: Key into PORTFOLIOS dict
        start: Backtest start date
        end: Backtest end date (optional)

    Returns:
        Tuple of (portfolio_name, combined_returns_series)
    """
    config = PORTFOLIOS[portfolio_id]
    weights = config["weights"]
    use_spy_filter = config["spy_filter"]

    # Load data
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    etf_prices = download_prices(symbols, start=start, end=end)

    stock_prices = None
    vix = None
    if any(sid in STOCK_STRATEGIES for sid in weights):
        stock_prices = download_sp500_prices(start=start)
        vix = download_vix()

    # Generate returns for each component strategy
    strategy_returns = {}
    for strategy_id in weights:
        strategy_returns[strategy_id] = _generate_strategy_returns(
            strategy_id, etf_prices, stock_prices, vix
        )

    # Align to common dates and compute weighted blend
    aligned = pd.DataFrame(strategy_returns).dropna()
    combined = sum(aligned[sid] * w for sid, w in weights.items())

    # Apply SPY trend filter
    if use_spy_filter:
        spy_filter = compute_spy_trend_filter(start=start)
        spy_aligned = spy_filter.reindex(combined.index, method="ffill").fillna(1.0)
        combined = combined * spy_aligned

    return config["name"], combined
