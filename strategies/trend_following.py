"""
Time-Series Momentum Strategy (Moskowitz, Ooi, Pedersen 2012).

Core idea: Assets that have gone up over the past 12 months tend to continue
going up. Assets that have gone down tend to continue going down.

This is NOT a dual moving average crossover. It has a robust academic foundation
and works out-of-sample across asset classes (equities, bonds, commodities,
currencies) and across decades.

Implementation:
  - For each asset, compute trailing return over lookback period
  - If positive: go long (weight = 1/N where N = number of assets)
  - If negative: go flat (weight = 0) or short (weight = -1/N)
  - Rebalance at the end of each holding period
  - Equal volatility weighting to normalize across asset classes
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class TimeSeriesMomentum(BaseStrategy):
    """Time-series momentum following Moskowitz, Ooi, Pedersen (2012)."""

    name = "Time-Series Momentum"

    def __init__(
        self,
        lookback_days: int = 126,
        holding_period_days: int = 21,
        vol_lookback_days: int = 63,
        vol_target: float = 0.10,
        allow_short: bool = False,
    ):
        """
        Args:
            lookback_days: Period to measure momentum (126 = ~6 months, robust across sweep)
            holding_period_days: How often to rebalance (21 = ~1 month)
            vol_lookback_days: Period for volatility estimation (63 = ~3 months)
            vol_target: Target annualized volatility per position (0.10 = 10%)
            allow_short: Whether to short assets with negative momentum
        """
        self.lookback_days = lookback_days
        self.holding_period_days = holding_period_days
        self.vol_lookback_days = vol_lookback_days
        self.vol_target = vol_target
        self.allow_short = allow_short

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate momentum signals with volatility scaling.

        For each asset:
        1. Compute trailing return over lookback period
        2. Determine direction: long if positive, flat/short if negative
        3. Scale position by inverse volatility (risk parity within strategy)
        """
        returns = prices.pct_change()

        # Trailing momentum signal: cumulative return over lookback
        momentum = prices.pct_change(self.lookback_days)

        # Annualized rolling volatility for position sizing
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)

        # Direction: +1 for positive momentum, -1 or 0 for negative
        direction = np.sign(momentum)
        if not self.allow_short:
            direction = direction.clip(lower=0)

        # Volatility-scaled weights: target vol / realized vol
        # This normalizes position sizes so each asset contributes equal risk
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=2.0)  # Cap leverage at 2x

        # Number of assets with active positions (for equal weighting)
        n_assets = (direction != 0).sum(axis=1).replace(0, 1)

        # Final weight = direction * vol_scalar / n_active_assets
        weights = direction * vol_scalar
        weights = weights.div(n_assets, axis=0)

        # Only rebalance at holding period intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            grid_dates = self.rebalance_grid(valid_idx)
            rebalance_mask.loc[grid_dates] = True

        # Forward-fill weights between rebalance dates
        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)


class MultiTimeframeMomentum(BaseStrategy):
    """Multi-timeframe momentum — blends short, medium, and long lookbacks.

    Instead of a single 12-month signal, averages momentum across multiple
    timeframes. This makes the strategy more responsive to regime changes
    (like COVID crash) while still capturing long-term trends.

    Academic support: Baltas & Kosowski (2013), "Momentum Strategies in
    Futures Markets and Trend-Following Funds"
    """

    name = "Multi-Timeframe Momentum"

    def __init__(
        self,
        lookback_days: list[int] | None = None,
        holding_period_days: int = 21,
        vol_lookback_days: int = 63,
        vol_target: float = 0.10,
        allow_short: bool = False,
    ):
        """
        Args:
            lookback_days: List of lookback periods to blend (default: 1m, 3m, 6m, 12m)
            holding_period_days: Rebalance frequency
            vol_lookback_days: Volatility estimation window
            vol_target: Target annualized vol per position
            allow_short: Allow short positions
        """
        self.lookback_days = lookback_days or [21, 63, 126, 252]
        self.holding_period_days = holding_period_days
        self.vol_lookback_days = vol_lookback_days
        self.vol_target = vol_target
        self.allow_short = allow_short

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        returns = prices.pct_change()

        # Compute momentum signal for each timeframe
        momentum_signals = []
        for lb in self.lookback_days:
            mom = prices.pct_change(lb)
            # Normalize to +1/-1 direction
            momentum_signals.append(np.sign(mom))

        # Average across timeframes — gives a score from -1 to +1
        # A score of +1 means ALL timeframes agree: strong uptrend
        # A score of 0 means mixed signals: stay flat
        avg_signal = sum(momentum_signals) / len(momentum_signals)

        if not self.allow_short:
            avg_signal = avg_signal.clip(lower=0)

        # Volatility scaling
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=2.0)

        # Number of active positions
        n_assets = (avg_signal.abs() > 0.25).sum(axis=1).replace(0, 1)

        # Final weights
        weights = avg_signal * vol_scalar
        weights = weights.div(n_assets, axis=0)

        # Rebalance at holding period intervals
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            grid_dates = self.rebalance_grid(valid_idx)
            rebalance_mask.loc[grid_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)


class SimpleMomentum(BaseStrategy):
    """Simplified momentum — no volatility scaling, just direction.

    Useful as a baseline to compare against the full implementation.
    """

    name = "Simple Momentum"

    def __init__(self, lookback_days: int = 252, holding_period_days: int = 21):
        self.lookback_days = lookback_days
        self.holding_period_days = holding_period_days

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        n_assets = len(prices.columns)
        momentum = prices.pct_change(self.lookback_days)

        # Equal weight long if positive momentum, flat otherwise
        direction = (momentum > 0).astype(float)
        weights = direction / n_assets

        # Rebalance monthly
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            grid_dates = self.rebalance_grid(valid_idx)
            rebalance_mask.loc[grid_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)
