"""Tests for live vol-scaling (AUDIT_MONTH2 C4)."""

import math
from unittest.mock import patch

import numpy as np
import pandas as pd

from execution.vol_scaling import compute_live_vol_scalar
from strategies.portfolio import apply_vol_scaling


def _synthetic_equity(n_days: int, daily_vol: float, seed: int = 42) -> pd.DataFrame:
    """Build a snapshot-shaped DataFrame with known daily return vol."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, daily_vol, size=n_days)
    equity = 100_000 * np.cumprod(1 + returns)
    dates = pd.bdate_range("2026-01-01", periods=n_days)
    return pd.DataFrame(
        {"equity": equity, "cash": 0.0, "daily_pnl": 0.0, "positions_count": 0},
        index=pd.DatetimeIndex(dates, name="date"),
    )


def test_cold_start_returns_unit_scalar():
    """With fewer rows than min_history_days+1, falls back to 1.0."""
    df = _synthetic_equity(n_days=10, daily_vol=0.01)
    with patch("execution.vol_scaling.load_snapshots", return_value=df):
        scalar, diag = compute_live_vol_scalar(account_id=2, min_history_days=21)
    assert scalar == 1.0
    assert diag["fallback_reason"] == "cold_start"


def test_empty_snapshots_returns_unit_scalar():
    df = pd.DataFrame(
        columns=["equity", "cash", "daily_pnl", "positions_count"],
        index=pd.DatetimeIndex([], name="date"),
    )
    with patch("execution.vol_scaling.load_snapshots", return_value=df):
        scalar, diag = compute_live_vol_scalar(account_id=2)
    assert scalar == 1.0
    assert diag["fallback_reason"] == "cold_start"


def test_high_vol_clips_to_floor():
    """Vol 10x target → scalar clipped to floor."""
    # daily 10% ~ annualized ~159% vol, target 15% → raw scalar ~0.09 → floor 0.5
    df = _synthetic_equity(n_days=60, daily_vol=0.10, seed=1)
    with patch("execution.vol_scaling.load_snapshots", return_value=df):
        scalar, diag = compute_live_vol_scalar(
            account_id=2, vol_target=0.15, scalar_floor=0.5, scalar_cap=1.0
        )
    assert scalar == 0.5
    assert diag["raw_scalar"] < 0.5


def test_low_vol_clips_to_cap():
    """Vol much below target → scalar clipped to cap."""
    # daily 0.1% ~ annualized ~1.6% vol, target 15% → raw scalar ~9 → cap 1.0
    df = _synthetic_equity(n_days=60, daily_vol=0.001, seed=2)
    with patch("execution.vol_scaling.load_snapshots", return_value=df):
        scalar, diag = compute_live_vol_scalar(
            account_id=2, vol_target=0.15, scalar_floor=0.5, scalar_cap=1.0
        )
    assert scalar == 1.0
    assert diag["raw_scalar"] > 1.0


def test_matches_backtest_apply_vol_scaling():
    """Live scalar on a date must equal backtest apply_vol_scaling scalar on
    the same date. Both use the same EWMA(halflife) on the same returns
    series. The backtest lags its output by 1 day (.shift(1)); we compute
    from data through T-1 so the lag is implicit.
    """
    df = _synthetic_equity(n_days=120, daily_vol=0.012, seed=3)

    # Backtest path: apply_vol_scaling returns scaled returns; we want the
    # scalar itself. Rebuild the clip math to extract it. apply_vol_scaling
    # at T = 119 uses EWMA through T-1 (shift(1)), same as our live compute.
    returns = df["equity"].pct_change().dropna()
    ewma_var = returns.ewm(halflife=21).var()
    realized_vol = np.sqrt(ewma_var) * np.sqrt(252)
    raw = 0.15 / realized_vol.replace(0, np.nan)
    backtest_scalar_series = raw.clip(lower=0.5, upper=1.0).shift(1).fillna(1.0)
    backtest_scalar_today = float(backtest_scalar_series.iloc[-1])

    # Live path: data through T-1, so slice df up to penultimate row.
    df_live = df.iloc[:-1]
    with patch("execution.vol_scaling.load_snapshots", return_value=df_live):
        live_scalar, diag = compute_live_vol_scalar(
            account_id=2,
            vol_target=0.15,
            vol_halflife=21,
            scalar_floor=0.5,
            scalar_cap=1.0,
        )

    assert abs(live_scalar - backtest_scalar_today) < 1e-6


def test_apply_vol_scaling_default_cap_is_one():
    """Sim/live parity — backtest default cap must match live cap (1.0)."""
    import inspect
    sig = inspect.signature(apply_vol_scaling)
    assert sig.parameters["scalar_cap"].default == 1.0
