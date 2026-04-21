"""Tests for rebalance logic — order generation, sell-before-buy, etc."""

from unittest.mock import MagicMock, patch
from execution.rebalance import compute_rebalance, RebalanceResult, check_price_staleness
from execution.alpaca_broker import OrderRequest
from execution.risk_manager import RiskManager


def _mock_broker(
    positions: dict[str, float],
    value: float = 100_000,
    prices: dict | None = None,
    tradeable: set[str] | None = None,
):
    """Create a mock broker with given positions and prices.

    `tradeable` defaults to the union of positions + prices — i.e., all
    symbols the test configured are assumed tradeable. Matches
    AlpacaBroker.check_tradeable's `set[str]` return contract. Without this,
    MagicMock returns a bare mock whose `in` check is always False → every
    target symbol is stripped as "untradeable" before orders are generated.
    """
    broker = MagicMock()
    broker.account = 1
    broker.get_portfolio_value.return_value = value
    broker.get_position_map.return_value = positions
    if prices is None:
        prices = {sym: 100.0 for sym in positions}
    broker.get_latest_prices.return_value = prices
    if tradeable is None:
        tradeable = set(positions.keys()) | set(prices.keys())
    broker.check_tradeable.return_value = tradeable
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


@patch("execution.rebalance.get_current_signals")
def test_missing_prices_flagged(mock_signals):
    """Missing target prices are warned but don't block execution.

    Missing prices for target-only symbols (not in current positions)
    are flagged in missing_prices for UI warnings, but price_error
    stays False — the rest of the portfolio trades correctly.
    """
    mock_signals.return_value = {"AAPL": 0.10, "MISSING": 0.10}

    # Broker only returns price for AAPL, not MISSING (but MISSING is still a
    # tradeable asset per Alpaca — it just failed the price quote fetch).
    broker = _mock_broker(
        positions={},
        value=100_000,
        prices={"AAPL": 100.0},
        tradeable={"AAPL", "MISSING"},
    )

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    # Missing target prices are flagged for UI warnings
    assert "MISSING" in result.missing_prices
    # But don't block execution (price_error only for current positions)
    assert result.price_error is False
    # AAPL should still have an order (partial computation works)
    assert any(o.symbol == "AAPL" for o in result.orders)


@patch("execution.rebalance.get_current_signals")
def test_missing_current_position_prices_block_execution(mock_signals):
    """Missing prices for currently-held positions MUST block execution.

    If we hold a symbol but can't price it, sell sizing would be wrong.
    """
    mock_signals.return_value = {"AAPL": 0.10}

    # We hold MYSTERY but can't get its price
    broker = _mock_broker(
        positions={"AAPL": 50, "MYSTERY": 100},
        value=100_000,
        prices={"AAPL": 100.0},
    )

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=RiskManager(persist=False),
    )

    assert result.price_error is True
    assert "MYSTERY" in result.missing_prices or len([
        s for s in result.current_positions
        if s not in result.prices or result.prices.get(s, 0) <= 0
    ]) > 0


# ---- R11: check_price_staleness handles unfetchable symbols ----


def test_price_staleness_drift_detected():
    """Drifted prices (>threshold) are returned with reason=drift."""
    broker = MagicMock()
    broker.get_latest_prices.return_value = {"AAPL": 105.0, "MSFT": 200.5}
    compute_prices = {"AAPL": 100.0, "MSFT": 200.0}

    drifted = check_price_staleness(broker, compute_prices, threshold=0.02)

    assert len(drifted) == 1
    assert drifted[0]["symbol"] == "AAPL"
    assert drifted[0]["reason"] == "drift"
    assert drifted[0]["drift_pct"] == 5.0


def test_price_staleness_unfetchable_flagged():
    """Unfetchable symbol (missing from fresh quote) is flagged, not silently
    skipped (AUDIT_MONTH2 R11). Forces caller to re-preview rather than trade
    on a stale price.
    """
    broker = MagicMock()
    # AAPL fetchable; MSFT missing (delist/halt/network)
    broker.get_latest_prices.return_value = {"AAPL": 100.0}
    compute_prices = {"AAPL": 100.0, "MSFT": 200.0}

    drifted = check_price_staleness(broker, compute_prices, threshold=0.02)

    unfetchable = [d for d in drifted if d.get("reason") == "unfetchable"]
    assert len(unfetchable) == 1
    assert unfetchable[0]["symbol"] == "MSFT"
    assert unfetchable[0]["current_price"] is None
    assert unfetchable[0]["drift_pct"] is None


def test_price_staleness_zero_price_flagged():
    """Fresh price of 0 is treated as unfetchable (falsy)."""
    broker = MagicMock()
    broker.get_latest_prices.return_value = {"AAPL": 0}
    compute_prices = {"AAPL": 100.0}

    drifted = check_price_staleness(broker, compute_prices, threshold=0.02)

    assert len(drifted) == 1
    assert drifted[0]["reason"] == "unfetchable"
