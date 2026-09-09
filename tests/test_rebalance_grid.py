"""Re-ranking grid phase (HISTORY.md 2026-09-09).

The grid must be phased to the live calendar and independent of where the
price frame starts — the pre-fix grid counted from the frame's first bar,
so live and backtest disagreed and a truncated cache silently moved it.
"""

import pandas as pd

from strategies.base import REBALANCE_ANCHOR, rebalance_dates


def _bdays(start: str, end: str) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


def test_bar_before_anchor_is_a_grid_date():
    idx = _bdays("2024-01-01", "2026-12-31")
    grid = rebalance_dates(idx, 21)
    anchor_pos = idx.get_loc(pd.Timestamp(REBALANCE_ANCHOR))
    assert idx[anchor_pos - 1] in grid
    assert pd.Timestamp(REBALANCE_ANCHOR) not in grid


def test_spacing_is_period():
    idx = _bdays("2020-01-01", "2026-12-31")
    grid = rebalance_dates(idx, 21)
    positions = idx.get_indexer(grid)
    assert set(positions[1:] - positions[:-1]) == {21}


def test_phase_is_independent_of_frame_start():
    full = _bdays("2010-01-01", "2026-12-31")
    short = _bdays("2023-03-15", "2026-12-31")
    g_full = rebalance_dates(full, 21)
    g_short = rebalance_dates(short, 21)
    after = pd.Timestamp("2023-06-01")
    assert list(g_full[g_full >= after]) == list(g_short[g_short >= after])


def test_legacy_phase_counts_from_first_bar():
    idx = _bdays("2023-03-15", "2026-12-31")
    grid = rebalance_dates(idx, 21, anchor=None)
    assert grid[0] == idx[0]
    assert len(grid) == len(idx[::21])


def test_live_strategies_share_the_grid():
    """A1's momentum and A2's two components re-rank on the same dates."""
    from strategies.portfolio_config import STOCK_STRATEGIES, ETF_STRATEGIES

    for key, registry in (
        ("stock_momentum", STOCK_STRATEGIES),
        ("low_volatility", STOCK_STRATEGIES),
        ("multi_asset_trend", ETF_STRATEGIES),
    ):
        assert registry[key]().rebalance_anchor == REBALANCE_ANCHOR
