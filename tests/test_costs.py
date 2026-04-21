"""Tests for backtest transaction-cost layer (AUDIT_MONTH2 C6)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtesting.costs import (
    DEFAULT_COST_BPS,
    STRATEGY_COST_BPS,
    apply_transaction_costs,
    compute_one_way_turnover,
    cost_bps_for_strategy,
    generate_costed_returns,
)


def _signals(days: int, weights_per_day: list[list[float]]) -> pd.DataFrame:
    idx = pd.bdate_range(start="2023-01-02", periods=days)
    return pd.DataFrame(weights_per_day, index=idx, columns=["A", "B"])


def test_turnover_zero_for_static_weights():
    """No weight change → no turnover, no cost."""
    sig = _signals(5, [[0.5, 0.5]] * 5)
    t = compute_one_way_turnover(sig)
    assert (t == 0.0).all()


def test_turnover_full_rotation():
    """Full flip from [1,0] to [0,1] shows up as 1.0 turnover on the day the
    new position takes effect in the return math (signals.shift(1) convention)."""
    sig = _signals(4, [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]])
    t = compute_one_way_turnover(sig)
    # Day 3 (0-indexed): signals.shift(1) changed from [1,0] to [0,1] — that's
    # when the trade from yesterday's signal to today's takes effect.
    assert t.iloc[3] == 1.0
    # Other days: no position change, no turnover
    assert (t.iloc[:3] == 0.0).all()


def test_cost_drag_scales_with_turnover():
    """Higher turnover → proportionally higher cost drag."""
    sig_low = _signals(10, [[0.5, 0.5]] * 10)
    sig_high = _signals(10, [[0.5, 0.5], [0.0, 1.0], [1.0, 0.0]] * 3 + [[0.5, 0.5]])

    rets = pd.Series([0.01] * 10, index=sig_low.index)

    net_low = apply_transaction_costs(rets, sig_low, 20.0)
    net_high = apply_transaction_costs(rets, sig_high, 20.0)

    # Static weights: zero cost, returns unchanged
    pd.testing.assert_series_equal(net_low, rets)
    # High turnover: net < gross on at least one day
    assert (net_high < rets).any()


def test_cost_drag_scales_linearly_with_bps():
    """Doubling the bps rate should double the total drag."""
    sig = _signals(5, [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])
    rets = pd.Series([0.01] * 5, index=sig.index)

    drag_20 = (rets - apply_transaction_costs(rets, sig, 20.0)).sum()
    drag_40 = (rets - apply_transaction_costs(rets, sig, 40.0)).sum()

    assert abs(drag_40 - 2 * drag_20) < 1e-12


def test_cost_bps_fallback_for_unknown_strategy():
    assert cost_bps_for_strategy("stock_momentum") == STRATEGY_COST_BPS["stock_momentum"]
    assert cost_bps_for_strategy("crypto_momentum") == STRATEGY_COST_BPS["crypto_momentum"]
    assert cost_bps_for_strategy("unknown_strategy_xyz") == DEFAULT_COST_BPS


def test_crypto_costs_higher_than_equity():
    """Sanity: crypto bps > equity bps (reflects spread vs slippage)."""
    assert cost_bps_for_strategy("crypto_momentum") > cost_bps_for_strategy("stock_momentum")


def test_generate_costed_returns_matches_manual_path():
    """`generate_costed_returns` should equal the manual signals + apply_costs path."""
    from strategies.stock_momentum import StockMomentum

    # Build a synthetic 60-day / 5-stock price DataFrame
    idx = pd.bdate_range(start="2022-01-03", periods=60)
    np.random.seed(42)
    prices = pd.DataFrame(
        100 * np.cumprod(1 + 0.001 * np.random.randn(60, 5), axis=0),
        index=idx,
        columns=[f"STK{i}" for i in range(5)],
    )

    s = StockMomentum()
    from_helper = generate_costed_returns(s, prices, "stock_momentum")

    s2 = StockMomentum()
    signals = s2.generate_signals(prices)
    asset_returns = prices.pct_change()
    gross = (signals.shift(1) * asset_returns).sum(axis=1).dropna()
    manual = apply_transaction_costs(gross, signals, STRATEGY_COST_BPS["stock_momentum"])

    pd.testing.assert_series_equal(from_helper, manual)
