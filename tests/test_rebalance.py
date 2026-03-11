"""Tests for rebalance logic — order generation, sell-before-buy, etc."""

from unittest.mock import MagicMock, patch
from execution.rebalance import compute_rebalance, RebalanceResult
from execution.alpaca_broker import OrderRequest
from execution.risk_manager import RiskManager


def _mock_broker(positions: dict[str, float], value: float = 100_000, prices: dict | None = None):
    """Create a mock broker with given positions and prices."""
    broker = MagicMock()
    broker.get_portfolio_value.return_value = value
    broker.get_position_map.return_value = positions
    if prices is None:
        prices = {sym: 100.0 for sym in positions}
    broker.get_latest_prices.return_value = prices
    return broker


@patch("execution.rebalance.get_current_signals")
def test_basic_rebalance_generates_orders(mock_signals):
    """Rebalance from empty portfolio to target weights generates buy orders."""
    mock_signals.return_value = {"AAPL": 0.10, "MSFT": 0.10}

    broker = _mock_broker(positions={}, value=100_000, prices={"AAPL": 100.0, "MSFT": 200.0})

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    assert len(result.orders) == 2
    assert all(o.side == "buy" for o in result.orders)
    symbols = {o.symbol for o in result.orders}
    assert symbols == {"AAPL", "MSFT"}


@patch("execution.rebalance.get_current_signals")
def test_rebalance_generates_sells(mock_signals):
    """Rebalance with excess positions generates sell orders."""
    mock_signals.return_value = {"AAPL": 0.10}  # Only want AAPL

    # Currently hold AAPL and MSFT
    broker = _mock_broker(
        positions={"AAPL": 100, "MSFT": 50},
        value=100_000,
        prices={"AAPL": 100.0, "MSFT": 200.0},
    )

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    sell_orders = [o for o in result.orders if o.side == "sell"]
    assert any(o.symbol == "MSFT" for o in sell_orders)


@patch("execution.rebalance.get_current_signals")
def test_circuit_breaker_halts_rebalance(mock_signals):
    """When circuit breaker is active, rebalance returns empty orders."""
    mock_signals.return_value = {"AAPL": 0.10}

    broker = _mock_broker(positions={}, value=100_000)
    rm = RiskManager(persist=False)
    # Trip the circuit breaker
    rm.check_circuit_breakers(100_000)
    rm.check_circuit_breakers(84_000)

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=rm,
    )

    assert result.orders == []
    assert result.risk_check["portfolio_halted"] is True


@patch("execution.rebalance.get_current_signals")
def test_position_cap_at_20_percent(mock_signals):
    """No single position exceeds 20% of portfolio."""
    mock_signals.return_value = {"AAPL": 0.50}  # Request 50%

    broker = _mock_broker(positions={}, value=100_000, prices={"AAPL": 100.0})

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    # Should be capped at 20% = $20,000 = 200 shares
    assert len(result.orders) == 1
    assert result.orders[0].qty <= 200


@patch("execution.rebalance.get_current_signals")
def test_no_orders_when_at_target(mock_signals):
    """No orders generated when already at target."""
    mock_signals.return_value = {"AAPL": 0.10}  # 10% = $10k = 100 shares at $100

    broker = _mock_broker(
        positions={"AAPL": 100},
        value=100_000,
        prices={"AAPL": 100.0},
    )

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    assert result.orders == []
