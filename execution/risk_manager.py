"""
Risk Manager — Drawdown Monitor + Catastrophe Halt.

Design (AUDIT_MONTH2 C5 resolution, 2026-04-21):

- **-10% portfolio drawdown → dashboard alert.** Computed live in the
  `/api/portfolio/risk` endpoint (and surfaced in rebalance previews).
  No push notification, no blocking; the amber banner in
  `RiskStatusPanel` is the sole surface. Non-blocking by design.

- **-35% portfolio drawdown → catastrophe halt.** Latches a single
  persisted flag; requires manual reset via dashboard or
  `POST /api/portfolio/risk/reset?account=N`. Backstop for "something is
  catastrophically wrong that every other layer (SPY/BTC filters,
  vol-scaling) missed."

- **Peak is derived from daily snapshots, not persisted.** `data/snapshots.py`
  already writes one equity row per trading day per account; `compute_drawdown`
  reads that series and takes `max(snapshot_max, current_equity)`. Removes the
  stale-peak failure mode entirely — no matter how long between dashboard
  visits, the peak is always accurate.

State file schema: `{"halted": bool}`. That's it.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("fire.risk")

STATE_DIR = Path(__file__).parent.parent / "data" / "risk_state"


@dataclass
class RiskLimits:
    """Drawdown thresholds (applied as `dd <= -threshold`)."""
    portfolio_drawdown_alert: float = 0.10   # Dashboard banner, non-blocking
    portfolio_drawdown_halt: float = 0.35    # Catastrophe kill-switch


@dataclass
class DrawdownState:
    """Pure derivation from (current_equity, snapshot history)."""
    drawdown: float       # Negative float, e.g. -0.08 for -8%
    equity_peak: float
    alert_active: bool    # dd <= -alert_threshold


def compute_drawdown(
    account: int,
    current_equity: float,
    limits: RiskLimits | None = None,
    equity_history=None,
) -> DrawdownState:
    """Derive current drawdown state from daily snapshots + live equity.

    No persistence, no side effects. Peak is `max(snapshot_history_max,
    current_equity)` — snapshots are the source of truth for historical
    highs, and `current_equity` handles the intra-day case where the book
    is at a new high before the next snapshot write.

    Args:
        account: Account number (used to load snapshots if `equity_history`
            is not provided).
        current_equity: Live portfolio value (Alpaca).
        limits: Threshold overrides.
        equity_history: Optional pre-loaded equity Series or DataFrame
            (tests pass this to avoid touching the filesystem). If None,
            snapshots are loaded via `data.snapshots.load_snapshots`.
    """
    limits = limits or RiskLimits()

    if equity_history is None:
        from data.snapshots import load_snapshots
        try:
            equity_history = load_snapshots(account)
        except Exception as e:
            log.warning(f"load_snapshots({account}) failed: {e}; using current equity as peak")
            equity_history = None

    snapshot_peak = 0.0
    if equity_history is not None and len(equity_history) > 0:
        eq = equity_history["equity"] if "equity" in getattr(equity_history, "columns", []) else equity_history
        eq = eq.dropna()
        if len(eq) > 0:
            snapshot_peak = float(eq.max())

    peak = max(snapshot_peak, current_equity)
    dd = (current_equity - peak) / peak if peak > 0 else 0.0
    return DrawdownState(
        drawdown=dd,
        equity_peak=peak,
        alert_active=dd <= -limits.portfolio_drawdown_alert,
    )


class RiskManager:
    """Minimal halt-latch.

    The only persisted state is a single `halted` boolean. All drawdown
    logic is in `compute_drawdown` (pure function).

    Args:
        account: Account number for state file isolation (1-4)
        persist: Whether to save/load halt state from disk
        limits: Threshold overrides (used by `check_and_latch_halt`)
    """

    def __init__(
        self,
        account: int | None = None,
        persist: bool = True,
        limits: RiskLimits | None = None,
    ):
        self._account = account
        self._persist = persist
        self.limits = limits or RiskLimits()
        self._halted = False

        if self._persist:
            self._load_state()

    @property
    def halted(self) -> bool:
        return self._halted

    @property
    def _state_file(self) -> Path:
        suffix = f"_acct{self._account}" if self._account else ""
        return STATE_DIR / f"circuit_breaker{suffix}.json"

    def _load_state(self):
        """Load halt state. Corrupted file → fail-safe (halted=True).

        Better to force a manual review than to silently lose a halt.
        """
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            self._halted = bool(data.get("halted", False))
        except (json.JSONDecodeError, OSError) as e:
            self._halted = True
            log.error(
                f"Risk state corrupted ({self._state_file}): {e}. "
                "Defaulting to HALTED (fail-safe). Reset manually via API."
            )

    def _save_state(self):
        """Atomic write — tmp file + rename."""
        if not self._persist:
            return
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps({"halted": self._halted}, indent=2))
            os.rename(str(tmp), str(self._state_file))
        except OSError as e:
            log.warning(f"Could not save risk state: {e}")

    def check_and_latch_halt(self, drawdown: float, equity_peak: float, current_equity: float) -> bool:
        """If drawdown breaches the halt threshold, latch. Idempotent.

        Called from both `compute_rebalance` (blocks trading) and the
        `/risk` endpoint (keeps dashboard state accurate between
        rebalances). Extra calls on an already-halted account are no-ops
        — the file is only rewritten on the transition.

        Returns the latched halt state after the call.
        """
        if drawdown <= -self.limits.portfolio_drawdown_halt and not self._halted:
            self._halted = True
            log.error(
                f"CATASTROPHE HALT (acct {self._account}): "
                f"DD {drawdown:.1%} <= -{self.limits.portfolio_drawdown_halt:.0%}. "
                f"Peak ${equity_peak:,.0f}, current ${current_equity:,.0f}. "
                "Manual reset required."
            )
            self._save_state()
        return self._halted

    def can_trade(self) -> bool:
        """Trading is allowed unless the catastrophe halt is active."""
        return not self._halted

    def reset_halt(self):
        """Manually clear the catastrophe halt after review."""
        if self._halted:
            log.info(f"Manual halt reset (acct {self._account})")
        self._halted = False
        self._save_state()
