"""
Base Strategy — Abstract interface that all strategies implement.

Every strategy must expose a `generate_returns(prices)` method that takes
a DataFrame of prices and returns a Series of daily strategy returns.
This is the interface the validation framework expects.
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "BaseStrategy"

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
