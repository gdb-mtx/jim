"""
Risk Manager — Drawdown Circuit Breakers.

Position sizing is handled at the strategy layer (equal-weight top-N,
blend weights, vol-scaling where applicable) — this module does NOT size
positions. Historical Kelly + 2% rule + max_position_pct code was removed
2026-04-21 (AUDIT_MONTH2 C7 resolution, R12 cleanup) — those layers were
dead code and, in the case of max_position_pct=20%, actively buggy against
A4's top-2 crypto design.

Circuit breaker state (peaks, halts) persists to disk so server restarts
don't reset safety protections.

See PLAN.md Section 3.5 (Drawdown Circuit Breakers) — though the design
itself is under review; see AUDIT_MONTH2 C5.
"""

import json
import logging
import os
from pathlib import Path

import pandas as pd
import numpy as np
from dataclasses import dataclass

log = logging.getLogger("fire.risk")

STATE_DIR = Path(__file__).parent.parent / "data" / "risk_state"


@dataclass
class RiskLimits:
    """Circuit-breaker thresholds. (Position sizing lives in strategies.)"""
    portfolio_drawdown_halt: float = 0.15       # Halt all trading at -15%
    strategy_drawdown_halt: float = 0.10        # Halt strategy at -10%


class RiskManager:
    """Enforces all risk management rules.

    Args:
        limits: Risk parameters (uses defaults if None)
        account: Account number for state file isolation (1-4)
        persist: Whether to save/load state from disk
    """

    def __init__(
        self,
        limits: RiskLimits | None = None,
        account: int | None = None,
        persist: bool = True,
    ):
        self.limits = limits or RiskLimits()
        self._account = account
        self._persist = persist
        self._equity_peak = 0.0
        self._strategy_peaks: dict[str, float] = {}
        self._halted = False
        self._halted_strategies: set[str] = set()

        if self._persist:
            self._load_state()

    @property
    def _state_file(self) -> Path:
        suffix = f"_acct{self._account}" if self._account else ""
        return STATE_DIR / f"circuit_breaker{suffix}.json"

    def _load_state(self):
        """Load circuit breaker state from disk.

        Fail-safe: if the state file exists but is corrupted, default to
        halted=True. Better to block trading until manually reset than to
        silently lose a halt after a crash.
        """
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text())
            self._equity_peak = data.get("equity_peak", 0.0)
            self._strategy_peaks = data.get("strategy_peaks", {})
            self._halted = data.get("halted", False)
            self._halted_strategies = set(data.get("halted_strategies", []))
            log.info(f"Loaded circuit breaker state from {self._state_file}")
        except (json.JSONDecodeError, OSError) as e:
            self._halted = True
            log.error(
                f"Circuit breaker state corrupted ({self._state_file}): {e}. "
                "Defaulting to HALTED (fail-safe). Reset manually via API."
            )

    def _save_state(self):
        """Save circuit breaker state to disk (atomic write)."""
        if not self._persist:
            return
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "equity_peak": self._equity_peak,
                "strategy_peaks": self._strategy_peaks,
                "halted": self._halted,
                "halted_strategies": list(self._halted_strategies),
            }
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            os.rename(str(tmp), str(self._state_file))
        except OSError as e:
            log.warning(f"Could not save circuit breaker state: {e}")

    def check_circuit_breakers(
        self,
        current_portfolio_value: float,
        strategy_values: dict[str, float] | None = None,
    ) -> dict:
        """Check drawdown circuit breakers.

        Args:
            current_portfolio_value: Current total portfolio value
            strategy_values: Dict of strategy_name -> current_value

        Returns:
            Dict with halt status for portfolio and each strategy
        """
        # Update portfolio peak
        self._equity_peak = max(self._equity_peak, current_portfolio_value)

        # Check portfolio-level circuit breaker
        if self._equity_peak > 0:
            portfolio_dd = (current_portfolio_value - self._equity_peak) / self._equity_peak
            if portfolio_dd <= -self.limits.portfolio_drawdown_halt:
                self._halted = True
                log.warning(f"CIRCUIT BREAKER: Portfolio halted at {portfolio_dd:.1%} drawdown")

        result = {
            "portfolio_halted": self._halted,
            "portfolio_drawdown": portfolio_dd if self._equity_peak > 0 else 0,
            "equity_peak": self._equity_peak,
            "strategies_halted": {},
        }

        # Check strategy-level circuit breakers
        if strategy_values:
            for name, value in strategy_values.items():
                if name not in self._strategy_peaks:
                    self._strategy_peaks[name] = value
                self._strategy_peaks[name] = max(self._strategy_peaks[name], value)

                if self._strategy_peaks[name] > 0:
                    strategy_dd = (value - self._strategy_peaks[name]) / self._strategy_peaks[name]
                    if strategy_dd <= -self.limits.strategy_drawdown_halt:
                        self._halted_strategies.add(name)
                        log.warning(f"CIRCUIT BREAKER: Strategy '{name}' halted at {strategy_dd:.1%} drawdown")

                result["strategies_halted"][name] = name in self._halted_strategies

        self._save_state()
        return result

    def can_trade(self, strategy_name: str | None = None) -> bool:
        """Check if trading is allowed.

        Args:
            strategy_name: Optional strategy to check

        Returns:
            True if trading is allowed
        """
        if self._halted:
            return False
        if strategy_name and strategy_name in self._halted_strategies:
            return False
        return True

    def reset_halt(self, strategy_name: str | None = None):
        """Manually reset a halt after review.

        Args:
            strategy_name: Specific strategy to reset, or None for portfolio
        """
        if strategy_name:
            self._halted_strategies.discard(strategy_name)
            log.info(f"Circuit breaker reset for strategy: {strategy_name}")
        else:
            self._halted = False
            log.info("Portfolio circuit breaker reset")
        self._save_state()
