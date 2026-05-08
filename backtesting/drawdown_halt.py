"""Backtest halt simulation — sim/live parity for the -35% catastrophe halt.

Post-hoc halt-and-hold layer over a returns series. Halt is permanent within a
single sim run (no manual reset inside a backtest), so once it trips returns go
flat for the remainder of the window — the conservative honest simulation.

For the -35% threshold this is a no-op on every current OOS window (deepest
observed: A4 -11.4%; combined -7.0%). Module exists so the parity gap is closed
in code and stress-test scenarios with lower thresholds are ready.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HaltSimulation:
    """Result of a halt-and-hold simulation on a returns series."""
    returns: pd.Series          # Adjusted returns: 0.0 on/after halt day
    halt_date: pd.Timestamp | None  # First day DD <= -halt_threshold, or None
    max_drawdown_pre_halt: float    # Worst DD observed up to (and including) halt_date
    halt_threshold: float

    @property
    def halt_fired(self) -> bool:
        return self.halt_date is not None


def simulate_drawdown_halt(
    returns: pd.Series,
    halt_threshold: float = 0.35,
) -> HaltSimulation:
    """Apply a catastrophe-halt layer to a daily returns series.

    Args:
        returns: Daily returns (not cumulative). NaN and zero values are
            treated as flat days.
        halt_threshold: Drawdown magnitude that trips the halt (positive
            float; default 0.35 matches the live kill-switch).

    Returns:
        HaltSimulation with the adjusted returns + metadata.

    Halt logic: walk the cumulative equity curve day-by-day. Track running
    peak. If `(equity - peak) / peak <= -halt_threshold`, flag that day as
    the halt date; all subsequent returns are zeroed. The halt day itself
    keeps its realized return (the halt latches at end-of-day).
    """
    if len(returns) == 0:
        return HaltSimulation(
            returns=returns.copy(),
            halt_date=None,
            max_drawdown_pre_halt=0.0,
            halt_threshold=halt_threshold,
        )

    r = returns.fillna(0.0).astype(float)
    equity = (1.0 + r).cumprod()
    # Implicit pre-start peak of 1.0 — otherwise the first down-day sets the
    # peak equal to its own depressed equity and DD never gets computed
    # against the starting value.
    peak = equity.cummax().clip(lower=1.0)
    dd = (equity - peak) / peak

    halt_mask = dd <= -halt_threshold
    if not halt_mask.any():
        return HaltSimulation(
            returns=returns.copy(),
            halt_date=None,
            max_drawdown_pre_halt=float(dd.min()),
            halt_threshold=halt_threshold,
        )

    halt_date = halt_mask.idxmax()  # First True
    halt_pos = equity.index.get_loc(halt_date)

    adjusted = r.copy()
    # Zero all returns strictly AFTER the halt day (halt day itself keeps
    # its return — the breach is detected at EOD).
    if halt_pos + 1 < len(adjusted):
        adjusted.iloc[halt_pos + 1:] = 0.0

    max_dd_pre = float(dd.iloc[: halt_pos + 1].min())

    return HaltSimulation(
        returns=adjusted,
        halt_date=halt_date,
        max_drawdown_pre_halt=max_dd_pre,
        halt_threshold=halt_threshold,
    )


def would_halt_have_fired(
    returns: pd.Series,
    halt_threshold: float = 0.35,
) -> bool:
    """Cheap yes/no check — useful for sim/live parity assertions."""
    return simulate_drawdown_halt(returns, halt_threshold).halt_fired
