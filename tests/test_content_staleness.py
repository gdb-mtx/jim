"""Equity cache staleness is "holds the last completed NYSE session" — nothing else."""

import pandas as pd
import pytest

import data.trading_dates as td
from data.pipeline import content_is_stale


def _frame(last: str) -> pd.DataFrame:
    idx = pd.bdate_range(end=last, periods=30)
    return pd.DataFrame({"SPY": 1.0}, index=idx)


@pytest.mark.parametrize("last_completed, cache_ends, stale", [
    ("2026-10-20", "2026-10-20", False),   # after the close, cache holds today's settled row
    ("2026-10-20", "2026-10-19", True),    # after the close, yesterday only -> refresh
    ("2026-10-19", "2026-10-19", False),   # during the session, yesterday is the last completed
    ("2026-10-19", "2026-10-16", True),    # Monday intraday, cache stopped Thursday
])
def test_equity_staleness_is_last_completed_session(monkeypatch, last_completed, cache_ends, stale):
    monkeypatch.setattr(td, "last_completed_session", lambda: last_completed)
    assert content_is_stale(_frame(cache_ends), asset_class="equity") is stale
