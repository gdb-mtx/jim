"""
Risk Manager — Fractional Kelly + 2% Rule + Drawdown Circuit Breakers.

This module enforces three layers of risk protection:
1. Kelly Criterion (fractional) determines position SIZE
2. The 2% rule caps maximum LOSS per trade
3. Circuit breakers halt trading at portfolio/strategy drawdown thresholds

See PLAN.md Section 3 (Kelly) and Section 5 (Constraints).
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class RiskLimits:
    """Risk management parameters."""
    max_loss_per_trade_pct: float = 0.02       # 2% max loss per trade
    kelly_fraction: float = 0.25                # Quarter-Kelly (conservative)
    portfolio_drawdown_halt: float = 0.15       # Halt all trading at -15%
    strategy_drawdown_halt: float = 0.10        # Halt strategy at -10%
    max_position_pct: float = 0.20              # No single position > 20% of portfolio


@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    symbol: str
    kelly_optimal_pct: float      # Full Kelly suggests this %
    kelly_fractional_pct: float   # Fractional Kelly (what we use)
    max_loss_capped_pct: float    # After applying 2% rule
    final_position_pct: float     # Final answer (min of all constraints)
    shares: int                   # Number of shares to buy
    dollar_amount: float          # Dollar value of position


class RiskManager:
    """Enforces all risk management rules."""

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self._equity_peak = 0.0
        self._strategy_peaks: dict[str, float] = {}
        self._halted = False
        self._halted_strategies: set[str] = set()

    def calculate_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        current_price: float,
        stop_loss_pct: float,
    ) -> PositionSize:
        """Calculate position size using Kelly + 2% rule.

        Args:
            symbol: Ticker symbol
            portfolio_value: Current total portfolio value
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade return (positive decimal)
            avg_loss: Average losing trade return (positive decimal, we negate)
            current_price: Current price per share
            stop_loss_pct: Stop loss distance as decimal (e.g., 0.05 = 5%)

        Returns:
            PositionSize with all sizing details
        """
        # Kelly Criterion: f* = (bp - q) / b
        if avg_loss == 0 or win_rate <= 0:
            kelly_full = 0.0
        else:
            b = avg_win / avg_loss  # Win/loss ratio
            p = win_rate
            q = 1 - p
            kelly_full = max((b * p - q) / b, 0)

        # Apply fractional Kelly
        kelly_frac = kelly_full * self.limits.kelly_fraction

        # Apply 2% max loss rule
        # If stop_loss_pct would cause > 2% portfolio loss, reduce position
        if stop_loss_pct > 0:
            max_position_from_loss_rule = self.limits.max_loss_per_trade_pct / stop_loss_pct
        else:
            max_position_from_loss_rule = kelly_frac

        # Take the most conservative of all constraints
        final_pct = min(
            kelly_frac,
            max_position_from_loss_rule,
            self.limits.max_position_pct,
        )

        dollar_amount = portfolio_value * final_pct
        shares = int(dollar_amount / current_price) if current_price > 0 else 0

        return PositionSize(
            symbol=symbol,
            kelly_optimal_pct=kelly_full,
            kelly_fractional_pct=kelly_frac,
            max_loss_capped_pct=max_position_from_loss_rule,
            final_position_pct=final_pct,
            shares=shares,
            dollar_amount=shares * current_price,
        )

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

                result["strategies_halted"][name] = name in self._halted_strategies

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
        else:
            self._halted = False
