"""
Multi-Asset Trend Following (Hurst, Ooi, Pedersen 2017).

Applies trend-following across uncorrelated asset classes — equities,
bonds, gold, commodities, international equities — using a constrained
universe of 5 ETFs that represent genuinely different return drivers.

This is NOT the same as the existing ETF momentum strategies, which use
17 correlated equity-sector ETFs. The key here is *asset class diversity*:
when equities crash, bonds and gold often trend UP, providing crisis alpha.

Academic basis:
- Hurst, Ooi, Pedersen (2017): "A Century of Evidence on Trend-Following"
  137 years of data, Sharpe ~1.0 for diversified trend portfolio
- Faber (2007): "A Quantitative Approach to Tactical Asset Allocation"
  Simple 10-month SMA rule on 5 asset classes, halves drawdowns
- Moskowitz, Ooi, Pedersen (2012): Time-series momentum across 58 instruments
- Baltas & Kosowski (2013): Multi-asset trend captures different risk premia

Key properties:
- Crisis alpha: tends to work when equities crash (bonds/gold trend up)
- Low correlation (0.15-0.35) with equity momentum
- Uses only 5 ETFs — each representing a distinct asset class
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy, REBALANCE_ANCHOR


# Deliberately small, uncorrelated universe — one ETF per asset class
MULTI_ASSET_UNIVERSE = ["SPY", "EFA", "TLT", "GLD", "DBC"]


class MultiAssetTrend(BaseStrategy):
    """Multi-asset trend following across 5 uncorrelated asset classes.

    Dual-confirmation signal: requires both positive trailing return
    AND price above 200-day MA to go long. This reduces whipsaw.
    """

    name = "Multi-Asset Trend"

    def __init__(
        self,
        lookback_days: int = 126,
        ma_period: int = 200,
        holding_period_days: int = 21,
        vol_lookback_days: int = 63,
        vol_target: float = 0.10,
        rebalance_anchor: str | None = REBALANCE_ANCHOR,
    ):
        """
        Args:
            lookback_days: Trailing return period for trend signal (126 = ~6 months)
            ma_period: Moving average period for confirmation (200 days)
            holding_period_days: Rebalance frequency (21 = monthly)
            vol_lookback_days: Volatility estimation window
            vol_target: Target annualized vol per position
            rebalance_anchor: Grid phase — see strategies.base.rebalance_dates.
        """
        self.lookback_days = lookback_days
        self.ma_period = ma_period
        self.holding_period_days = holding_period_days
        self.vol_lookback_days = vol_lookback_days
        self.vol_target = vol_target
        self.rebalance_anchor = rebalance_anchor

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate trend signals across asset classes.

        Dual confirmation: go long only when BOTH:
        1. Trailing return over lookback is positive
        2. Price is above its 200-day moving average

        Otherwise go flat (to cash). No shorting.
        """
        # Filter to our specific universe (ignore extra columns)
        available = [s for s in MULTI_ASSET_UNIVERSE if s in prices.columns]
        prices = prices[available].copy()

        returns = prices.pct_change()

        # Signal 1: Trailing return over lookback period
        trailing_return = prices.pct_change(self.lookback_days)
        positive_trend = trailing_return > 0

        # Signal 2: Price above 200-day moving average
        ma = prices.rolling(self.ma_period).mean()
        above_ma = prices > ma

        # Dual confirmation: both must agree
        direction = (positive_trend & above_ma).astype(float)

        # Volatility scaling — target vol per position
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=2.0)

        # Number of active positions for equal-risk weighting
        n_active = direction.sum(axis=1).replace(0, 1)

        # Final weights: direction * vol_scalar / n_active
        weights = (direction * vol_scalar).div(n_active, axis=0)

        # Cap total exposure at 1.0 (no leverage)
        total_exposure = weights.sum(axis=1)
        excess = total_exposure.clip(lower=1.0)
        weights = weights.div(excess, axis=0)

        # Rebalance at holding period intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            grid_dates = self.rebalance_grid(valid_idx)
            rebalance_mask.loc[grid_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)
