"""Tests for the risk manager — circuit breakers, Kelly sizing, persistence."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from execution.risk_manager import RiskManager, RiskLimits


def test_kelly_sizing_basic():
    """Kelly criterion produces reasonable position sizes."""
    rm = RiskManager(persist=False)
    result = rm.calculate_position_size(
        symbol="AAPL",
        portfolio_value=100_000,
        win_rate=0.55,
        avg_win=0.10,
        avg_loss=0.05,
        current_price=150.0,
        stop_loss_pct=0.05,
    )
    assert result.final_position_pct > 0
    assert result.final_position_pct <= 0.20  # max_position_pct cap
    assert result.shares > 0
    assert result.dollar_amount > 0


def test_kelly_zero_edge():
    """Zero win rate or zero avg_loss produces zero sizing."""
    rm = RiskManager(persist=False)
    result = rm.calculate_position_size(
        symbol="TEST",
        portfolio_value=100_000,
        win_rate=0.0,
        avg_win=0.10,
        avg_loss=0.05,
        current_price=50.0,
        stop_loss_pct=0.05,
    )
    assert result.kelly_optimal_pct == 0.0
    assert result.shares == 0


def test_circuit_breaker_triggers():
    """Portfolio circuit breaker fires at -15% drawdown."""
    rm = RiskManager(persist=False)

    # Set peak
    rm.check_circuit_breakers(100_000)
    assert rm.can_trade()

    # Drop 14% — still OK
    rm.check_circuit_breakers(86_000)
    assert rm.can_trade()

    # Drop 16% — halted
    rm.check_circuit_breakers(84_000)
    assert not rm.can_trade()


def test_strategy_circuit_breaker():
    """Strategy-level circuit breaker fires independently."""
    rm = RiskManager(persist=False)
    rm.check_circuit_breakers(100_000, {"momentum": 50_000})
    assert rm.can_trade("momentum")

    # Drop momentum 11%
    rm.check_circuit_breakers(100_000, {"momentum": 44_500})
    assert not rm.can_trade("momentum")
    # Portfolio still OK
    assert rm.can_trade()


def test_reset_halt():
    """Halts can be manually reset."""
    rm = RiskManager(persist=False)
    rm.check_circuit_breakers(100_000)
    rm.check_circuit_breakers(84_000)
    assert not rm.can_trade()

    rm.reset_halt()
    assert rm.can_trade()


def test_state_persistence(tmp_path):
    """Circuit breaker state survives save/load cycle."""
    state_dir = tmp_path / "risk_state"

    with patch("execution.risk_manager.STATE_DIR", state_dir):
        # Create manager, trigger breaker, save
        rm1 = RiskManager(account=1, persist=True)
        rm1.check_circuit_breakers(100_000)
        rm1.check_circuit_breakers(84_000)
        assert not rm1.can_trade()

        # New manager should load the halted state
        rm2 = RiskManager(account=1, persist=True)
        assert not rm2.can_trade()
        assert rm2._equity_peak == 100_000

        # Different account should be independent
        rm3 = RiskManager(account=2, persist=True)
        assert rm3.can_trade()


def test_state_file_isolation(tmp_path):
    """Each account gets its own state file."""
    state_dir = tmp_path / "risk_state"

    with patch("execution.risk_manager.STATE_DIR", state_dir):
        rm1 = RiskManager(account=1, persist=True)
        rm1.check_circuit_breakers(100_000)

        rm2 = RiskManager(account=2, persist=True)
        rm2.check_circuit_breakers(200_000)

        files = list(state_dir.iterdir())
        assert len(files) == 2
        names = {f.name for f in files}
        assert "circuit_breaker_acct1.json" in names
        assert "circuit_breaker_acct2.json" in names


def test_two_percent_rule():
    """2% rule caps position size when stop loss is tight."""
    rm = RiskManager(persist=False)
    # With a 1% stop loss, 2% rule limits position to 200% — so max_position_pct (20%) wins
    result = rm.calculate_position_size(
        symbol="TEST",
        portfolio_value=100_000,
        win_rate=0.60,
        avg_win=0.20,
        avg_loss=0.10,
        current_price=100.0,
        stop_loss_pct=0.01,
    )
    assert result.final_position_pct <= 0.20

    # With a 10% stop loss, 2% rule limits to 20% — same as max_position_pct
    result2 = rm.calculate_position_size(
        symbol="TEST",
        portfolio_value=100_000,
        win_rate=0.60,
        avg_win=0.20,
        avg_loss=0.10,
        current_price=100.0,
        stop_loss_pct=0.10,
    )
    assert result2.final_position_pct <= 0.20
    assert abs(result2.max_loss_capped_pct - 0.20) < 1e-10  # 2% / 10% = 20%
