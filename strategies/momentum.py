"""
Cross-Sectional & Dual Momentum Strategies.

Cross-Sectional Momentum (Jegadeesh & Titman 1993):
  Instead of asking "is this asset trending up?" (time-series), asks
  "which assets are trending up the MOST?" and rotates into the top N.
  More assets = more dispersion = more opportunity.

Dual Momentum (Gary Antonacci 2014, "Dual Momentum Investing"):
  Combines both time-series and cross-sectional momentum:
  1. Absolute momentum filter: is the asset beating cash (T-bills/SHY)?
  2. Relative momentum rank: which assets are strongest?
  3. Only hold assets that pass BOTH filters.
  Simple, low turnover, strong out-of-sample evidence for retail traders.
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class CrossSectionalMomentum(BaseStrategy):
    """Cross-sectional (relative strength) momentum.

    Ranks all assets by trailing return, goes long the top N performers.
    Academic basis: Jegadeesh & Titman (1993), Asness et al. (2013).
    """

    name = "Cross-Sectional Momentum"

    def __init__(
        self,
        lookback_days: int = 189,
        holding_period_days: int = 21,
        top_n: int = 6,
        vol_lookback_days: int = 63,
        vol_target: float = 0.10,
        skip_recent: int = 0,
    ):
        """
        Args:
            lookback_days: Period to rank momentum (189 = ~9 months, robust across sweep)
            holding_period_days: Rebalance frequency (21 = ~1 month)
            top_n: Number of top-ranked assets to hold (6 = top third of 18-asset universe)
            vol_lookback_days: Volatility estimation window
            vol_target: Target annualized vol per position
            skip_recent: Skip most recent N days (0 = disabled, skip_recent hurts with ETFs)
        """
        self.lookback_days = lookback_days
        self.holding_period_days = holding_period_days
        self.top_n = top_n
        self.vol_lookback_days = vol_lookback_days
        self.vol_target = vol_target
        self.skip_recent = skip_recent

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Rank assets by momentum, go long top N.

        1. Compute trailing return (skipping most recent month to avoid reversal)
        2. Rank all assets
        3. Equal-weight top N, vol-scaled
        """
        returns = prices.pct_change()

        # Momentum = return over lookback, skipping the most recent `skip_recent` days
        # This avoids short-term mean reversion (Jegadeesh 1990)
        if self.skip_recent > 0:
            lagged_prices = prices.shift(self.skip_recent)
            older_prices = prices.shift(self.lookback_days)
            momentum = (lagged_prices - older_prices) / older_prices
        else:
            momentum = prices.pct_change(self.lookback_days)

        # Rank assets each day (ascending: rank N = best performer)
        ranks = momentum.rank(axis=1, ascending=True)
        n_assets = len(prices.columns)
        cutoff = n_assets - self.top_n  # Top N threshold

        # Select top N
        selected = (ranks > cutoff).astype(float)

        # Volatility scaling
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=2.0)

        # Equal weight among selected, vol-scaled
        n_selected = selected.sum(axis=1).replace(0, 1)
        weights = selected * vol_scalar
        weights = weights.div(n_selected, axis=0)

        # Rebalance at intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[::self.holding_period_days]
            rebalance_mask.loc[rebalance_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)


class DualMomentum(BaseStrategy):
    """Dual Momentum — Antonacci (2014).

    Combines absolute (time-series) and relative (cross-sectional) momentum:
    1. Absolute filter: only hold assets with positive excess momentum over cash proxy
    2. Relative rank: among passing assets, hold the top N
    3. When nothing passes the absolute filter, go to bonds (TLT/AGG)

    This is one of the most well-documented and robust retail strategies.
    """

    name = "Dual Momentum"

    def __init__(
        self,
        lookback_days: int = 126,
        holding_period_days: int = 21,
        top_n: int = 6,
        cash_proxy: str = "SHY",
        safe_haven: str = "TLT",
        vol_lookback_days: int = 63,
        vol_target: float = 0.10,
    ):
        """
        Args:
            lookback_days: Momentum lookback (126 = ~6 months, robust across sweep)
            holding_period_days: Rebalance frequency
            top_n: Max assets to hold from the risky universe (6 = top third)
            cash_proxy: Ticker for cash/T-bill comparison (SHY = 1-3yr Treasury)
            safe_haven: Ticker to flee to when all assets fail absolute test
            vol_lookback_days: Volatility estimation window
            vol_target: Target annualized vol per position
        """
        self.lookback_days = lookback_days
        self.holding_period_days = holding_period_days
        self.top_n = top_n
        self.cash_proxy = cash_proxy
        self.safe_haven = safe_haven
        self.vol_lookback_days = vol_lookback_days
        self.vol_target = vol_target

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Dual momentum signal generation.

        1. Compute trailing returns for all assets
        2. Absolute filter: asset return > cash proxy return
        3. Relative rank: pick top N from assets passing the filter
        4. If nothing passes: allocate to safe haven (bonds)
        """
        returns = prices.pct_change()
        momentum = prices.pct_change(self.lookback_days)

        # Separate cash proxy momentum for absolute filter
        if self.cash_proxy in momentum.columns:
            cash_momentum = momentum[self.cash_proxy]
        else:
            # If cash proxy not in universe, use 0 as threshold
            cash_momentum = pd.Series(0.0, index=momentum.index)

        # Identify risky assets (everything except cash proxy and safe haven)
        risky_assets = [c for c in prices.columns
                        if c not in (self.cash_proxy, self.safe_haven)]

        # Step 1: Absolute momentum filter — must beat cash
        risky_momentum = momentum[risky_assets]
        passes_absolute = risky_momentum.gt(cash_momentum, axis=0)

        # Step 2: Rank passing assets by momentum (relative)
        # Mask out assets that fail absolute test
        filtered_momentum = risky_momentum.where(passes_absolute)
        ranks = filtered_momentum.rank(axis=1, ascending=True)
        n_passing = passes_absolute.sum(axis=1)
        actual_top_n = n_passing.clip(upper=self.top_n)

        # Select top N from passing assets
        cutoff = ranks.max(axis=1) - actual_top_n + 1
        cutoff = cutoff.clip(lower=1)
        selected = ranks.ge(cutoff, axis=0) & passes_absolute

        # Step 3: When nothing passes, go to safe haven
        nothing_passes = n_passing == 0

        # Build weight matrix for ALL assets
        weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)

        # Volatility scaling
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=2.0)

        # Assign weights to selected risky assets
        for col in risky_assets:
            weights[col] = selected[col].astype(float) * vol_scalar.get(col, 1.0)

        # Normalize by number of selected
        n_selected = selected.sum(axis=1).replace(0, 1)
        for col in risky_assets:
            weights[col] = weights[col] / n_selected

        # Safe haven allocation when nothing passes absolute filter
        if self.safe_haven in weights.columns:
            safe_vol_scalar = vol_scalar.get(self.safe_haven, pd.Series(1.0, index=prices.index))
            weights.loc[nothing_passes, self.safe_haven] = safe_vol_scalar[nothing_passes]

        # Zero out cash proxy (it's just for comparison, never hold it)
        if self.cash_proxy in weights.columns:
            weights[self.cash_proxy] = 0.0

        # Rebalance at intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[::self.holding_period_days]
            rebalance_mask.loc[rebalance_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)
