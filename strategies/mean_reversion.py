"""
Short-Term Reversal Strategy (Jegadeesh 1990, Lehmann 1990).

Buys S&P 500 stocks that dropped the most over the past week. This
captures the well-documented short-term reversal effect: stocks that
crash in the short term tend to bounce back.

This is the *anti-momentum* strategy. Our Stock Momentum explicitly
skips the most recent month (skip_recent=21) because short-term
reversals contaminate momentum signals. This strategy *harvests*
that exact effect.

Academic basis:
- Jegadeesh (1990): "Evidence of Predictable Behavior of Security Returns"
  Stocks with worst 1-4 week returns earn highest returns next month
- Lehmann (1990): "Fads, Martingales, and Market Efficiency"
  Weekly contrarian strategies produce significant abnormal returns
- Lo & MacKinlay (1990): "When Are Contrarian Profits Due to Overreaction?"
  Decomposed contrarian profits — cross-autocorrelation makes it robust
- Nagel (2012): "Evaporating Liquidity"
  Reversal profits = compensation for liquidity provision, strongest at high VIX

Key properties:
- Correlation with Stock Momentum: -0.10 to -0.30
- Strongest when VIX is elevated (opposite of momentum)
- Weekly rebalance (5-day holding period)
- High win rate but small gains per trade
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class ShortTermReversal(BaseStrategy):
    """Short-term reversal on S&P 500 — buy the biggest weekly losers.

    1. Rank stocks by trailing 5-day return (ascending)
    2. Buy bottom decile (worst ~45 stocks)
    3. Vol-scale positions
    4. VIX filter: INCREASE exposure at high VIX (reversals are strongest)
    5. SPY trend filter still applies (avoid catching knives in crashes)
    6. Weekly (5-day) rebalance
    """

    name = "Short-Term Reversal"

    def __init__(
        self,
        lookback_days: int = 5,
        top_n: int = 45,
        holding_period_days: int = 5,
        vol_target: float = 0.15,
        vol_lookback_days: int = 63,
        vix_threshold_reduce: float = 35.0,
        vix_threshold_exit: float = 45.0,
    ):
        """
        Args:
            lookback_days: Reversal signal period (5 = 1 week)
            top_n: Number of worst performers to buy
            holding_period_days: Rebalance frequency (5 = weekly)
            vol_target: Target annualized vol per position
            vol_lookback_days: Volatility estimation window
            vix_threshold_reduce: VIX level below which to REDUCE
                (reversed from momentum — we WANT high VIX for reversals)
            vix_threshold_exit: VIX level to exit (systemic crisis too extreme)
        """
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.holding_period_days = holding_period_days
        self.vol_target = vol_target
        self.vol_lookback_days = vol_lookback_days
        self.vix_threshold_reduce = vix_threshold_reduce
        self.vix_threshold_exit = vix_threshold_exit
        self._vix = None

    def set_vix(self, vix: pd.Series):
        """Inject VIX data for regime filtering."""
        self._vix = vix

    def _get_regime_scalar(self, dates: pd.DatetimeIndex) -> pd.Series:
        """Compute regime scalar — INVERTED from momentum.

        For reversals, elevated VIX is GOOD (bigger bounces).
        - VIX < 20: base exposure (1.0)
        - VIX 20-35: increased exposure (1.25) — reversals are stronger
        - VIX > 45: exit (0.0) — systemic crisis, everything correlates
        """
        if self._vix is None:
            return pd.Series(1.0, index=dates)

        vix_aligned = self._vix.reindex(dates).ffill()

        scalar = pd.Series(1.0, index=dates)
        # Boost exposure when VIX is moderately elevated (reversal sweet spot)
        scalar[(vix_aligned >= 20) & (vix_aligned < self.vix_threshold_reduce)] = 1.25
        # Still exit at extreme panic (everything is correlated)
        scalar[vix_aligned >= self.vix_threshold_exit] = 0.0

        return scalar

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate short-term reversal signals.

        Buy the biggest short-term losers — they tend to bounce back.
        This is the mirror image of momentum stock selection.
        """
        returns = prices.pct_change()

        # Short-term return (5-day) — we want the WORST performers
        short_return = prices.pct_change(self.lookback_days)

        # Rank ascending: rank 1 = worst return = our buy signal
        ranks = short_return.rank(axis=1, ascending=True, method="average")
        n_stocks = prices.shape[1]

        # Select bottom decile (worst performers)
        effective_top_n = min(self.top_n, max(1, n_stocks // 10))
        selected = (ranks <= effective_top_n).astype(float)

        # Volatility scaling per stock
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=3.0)

        # Weight = selected * vol_scalar / n_selected
        n_selected = selected.sum(axis=1).replace(0, 1)
        weights = (selected * vol_scalar).div(n_selected, axis=0)

        # Cap total exposure at 1.5x
        total_exposure = weights.sum(axis=1)
        excess = (total_exposure / 1.5).clip(lower=1.0)
        weights = weights.div(excess, axis=0)

        # VIX regime filter (inverted — boost at moderate VIX)
        regime_scalar = self._get_regime_scalar(prices.index)
        weights = weights.mul(regime_scalar, axis=0)

        # Rebalance at holding period intervals (weekly)
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[:: self.holding_period_days]
            rebalance_mask.loc[rebalance_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)
