"""
Base Strategy — Abstract interface that all strategies implement.

Every strategy must expose a `generate_returns(prices)` method that takes
a DataFrame of prices and returns a Series of daily strategy returns.
This is the interface the validation framework expects.
"""

from abc import ABC, abstractmethod
import pandas as pd

# Every strategy's re-ranking grid is phased to the live rebalance calendar
# (rebalance_dates below), so the backtest's rebalance phase IS the live
# phase. Before 2026-09-09 each grid counted from the first bar of whatever
# frame it was handed, which put live 2-3 weeks behind the signal on every
# cycle (HISTORY.md 2026-09-09). The anchor lives with the calendar helpers.
from data.trading_dates import REBALANCE_ANCHOR  # noqa: E402  (re-exported)


def rebalance_dates(
    index: pd.DatetimeIndex, period: int, anchor: str | None = REBALANCE_ANCHOR
) -> pd.DatetimeIndex:
    """Every `period` bars, phased so the bar BEFORE `anchor` is a grid date.

    Live rebalances on day D at ~3 PM ET with data through D-1 and reads the
    latest signal row; ranking on the bar before each live date makes that
    row a fresh ranking. The backtest earns D's return on the new book while
    live earns from ~3 PM on D — the usual trade-at-close approximation.

    anchor=None counts from index[0] (the pre-2026-09-09 phase; research
    only). If the index ends before the anchor the phase is approximate.
    """
    if anchor is None or len(index) == 0:
        return index[::period]
    pos = max(int(index.searchsorted(pd.Timestamp(anchor))) - 1, 0)
    return index[pos % period::period]


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "BaseStrategy"
    # Phase of the re-ranking grid; see rebalance_dates(). Live strategies
    # expose it as a constructor arg, research ones inherit the default.
    rebalance_anchor: str | None = REBALANCE_ANCHOR
    # Most recent grid date in the last generate_signals() call — the date
    # the latest row's ranking was computed on. The live path reports it so
    # a rebalance that slipped past its grid date shows how stale its book is.
    last_grid_date: pd.Timestamp | None = None

    def rebalance_grid(self, index: pd.DatetimeIndex) -> pd.DatetimeIndex:
        dates = rebalance_dates(index, self.holding_period_days, self.rebalance_anchor)
        self.last_grid_date = dates[-1] if len(dates) else None
        return dates

    @abstractmethod
    def generate_signals(self, prices: pd.DataFrame) -> pd.DataFrame:
        """Generate position signals from price data.

        Args:
            prices: DataFrame with DatetimeIndex, one column per asset

        Returns:
            DataFrame of position weights (-1 to 1) per asset per day.
            Positive = long, negative = short, 0 = no position.
        """
        ...

    def generate_returns(self, prices: pd.DataFrame) -> pd.Series:
        """Generate strategy returns — this is what the validation framework calls.

        Args:
            prices: DataFrame of asset prices

        Returns:
            Series of daily strategy returns
        """
        signals = self.generate_signals(prices)
        asset_returns = prices.pct_change()

        # Strategy return = sum of (signal * asset return) across all assets
        # Signals are lagged by 1 day (trade on today's signal, get tomorrow's return)
        strategy_returns = (signals.shift(1) * asset_returns).sum(axis=1)

        return strategy_returns.dropna()
