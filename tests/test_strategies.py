"""Smoke tests for all strategies — verify they initialize, generate signals, and return valid data.

These tests use synthetic price data (no network calls) to validate that
each strategy class works end-to-end without crashing.
"""

import numpy as np
import pandas as pd
import pytest

from strategies.trend_following import TimeSeriesMomentum, MultiTimeframeMomentum
from strategies.momentum import CrossSectionalMomentum, DualMomentum
from strategies.stock_momentum import StockMomentum
from strategies.multi_asset_trend import MultiAssetTrend
from strategies.low_volatility import LowVolatility
from strategies.mean_reversion import ShortTermReversal
from strategies.crypto_momentum import CryptoMomentum


def _make_prices(symbols: list[str], days: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic price data with realistic random walk."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-01", periods=days, freq="B")
    data = {}
    for sym in symbols:
        returns = rng.normal(0.0003, 0.015, size=days)
        data[sym] = 100 * np.exp(np.cumsum(returns))
    return pd.DataFrame(data, index=dates)


# ── ETF-based strategies ──────────────────────────────────────────

ETF_SYMBOLS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC",
               "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLRE", "SHY"]


@pytest.mark.parametrize("StrategyClass", [
    TimeSeriesMomentum,
    MultiTimeframeMomentum,
    CrossSectionalMomentum,
    DualMomentum,
    MultiAssetTrend,
])
def test_etf_strategy_smoke(StrategyClass):
    """ETF strategies produce valid signals and returns."""
    prices = _make_prices(ETF_SYMBOLS)
    strategy = StrategyClass()

    signals = strategy.generate_signals(prices)
    assert isinstance(signals, pd.DataFrame)
    assert len(signals) > 0
    # Weights should be bounded
    assert signals.abs().max().max() <= 1.01  # allow small float tolerance

    returns = strategy.generate_returns(prices)
    assert isinstance(returns, pd.Series)
    assert len(returns) > 0
    assert not returns.isna().all()


# ── Stock-based strategies ────────────────────────────────────────

STOCK_SYMBOLS = [f"STOCK_{i}" for i in range(50)]  # 50 fake stocks


def _make_vix(days: int = 500) -> pd.Series:
    """Synthetic VIX series oscillating around 20."""
    dates = pd.bdate_range("2022-01-01", periods=days, freq="B")
    rng = np.random.default_rng(99)
    vix = 20 + rng.normal(0, 3, size=days).cumsum() * 0.1
    vix = np.clip(vix, 10, 50)
    return pd.Series(vix, index=dates, name="VIX")


@pytest.mark.parametrize("StrategyClass", [
    StockMomentum,
    LowVolatility,
    ShortTermReversal,
])
def test_stock_strategy_smoke(StrategyClass):
    """Stock strategies produce valid signals with VIX."""
    prices = _make_prices(STOCK_SYMBOLS)
    vix = _make_vix()

    strategy = StrategyClass()
    strategy.set_vix(vix)

    signals = strategy.generate_signals(prices)
    assert isinstance(signals, pd.DataFrame)
    assert len(signals) > 0

    returns = strategy.generate_returns(prices)
    assert isinstance(returns, pd.Series)
    assert len(returns) > 0
    assert not returns.isna().all()


# ── Crypto strategy ──────────────────────────────────────────────

CRYPTO_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD",
                  "AVAX-USD", "LINK-USD", "DOT-USD", "XRP-USD"]


def test_crypto_strategy_smoke():
    """Crypto momentum strategy produces valid signals with BTC filter."""
    prices = _make_prices(CRYPTO_SYMBOLS, days=400)
    btc = prices["BTC-USD"].copy()
    btc.name = "BTC-USD"

    strategy = CryptoMomentum()
    strategy.set_btc(btc)

    signals = strategy.generate_signals(prices)
    assert isinstance(signals, pd.DataFrame)
    assert len(signals) > 0

    returns = strategy.generate_returns(prices)
    assert isinstance(returns, pd.Series)
    assert len(returns) > 0


# ── Cross-strategy invariants ────────────────────────────────────

def test_all_strategies_have_names():
    """Every strategy class has a meaningful name attribute."""
    all_classes = [
        TimeSeriesMomentum, MultiTimeframeMomentum,
        CrossSectionalMomentum, DualMomentum,
        MultiAssetTrend, StockMomentum,
        LowVolatility, ShortTermReversal,
        CryptoMomentum,
    ]
    for cls in all_classes:
        s = cls()
        assert hasattr(s, "name")
        assert len(s.name) > 0
        assert s.name != "BaseStrategy"


def test_returns_are_reasonable():
    """Strategy returns should not have absurd daily values."""
    prices = _make_prices(ETF_SYMBOLS)
    strategy = TimeSeriesMomentum()
    returns = strategy.generate_returns(prices)

    # No single day should have > 100% return (sanity check)
    assert returns.abs().max() < 1.0
    # Mean daily return should be small
    assert abs(returns.mean()) < 0.01
