"""Daily crypto momentum rotation: top-N by 21d return, gated by BTC trend filter."""

import numpy as np
import pandas as pd
from strategies.base import BaseStrategy


class CryptoMomentum(BaseStrategy):
    name = "Crypto Momentum Rotation"

    def __init__(
        self,
        lookback_days: int = 21,
        top_n: int = 2,
        holding_period_days: int = 1,
        btc_ma_period: int = 125,
    ):
        """top_n=2 and btc_ma_period=125 are robust-opt winners (scripts/crypto_robust_opt.py, 2026-04-18)."""
        self.lookback_days = lookback_days
        self.top_n = top_n
        self.holding_period_days = holding_period_days
        self.btc_ma_period = btc_ma_period
        self._btc = None

    def set_btc(self, btc_prices: pd.Series):
        self._btc = btc_prices

    def _get_btc_trend_scalar(self, dates: pd.DatetimeIndex) -> pd.Series:
        """Binary BTC trend filter: 1.0 when above MA, 0.0 below."""
        if self._btc is None:
            return pd.Series(1.0, index=dates)

        # Strict min_periods for warmup (AUDIT_MONTH2.md C2).
        btc_ma_full = self._btc.rolling(
            self.btc_ma_period, min_periods=self.btc_ma_period
        ).mean()

        btc_aligned = self._btc.reindex(dates).ffill()
        btc_ma = btc_ma_full.reindex(dates).ffill()

        scalar = pd.Series(
            np.where(btc_aligned > btc_ma, 1.0, 0.0),
            index=dates,
        )
        return scalar

    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Rank coins by trailing momentum, hold top N equal-weight, gate by BTC trend filter."""
        # Drop today's partial UTC bar so momentum uses yesterday's settled close (HISTORY.md C9).
        if len(prices) >= 1:
            today_utc = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
            if pd.Timestamp(prices.index[-1]) >= today_utc:
                prices = prices.iloc[:-1]

        n_coins = prices.shape[1]
        momentum = prices.pct_change(self.lookback_days)
        ranks = momentum.rank(axis=1, ascending=True, method="average")

        effective_top_n = min(self.top_n, max(1, n_coins))
        cutoff = n_coins - effective_top_n
        selected = (ranks > cutoff).astype(float)

        # Equal weight among selected
        n_selected = selected.sum(axis=1).replace(0, 1)
        weights = selected.div(n_selected, axis=0)

        # BTC trend filter
        btc_scalar = self._get_btc_trend_scalar(prices.index)
        weights = weights.mul(btc_scalar, axis=0)

        # Rebalance at holding period intervals
        if self.holding_period_days > 1:
            rebalance_mask = pd.Series(False, index=prices.index)
            valid_idx = weights.dropna(how="all").index
            if len(valid_idx) > 0:
                rebalance_dates = valid_idx[:: self.holding_period_days]
                rebalance_mask.loc[rebalance_dates] = True
            weights[~rebalance_mask] = np.nan
            weights = weights.ffill()

        return weights.fillna(0)
