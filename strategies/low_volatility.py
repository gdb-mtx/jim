"""
Low-Volatility Anomaly Strategy (Baker, Bradley, Wurgler 2011).

Buys the least volatile stocks in the S&P 500. Low-vol stocks have
historically delivered higher *risk-adjusted* returns than high-vol stocks —
the opposite of what CAPM predicts.

This strategy is the ideal complement to momentum because:
- Momentum buys recent winners (typically high-vol, high-beta)
- Low-vol buys boring stocks (utilities, staples, healthcare)
- Correlation between the two is -0.2 to 0.1
- When momentum crashes, low-vol stocks hold steady

Academic basis:
- Baker, Bradley, Wurgler (2011): "Benchmarks as Limits to Arbitrage"
  Low-vol stocks earn higher Sharpe than high-vol stocks
- Frazzini & Pedersen (2014): "Betting Against Beta"
  Low-beta anomaly across 20 countries, 12 asset classes
- Ang, Hodrick, Xing, Zhang (2006): High idiosyncratic vol = low returns
- Blitz & van Vliet (2007): "The Volatility Effect"
  Lowest-vol decile outperforms highest by 2-3%/year

Enhancement: momentum filter within low-vol (positive 12-month return)
to avoid value traps — stocks that are low-vol because they're dying.
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class LowVolatility(BaseStrategy):
    """Low-volatility stock selection with momentum quality filter.

    1. Rank S&P 500 stocks by trailing realized volatility (ascending)
    2. Select lowest-vol quintile (~90 stocks)
    3. Filter: require positive 12-month return (avoid dying stocks)
    4. Pick top N by lowest vol from filtered set
    5. Equal weight, monthly rebalance
    6. VIX regime filter + SPY trend filter compatible
    """

    name = "Low Volatility"

    def __init__(
        self,
        vol_lookback_days: int = 63,
        momentum_lookback_days: int = 252,
        top_n: int = 30,
        holding_period_days: int = 21,
        vol_target: float = 0.15,
        position_vol_lookback: int = 63,
        vix_threshold_reduce: float = 35.0,
        vix_threshold_exit: float = 45.0,
        vix_reduce_factor: float = 0.5,
    ):
        """
        Args:
            vol_lookback_days: Window for ranking stocks by vol (63 = 3 months)
            momentum_lookback_days: Window for momentum quality filter (252 = 12 months)
            top_n: Number of low-vol stocks to hold
            holding_period_days: Rebalance frequency (21 = monthly)
            vol_target: Target annualized vol per position
            position_vol_lookback: Window for position-level vol scaling
            vix_threshold_reduce: VIX level to halve exposure
            vix_threshold_exit: VIX level to exit entirely
            vix_reduce_factor: Scale factor when VIX elevated
        """
        self.vol_lookback_days = vol_lookback_days
        self.momentum_lookback_days = momentum_lookback_days
        self.top_n = top_n
        self.holding_period_days = holding_period_days
        self.vol_target = vol_target
        self.position_vol_lookback = position_vol_lookback
        self.vix_threshold_reduce = vix_threshold_reduce
        self.vix_threshold_exit = vix_threshold_exit
        self.vix_reduce_factor = vix_reduce_factor
        self._vix = None

    def set_vix(self, vix: pd.Series):
        """Inject VIX data for regime filtering."""
        self._vix = vix

    def _get_regime_scalar(self, dates: pd.DatetimeIndex) -> pd.Series:
        """Compute VIX-based regime scalar."""
        if self._vix is None:
            return pd.Series(1.0, index=dates)

        vix_aligned = self._vix.reindex(dates).ffill()
        scalar = pd.Series(1.0, index=dates)
        scalar[vix_aligned >= self.vix_threshold_reduce] = self.vix_reduce_factor
        scalar[vix_aligned >= self.vix_threshold_exit] = 0.0
        return scalar

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate low-volatility stock selection signals.

        1. Compute trailing realized vol for each stock
        2. Rank by vol (ascending — lowest vol gets highest rank)
        3. Filter for positive momentum (avoid value traps)
        4. Select top N lowest-vol stocks with positive momentum
        5. Equal weight with vol-targeting
        """
        returns = prices.pct_change()

        # Realized volatility ranking (lower = better)
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)

        # Rank by vol ascending (rank 1 = lowest vol = best)
        # Use descending rank so highest rank = lowest vol
        vol_rank = rolling_vol.rank(axis=1, ascending=False, method="average")

        # Momentum quality filter: require positive 12-month return
        momentum = prices.pct_change(self.momentum_lookback_days)
        positive_momentum = momentum > 0

        # Combined: low vol + positive momentum
        n_stocks = prices.shape[1]
        vol_quintile_cutoff = n_stocks * 0.80  # top 20% of vol_rank = lowest vol
        is_low_vol = vol_rank > vol_quintile_cutoff
        eligible = (is_low_vol & positive_momentum).astype(float)

        # Among eligible, pick top N by lowest vol (highest vol_rank)
        # Mask out non-eligible, then rank again
        eligible_vol_rank = vol_rank * eligible.replace(0, np.nan)
        final_rank = eligible_vol_rank.rank(axis=1, ascending=False, method="average")
        effective_top_n = min(self.top_n, max(1, n_stocks // 15))
        selected = (final_rank <= effective_top_n).astype(float)

        # Position-level vol scaling
        position_vol = returns.rolling(self.position_vol_lookback).std() * np.sqrt(252)
        pos_vol_scalar = self.vol_target / position_vol.replace(0, np.nan)
        pos_vol_scalar = pos_vol_scalar.clip(upper=3.0)

        # Weight = selected * vol_scalar / n_selected
        n_selected = selected.sum(axis=1).replace(0, 1)
        weights = (selected * pos_vol_scalar).div(n_selected, axis=0)

        # Cap total exposure at 1.5x
        total_exposure = weights.sum(axis=1)
        excess = (total_exposure / 1.5).clip(lower=1.0)
        weights = weights.div(excess, axis=0)

        # VIX regime filter
        regime_scalar = self._get_regime_scalar(prices.index)
        weights = weights.mul(regime_scalar, axis=0)

        # Rebalance at holding period intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[:: self.holding_period_days]
            rebalance_mask.loc[rebalance_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)
