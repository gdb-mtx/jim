"""Due-check for the scheduled 21-day rebalance (scripts/scheduled_rebalance.py)."""

import pandas as pd
import pytest

from scripts import scheduled_rebalance as sr

GRID = pd.Timestamp("2026-09-18")


def _journal(monkeypatch, entries):
    import execution.rebalance_log as rl
    monkeypatch.setattr(rl, "get_recent_rebalances", lambda limit=300: entries)


@pytest.fixture
def today(monkeypatch):
    def _set(date: str):
        monkeypatch.setattr(sr, "today_et", lambda: date)
    return _set


def test_due_on_the_day_after_the_grid_date(today, monkeypatch):
    today("2026-09-21")
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-08-28T17:40:00+00:00"}])
    ok, why = sr.is_due(1, GRID)
    assert ok and "not yet traded" in why


def test_not_due_once_journaled_after_the_grid_date(today, monkeypatch):
    today("2026-09-22")
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-09-21T19:12:00+00:00"}])
    ok, why = sr.is_due(1, GRID)
    assert not ok and "already rebalanced" in why


def test_rebalance_on_the_grid_date_itself_does_not_count(today, monkeypatch):
    """A 3 PM rebalance on the grid date traded the previous ranking."""
    today("2026-09-21")
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-09-18T19:05:00+00:00"}])
    ok, _ = sr.is_due(1, GRID)
    assert ok


def test_catch_up_window_then_give_up(today, monkeypatch):
    _journal(monkeypatch, [])
    today("2026-09-24")
    assert sr.is_due(1, GRID)[0]
    today("2026-09-30")
    ok, why = sr.is_due(1, GRID)
    assert not ok and "outside catch-up window" in why


def test_other_accounts_journal_is_ignored(today, monkeypatch):
    today("2026-09-21")
    _journal(monkeypatch, [{"account": 2, "timestamp": "2026-09-21T19:12:00+00:00"}])
    assert sr.is_due(1, GRID)[0]


def test_live_calendar_matches_scorecard_bounds():
    from data.trading_dates import live_rebalance_dates
    assert live_rebalance_dates("2026-12-31")[:6] == [
        "2026-04-21", "2026-05-20", "2026-06-22", "2026-07-22", "2026-08-20", "2026-09-21",
    ]
