"""Tests for the backtest halt simulation (AUDIT_MONTH2 C5 parity layer)."""

import numpy as np
import pandas as pd

from backtesting.drawdown_halt import simulate_drawdown_halt, would_halt_have_fired


def _series(values, start="2023-01-02"):
    idx = pd.bdate_range(start=start, periods=len(values))
    return pd.Series(values, index=idx)


def test_no_halt_on_shallow_drawdown():
    """-10% DD → halt at -35% does not fire; returns are unchanged."""
    # -1% per day for 10 days ≈ -10% DD
    r = _series([-0.01] * 10)
    sim = simulate_drawdown_halt(r, halt_threshold=0.35)

    assert sim.halt_fired is False
    assert sim.halt_date is None
    pd.testing.assert_series_equal(sim.returns, r)
    assert sim.max_drawdown_pre_halt > -0.35


def test_halt_fires_on_catastrophic_drawdown():
    """-40% cumulative decline trips the -35% halt; subsequent returns zeroed."""
    # 5 days of -10% each → (0.9)^5 = 0.59049 → DD ≈ -41%
    r = _series([-0.10] * 5 + [0.05] * 10)  # Then try to recover
    sim = simulate_drawdown_halt(r, halt_threshold=0.35)

    assert sim.halt_fired is True
    # Halt should fire somewhere in the first 5 days (cumulative hits -35%
    # at day 5: (0.9)^4 = 0.6561 = -34.4%, (0.9)^5 = 0.59049 = -41%).
    halt_idx = sim.returns.index.get_loc(sim.halt_date)
    assert halt_idx == 4  # 5th day (0-indexed)

    # Halt day keeps its return
    assert sim.returns.iloc[halt_idx] == -0.10
    # All subsequent returns zeroed
    assert (sim.returns.iloc[halt_idx + 1:] == 0.0).all()
    # Recovery leg never happens in the adjusted series
    adjusted_equity = (1 + sim.returns).cumprod()
    # Final equity ≈ 0.59049 (stays flat after halt)
    assert abs(adjusted_equity.iloc[-1] - (0.9 ** 5)) < 1e-9


def test_halt_stays_latched_through_recovery():
    """Even if the raw series V-shapes back to a new peak, halt stays on."""
    # -40% then +50% cumulative
    r = _series([-0.40, 0.50])
    sim = simulate_drawdown_halt(r, halt_threshold=0.35)

    assert sim.halt_fired is True
    # Raw cumulative equity recovers: 0.6 * 1.5 = 0.90 (still below peak
    # but above halt threshold). Doesn't matter — halt latches.
    assert sim.returns.iloc[0] == -0.40
    assert sim.returns.iloc[1] == 0.0


def test_empty_series_is_no_op():
    r = pd.Series(dtype=float)
    sim = simulate_drawdown_halt(r)
    assert sim.halt_fired is False
    assert len(sim.returns) == 0


def test_threshold_override():
    """A tighter threshold (-10%) fires where the default (-35%) does not."""
    r = _series([-0.02] * 8)  # ~-15% DD
    assert would_halt_have_fired(r, halt_threshold=0.35) is False
    assert would_halt_have_fired(r, halt_threshold=0.10) is True


def test_nan_values_treated_as_flat():
    r = _series([-0.10, np.nan, -0.10, -0.10, -0.10, -0.10])
    sim = simulate_drawdown_halt(r, halt_threshold=0.35)
    assert sim.halt_fired is True
