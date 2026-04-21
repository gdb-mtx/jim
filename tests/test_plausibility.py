"""Tests for data/plausibility.py — per-ticker value-plausibility layer.

Guards the AUDIT_MONTH2 S5 defensive layer: per-ticker min/max bands with
write-time assertions, read-time cache-vs-live cross-validation, and
persistent state tracking.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from data import plausibility


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect plausibility state file to a tmp path so tests don't touch
    the real data/risk_state/plausibility_state.json."""
    state_path = tmp_path / "plausibility_state.json"
    monkeypatch.setattr(plausibility, "STATE_PATH", state_path)
    return state_path


# ---- Write-time assertions ----


def test_good_btc_passes(tmp_state):
    btc = pd.Series([60_000, 75_000, 80_000, 75_312], name="BTC-USD")
    plausibility.assert_plausible(btc, "BTC-USD")  # no raise
    state = plausibility.get_state()
    assert "BTC-USD" in state
    assert "last_success_at" in state["BTC-USD"]
    assert state["BTC-USD"]["last_success_n_obs"] == 4


def test_wrong_btc_values_raise(tmp_state):
    # Simulates the 2026-04-21 bug: yfinance returned $9-$29 range
    bad = pd.Series([9.0, 20.5, 24.5, 29.0], name="BTC-USD")
    with pytest.raises(plausibility.PlausibilityError, match="below expected floor"):
        plausibility.assert_plausible(bad, "BTC-USD")
    state = plausibility.get_state()
    assert "BTC-USD" in state
    assert "last_failure_at" in state["BTC-USD"]
    assert state["BTC-USD"]["last_failure_obs_max"] == 29.0


def test_above_cap_raises(tmp_state):
    # SPY min 50, max 2000 — values all above $2000
    way_too_high = pd.Series([3000, 3500, 4000], name="SPY")
    with pytest.raises(plausibility.PlausibilityError, match="above expected cap"):
        plausibility.assert_plausible(way_too_high, "SPY")


def test_unknown_ticker_passes_silently(tmp_state):
    # No band for this symbol → no check, no state written
    plausibility.assert_plausible(pd.Series([0.01, 0.02]), "UNKNOWN-TICKER-XYZ")
    assert plausibility.get_state() == {}


def test_nan_only_series_does_not_raise(tmp_state):
    # All-NaN isn't a plausibility failure on its own; coverage checks
    # handle missing data. assert_plausible should pass silently +
    # record a success with n_obs=0.
    all_nan = pd.Series([float("nan")] * 5, name="BTC-USD")
    plausibility.assert_plausible(all_nan, "BTC-USD")
    state = plausibility.get_state()
    assert state["BTC-USD"]["last_success_n_obs"] == 0


def test_vix_bands_match_history(tmp_state):
    # VIX: 5-100. Actual historical VIX range spot-checked:
    #   2008 peak ~80, 2020 peak ~85, typical range 12-25
    normal_vix = pd.Series([15.0, 20.0, 35.0, 85.0], name="^VIX")
    plausibility.assert_plausible(normal_vix, "^VIX")  # no raise


def test_assert_plausible_df_checks_all_columns(tmp_state):
    # DataFrame with 3 columns — BTC good, ETH good, SPY bad
    df = pd.DataFrame({
        "BTC-USD": [50_000, 60_000, 70_000],
        "ETH-USD": [3_000, 3_500, 4_000],
        "SPY": [10.0, 15.0, 20.0],  # Below SPY floor of $50
    })
    with pytest.raises(plausibility.PlausibilityError, match="SPY"):
        plausibility.assert_plausible_df(df)


def test_assert_plausible_df_skips_unknown_columns(tmp_state):
    # S&P 500 stocks have no bands — should silently pass
    df = pd.DataFrame({
        "AAPL": [150.0, 160.0],
        "MSFT": [300.0, 310.0],
        "NVDA": [800.0, 900.0],
    })
    plausibility.assert_plausible_df(df)
    # Check: no state entries written for these unknown tickers
    state = plausibility.get_state()
    assert "AAPL" not in state
    assert "MSFT" not in state


# ---- Read-time cross-validation ----


def test_cross_validate_within_threshold(tmp_state):
    # cached 706, live 710 → 0.57% divergence, within 5% threshold
    cached = pd.Series([700, 702, 704, 706], name="SPY")
    result = plausibility.cross_validate_last_close(
        cached, "SPY", live_price=710.0, threshold_pct=0.05
    )
    assert result.within_threshold is True
    assert result.divergence_pct < 0.01
    # Should NOT record state for successful cross-validations
    assert plausibility.get_state() == {}


def test_cross_validate_divergence_recorded(tmp_state):
    # cached 706, live 400 → 43% divergence, way outside threshold
    cached = pd.Series([700, 702, 704, 706], name="SPY")
    result = plausibility.cross_validate_last_close(
        cached, "SPY", live_price=400.0, threshold_pct=0.05
    )
    assert result.within_threshold is False
    assert 0.40 < result.divergence_pct < 0.45
    state = plausibility.get_state()
    assert "SPY" in state
    assert state["SPY"]["last_divergence_cached"] == 706.0
    assert state["SPY"]["last_divergence_live"] == 400.0


def test_cross_validate_empty_cache_passes(tmp_state):
    # Empty cache shouldn't trigger divergence — coverage layer handles empty
    empty = pd.Series([], dtype=float, name="SPY")
    result = plausibility.cross_validate_last_close(empty, "SPY", live_price=700.0)
    assert result.within_threshold is True


# ---- State / active-issues logic ----


def test_has_active_issues_unresolved_failure(tmp_state):
    # Write a failure; no subsequent success → unresolved
    bad = pd.Series([9.0, 20.0], name="BTC-USD")
    with pytest.raises(plausibility.PlausibilityError):
        plausibility.assert_plausible(bad, "BTC-USD")
    active = plausibility.has_active_issues()
    assert len(active) == 1
    assert active[0]["ticker"] == "BTC-USD"
    assert active[0]["unresolved_failure"] is True


def test_has_active_issues_resolved_after_success(tmp_state):
    # Failure followed by success → no longer active (success is newer)
    bad = pd.Series([9.0, 20.0], name="BTC-USD")
    with pytest.raises(plausibility.PlausibilityError):
        plausibility.assert_plausible(bad, "BTC-USD")

    # Force a newer timestamp via monkey-patching the internal now helper
    # so we don't rely on wall-clock gaps between operations.
    import datetime as dt
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)
    with patch.object(plausibility, "_now_iso", return_value=later.isoformat()):
        good = pd.Series([60_000, 75_000, 80_000], name="BTC-USD")
        plausibility.assert_plausible(good, "BTC-USD")

    active = plausibility.has_active_issues()
    assert len(active) == 0  # Resolved


def test_has_active_issues_recent_divergence(tmp_state):
    cached = pd.Series([700.0, 706.0], name="SPY")
    plausibility.cross_validate_last_close(cached, "SPY", live_price=100.0)
    active = plausibility.has_active_issues()
    assert len(active) == 1
    assert active[0]["recent_divergence"] is True


def test_has_active_issues_old_divergence_is_not_active(tmp_state):
    # Divergence >24h ago (the default TTL) should not be "active"
    import datetime as dt
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=48)
    with patch.object(plausibility, "_now_iso", return_value=old.isoformat()):
        cached = pd.Series([700.0, 706.0], name="SPY")
        plausibility.cross_validate_last_close(cached, "SPY", live_price=100.0)
    active = plausibility.has_active_issues()
    assert len(active) == 0


def test_state_persisted_across_calls(tmp_state):
    # Write failure, read it back via get_state
    bad = pd.Series([9.0, 20.0], name="BTC-USD")
    with pytest.raises(plausibility.PlausibilityError):
        plausibility.assert_plausible(bad, "BTC-USD")
    # New function call — state should be there
    state = plausibility.get_state()
    assert "BTC-USD" in state
    assert "last_failure_reason" in state["BTC-USD"]


def test_corrupted_state_file_treated_as_empty(tmp_state):
    tmp_state.write_text("{ not valid json")
    assert plausibility.get_state() == {}
    assert plausibility.has_active_issues() == []
