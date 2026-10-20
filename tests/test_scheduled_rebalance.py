"""Due-check for the scheduled 21-day rebalance (scripts/scheduled_rebalance.py).

Calendar-based since 2026-10-20: no price cache is read to decide due-ness.
"""

import pandas as pd
import pytest

from scripts import scheduled_rebalance as sr


def _journal(monkeypatch, entries):
    import execution.rebalance_log as rl
    monkeypatch.setattr(rl, "get_recent_rebalances", lambda limit=300: entries)


def test_rebalance_day_resolves_to_previous_session_grid():
    assert sr.expected_rebalance("2026-10-20") == ("2026-10-20", "2026-10-19")
    assert sr.expected_rebalance("2026-09-21") == ("2026-09-21", "2026-09-18")


def test_catch_up_window_then_give_up():
    assert sr.expected_rebalance("2026-10-23") == ("2026-10-20", "2026-10-19")
    assert sr.expected_rebalance("2026-10-30") is None


def test_due_on_the_day(monkeypatch):
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-09-22T18:50:00+00:00"}])
    ok, why = sr.is_due(1, "2026-10-20")
    assert ok and "grid 2026-10-19" in why


def test_not_due_once_journaled_after_the_grid_bar(monkeypatch):
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-10-20T19:12:00+00:00"}])
    ok, why = sr.is_due(1, "2026-10-21")
    assert not ok and "already rebalanced" in why


def test_rebalance_on_the_grid_date_itself_does_not_count(monkeypatch):
    """A 3 PM rebalance on the grid date traded the previous ranking."""
    _journal(monkeypatch, [{"account": 1, "timestamp": "2026-10-19T19:05:00+00:00"}])
    assert sr.is_due(1, "2026-10-20")[0]


def test_other_accounts_journal_is_ignored(monkeypatch):
    _journal(monkeypatch, [{"account": 2, "timestamp": "2026-10-20T19:12:00+00:00"}])
    assert sr.is_due(1, "2026-10-20")[0]


def test_live_calendar_matches_scorecard_bounds():
    from data.trading_dates import live_rebalance_dates
    assert live_rebalance_dates("2026-12-31") == [
        "2026-04-21", "2026-05-20", "2026-06-22", "2026-07-22", "2026-08-20",
        "2026-09-21", "2026-10-20", "2026-11-18", "2026-12-18",
    ]


def test_runner_refuses_a_stale_ranking(monkeypatch):
    """require_signal_asof blocks execution when the book's as-of date differs."""
    from types import SimpleNamespace
    import execution.rebalance_runner as rr
    monkeypatch.setattr(rr, "require_validated", lambda a: None)
    monkeypatch.setattr(rr, "AlpacaBroker", lambda account: SimpleNamespace(account=account))
    monkeypatch.setattr(rr, "RiskManager", lambda account: None)
    fake = SimpleNamespace(risk_check={}, position_mismatch=False, price_error=False, prices={},
                           orders=[1], signal_asof="2026-09-18")
    monkeypatch.setattr(rr, "compute_rebalance", lambda **kw: fake)
    executed = []
    monkeypatch.setattr(rr, "execute_rebalance", lambda b, r: executed.append(1))
    res = rr.rebalance_account(1, source="test", require_signal_asof="2026-10-19")
    assert res["status"] == "stale_ranking" and not executed


def test_post_close_warm_only_when_session_closed_and_bar_missing(monkeypatch):
    import data.trading_dates as td
    calls = []
    import data.sp500 as sp
    for name in ("download_sp500_prices", "download_spy", "download_vix"):
        monkeypatch.setattr(sp, name, lambda *a, _n=name, **k: calls.append(_n))
    monkeypatch.setattr(td, "last_completed_session", lambda: "2026-10-20")
    # before the close: nothing
    monkeypatch.setattr(td, "equity_session_closed_today", lambda: False)
    monkeypatch.setattr(sr, "cache_has_bar", lambda d: False)
    d = {}; sr.warm_caches_after_close(d); assert calls == [] and "warmed" not in d
    # after the close with the bar already present: nothing
    monkeypatch.setattr(td, "equity_session_closed_today", lambda: True)
    monkeypatch.setattr(sr, "cache_has_bar", lambda d: True)
    sr.warm_caches_after_close(d); assert calls == []
    # after the close, bar missing: all three loaders, S&P last
    monkeypatch.setattr(sr, "cache_has_bar", lambda d: False)
    sr.warm_caches_after_close(d)
    assert calls == ["download_spy", "download_vix", "download_sp500_prices"] and d["warmed"] == "2026-10-20"
