"""
Individual Stock Momentum with VIX Regime Filter.

This is the real deal — momentum on individual S&P 500 stocks, where
there's actual dispersion to exploit. The ETF strategies were limited
by the correlation of their small universe.

Strategy logic:
1. Rank all S&P 500 stocks by 6-12 month momentum (skip last month)
2. Buy the top N stocks (e.g., top 20-30), equal or vol-weighted
3. VIX regime filter: reduce exposure when volatility is elevated
4. Rebalance monthly

Academic basis:
- Jegadeesh & Titman (1993): original stock momentum anomaly
- Asness, Moskowitz, Pedersen (2013): "Value and Momentum Everywhere"
- Daniel & Moskowitz (2016): momentum crashes and how VIX helps avoid them

The VIX filter is critical. Daniel & Moskowitz showed that momentum
strategies crash hard in high-volatility regimes (2009 recovery, etc.).
A simple VIX threshold avoids the worst of these crashes.
"""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class StockMomentum(BaseStrategy):
    """Individual stock momentum on S&P 500 with VIX regime filter.

    This strategy has fundamentally more alpha potential than ETF momentum
    because 500 stocks have far more dispersion than 18 ETFs.
    """

    name = "Stock Momentum (S&P 500)"

    def __init__(
        self,
        lookback_days: int = 189,
        skip_recent: int = 21,
        top_n: int = 15,
        holding_period_days: int = 21,
        vol_target: float = 0.20,
        vol_lookback_days: int = 63,
        vix_threshold_reduce: float = 35.0,
        vix_threshold_exit: float = 45.0,
        vix_reduce_factor: float = 0.5,
    ):
        """
        Args:
            lookback_days: Momentum ranking period (189 = ~9 months)
            skip_recent: Skip most recent N days to avoid short-term reversal
            top_n: Number of top stocks to hold
            holding_period_days: Rebalance frequency (21 = monthly)
            vol_target: Target annualized vol per position
            vol_lookback_days: Volatility estimation window
            vix_threshold_reduce: VIX level to halve exposure
            vix_threshold_exit: VIX level to exit entirely (go to cash)
            vix_reduce_factor: Position scale when VIX is elevated
        """
        self.lookback_days = lookback_days
        self.skip_recent = skip_recent
        self.top_n = top_n
        self.holding_period_days = holding_period_days
        self.vol_target = vol_target
        self.vol_lookback_days = vol_lookback_days
        self.vix_threshold_reduce = vix_threshold_reduce
        self.vix_threshold_exit = vix_threshold_exit
        self.vix_reduce_factor = vix_reduce_factor
        self._vix = None

    def set_vix(self, vix: pd.Series):
        """Inject VIX data for regime filtering.

        Args:
            vix: Series of VIX closing values with DatetimeIndex
        """
        self._vix = vix

    def _get_regime_scalar(self, dates: pd.DatetimeIndex) -> pd.Series:
        """Compute regime-based position scalar from VIX.

        Returns:
            Series of scalars: 1.0 (calm), reduce_factor (elevated), 0.0 (panic)
        """
        if self._vix is None:
            return pd.Series(1.0, index=dates)

        # Align VIX to strategy dates
        vix_aligned = self._vix.reindex(dates).ffill()

        scalar = pd.Series(1.0, index=dates)
        scalar[vix_aligned >= self.vix_threshold_reduce] = self.vix_reduce_factor
        scalar[vix_aligned >= self.vix_threshold_exit] = 0.0

        return scalar

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate individual stock momentum signals with VIX filter.

        1. Compute 9-month return, skip last month (avoid reversal)
        2. Rank all stocks, select top N
        3. Vol-scale positions
        4. Apply VIX regime filter
        5. Rebalance monthly
        """
        returns = prices.pct_change()

        # Momentum signal: return over lookback, skipping recent period
        if self.skip_recent > 0:
            lagged = prices.shift(self.skip_recent)
            older = prices.shift(self.lookback_days)
            momentum = (lagged - older) / older
        else:
            momentum = prices.pct_change(self.lookback_days)

        # Rank stocks each day — rank 1 goes to strongest momentum. Descending
        # rank with a direct `<= top_n` threshold is NaN-safe: tickers with
        # NaN momentum (pre-IPO, not enough history in the slice) get NaN rank
        # and are naturally excluded. The old pattern `ranks > (n_stocks -
        # top_n)` broke when the universe contained partial-history columns:
        # `n_stocks` counted every column, so the cutoff exceeded the actual
        # max achievable rank and zero stocks got picked.
        ranks = momentum.rank(axis=1, ascending=False, method="average")
        n_stocks = prices.shape[1]
        effective_top_n = min(self.top_n, max(1, n_stocks // 10))
        selected = (ranks <= effective_top_n).astype(float)

        # Volatility scaling per stock
        rolling_vol = returns.rolling(self.vol_lookback_days).std() * np.sqrt(252)
        vol_scalar = self.vol_target / rolling_vol.replace(0, np.nan)
        vol_scalar = vol_scalar.clip(upper=3.0)  # Cap at 3x leverage per stock

        # Weight = selected * vol_scalar / n_selected
        n_selected = selected.sum(axis=1).replace(0, 1)
        weights = (selected * vol_scalar).div(n_selected, axis=0)

        # Cap total portfolio exposure at 1.5x (no extreme leverage)
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
            rebalance_dates = valid_idx[::self.holding_period_days]
            rebalance_mask.loc[rebalance_dates] = True

        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

        return weights.fillna(0)


class StockMomentumNoVIX(StockMomentum):
    """Same strategy without VIX filter — useful as a comparison baseline."""

    name = "Stock Momentum (No VIX)"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vix_threshold_reduce = 999.0
        self.vix_threshold_exit = 999.0
