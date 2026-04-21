"""Tests for the risk manager.

Post-simplification (AUDIT_MONTH2 C5, 2026-04-21 afternoon):
  - `compute_drawdown` is pure — peak derived from daily snapshots + live
    equity, no persistence.
  - `RiskManager` only latches the -35% catastrophe halt. State file
    schema: `{"halted": bool}`.
  - The -10% alert is surfaced in `DrawdownState.alert_active` for the
    dashboard banner; it does not persist and does not block trading.
"""

import json
from unittest.mock import patch

import pandas as pd

from execution.risk_manager import (
    DrawdownState,
    RiskLimits,
    RiskManager,
    compute_drawdown,
)


def _hist(values: list[float]) -> pd.DataFrame:
    """Build a tiny snapshot-shaped DataFrame for compute_drawdown tests."""
    idx = pd.bdate_range(start="2026-03-01", periods=len(values))
    return pd.DataFrame({"equity": values}, index=idx)


# ── compute_drawdown (pure derivation) ──────────────────────────────────


def test_compute_drawdown_at_peak_is_zero():
    hist = _hist([100_000, 102_000, 105_000])
    s = compute_drawdown(account=1, current_equity=105_000, equity_history=hist)
    assert s.equity_peak == 105_000
    assert s.drawdown == 0.0
    assert s.alert_active is False


def test_compute_drawdown_uses_max_of_snapshot_and_current():
    """Current equity is a new high → peak reflects it immediately."""
    hist = _hist([100_000, 102_000, 105_000])
    s = compute_drawdown(account=1, current_equity=110_000, equity_history=hist)
    assert s.equity_peak == 110_000
    assert s.drawdown == 0.0


def test_compute_drawdown_alert_fires_below_10pct():
    hist = _hist([100_000, 108_000])
    s = compute_drawdown(account=1, current_equity=96_000, equity_history=hist)
    # Peak 108k, current 96k → DD ≈ -11.1%
    assert s.equity_peak == 108_000
    assert s.drawdown < -0.10
    assert s.alert_active is True


def test_compute_drawdown_no_alert_above_threshold():
    hist = _hist([100_000, 108_000])
    s = compute_drawdown(account=1, current_equity=100_000, equity_history=hist)
    # DD ≈ -7.4%, below threshold
    assert s.alert_active is False


def test_compute_drawdown_empty_history_falls_back_to_current():
    """Fresh account with no snapshots: peak = current, DD = 0."""
    hist = _hist([])
    s = compute_drawdown(account=1, current_equity=100_000, equity_history=hist)
    assert s.equity_peak == 100_000
    assert s.drawdown == 0.0


def test_compute_drawdown_accepts_series_not_just_df():
    idx = pd.bdate_range(start="2026-03-01", periods=3)
    series = pd.Series([100_000, 108_000, 105_000], index=idx)
    s = compute_drawdown(account=1, current_equity=96_000, equity_history=series)
    assert s.equity_peak == 108_000
    assert s.drawdown < -0.10


def test_compute_drawdown_respects_custom_alert_threshold():
    hist = _hist([100_000])
    s = compute_drawdown(
        account=1,
        current_equity=96_000,
        equity_history=hist,
        limits=RiskLimits(portfolio_drawdown_alert=0.05, portfolio_drawdown_halt=0.30),
    )
    # DD -4% vs 5% threshold → no alert
    assert s.alert_active is False
    s2 = compute_drawdown(
        account=1,
        current_equity=94_000,
        equity_history=hist,
        limits=RiskLimits(portfolio_drawdown_alert=0.05, portfolio_drawdown_halt=0.30),
    )
    # DD -6% vs 5% threshold → alert
    assert s2.alert_active is True


# ── RiskManager halt latch ──────────────────────────────────────────────


def test_halt_latches_at_threshold():
    rm = RiskManager(persist=False)
    assert rm.can_trade()
    latched = rm.check_and_latch_halt(drawdown=-0.36, equity_peak=100_000, current_equity=64_000)
    assert latched is True
    assert rm.halted is True
    assert not rm.can_trade()


def test_halt_does_not_fire_at_30pct():
    rm = RiskManager(persist=False)
    latched = rm.check_and_latch_halt(drawdown=-0.30, equity_peak=100_000, current_equity=70_000)
    assert latched is False
    assert rm.halted is False
    assert rm.can_trade()


def test_halt_is_idempotent():
    """Repeated calls on an already-halted manager don't re-log or re-save."""
    rm = RiskManager(persist=False)
    rm.check_and_latch_halt(-0.40, 100_000, 60_000)
    assert rm.halted is True
    # Second call: still halted, still can't trade, no error
    rm.check_and_latch_halt(-0.40, 100_000, 60_000)
    assert rm.halted is True


def test_reset_halt_clears_latch():
    rm = RiskManager(persist=False)
    rm.check_and_latch_halt(-0.40, 100_000, 60_000)
    rm.reset_halt()
    assert rm.halted is False
    assert rm.can_trade()


def test_state_persistence(tmp_path):
    state_dir = tmp_path / "risk_state"
    with patch("execution.risk_manager.STATE_DIR", state_dir):
        rm1 = RiskManager(account=1, persist=True)
        rm1.check_and_latch_halt(-0.40, 100_000, 60_000)

        rm2 = RiskManager(account=1, persist=True)
        assert rm2.halted is True
        assert not rm2.can_trade()

        # Different account independent
        rm3 = RiskManager(account=2, persist=True)
        assert rm3.halted is False


def test_state_file_schema(tmp_path):
    """State file contains only `halted` — no more peak / alert_active keys."""
    state_dir = tmp_path / "risk_state"
    with patch("execution.risk_manager.STATE_DIR", state_dir):
        rm = RiskManager(account=1, persist=True)
        rm.check_and_latch_halt(-0.40, 100_000, 60_000)

        data = json.loads((state_dir / "circuit_breaker_acct1.json").read_text())
        assert set(data.keys()) == {"halted"}
        assert data["halted"] is True


def test_corrupted_state_fails_safe(tmp_path):
    state_dir = tmp_path / "risk_state"
    state_dir.mkdir(parents=True)
    (state_dir / "circuit_breaker_acct1.json").write_text("garbage {{{")

    with patch("execution.risk_manager.STATE_DIR", state_dir):
        rm = RiskManager(account=1, persist=True)
        assert rm.halted is True
        assert not rm.can_trade()
