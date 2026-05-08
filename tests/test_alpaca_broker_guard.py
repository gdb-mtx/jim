"""Tests for AlpacaBroker pre-submit sell-qty guard (`_verify_sell_qtys`).

The guard re-fetches broker positions right before submission and refuses
to submit a sell whose qty exceeds broker-current by >1%. It exists to
prevent the over-sell failure mode observed 2026-05-08 where a stale
position read led the daily fire to issue a sell qty that didn't match
reality, contributing to a 2-day-old leveraged state on Alpaca paper.
"""

from unittest.mock import MagicMock, patch

import pytest

from execution.alpaca_broker import AlpacaBroker, OrderRequest


@pytest.fixture
def broker():
    """AlpacaBroker with the underlying alpaca-trade-api REST client mocked.

    Bypasses .env credential loading and any real network calls. Tests
    interact with the broker's methods; positions and order submissions
    are stubbed via `broker.api.<method>.return_value = ...`.
    """
    with patch.dict(
        "os.environ",
        {"ALPACA_API_KEY": "test", "ALPACA_SECRET_KEY": "test"},
    ):
        with patch("execution.alpaca_broker.tradeapi.REST"):
            b = AlpacaBroker(account=1)
    return b


def _mock_position(symbol: str, qty: float):
    """Build an Alpaca-shaped position object good enough for get_position_map."""
    p = MagicMock()
    p.symbol = symbol
    p.qty = str(qty)
    p.market_value = "1000"
    p.current_price = "10"
    p.unrealized_pl = "0"
    return p


def test_guard_passes_safe_sell(broker):
    """Sell qty within 1% of position passes the guard."""
    broker.api.list_positions.return_value = [_mock_position("BTCUSD", 1.0)]
    orders = [OrderRequest(symbol="BTC/USD", qty=0.99, side="sell", order_type="market")]
    safe, blocked = broker._verify_sell_qtys(orders)
    assert len(safe) == 1
    assert len(blocked) == 0


def test_guard_passes_within_tolerance(broker):
    """Sell qty up to 1% over current passes (covers fee/rounding drift)."""
    broker.api.list_positions.return_value = [_mock_position("BTCUSD", 1.0)]
    orders = [OrderRequest(symbol="BTC/USD", qty=1.005, side="sell", order_type="market")]
    safe, blocked = broker._verify_sell_qtys(orders)
    assert len(safe) == 1
    assert len(blocked) == 0


def test_guard_blocks_obvious_oversell(broker):
    """Sell qty 100x position: guard blocks. This is the 2026-05-08 case."""
    broker.api.list_positions.return_value = [_mock_position("XRPUSD", 67.6)]
    orders = [
        OrderRequest(symbol="XRP/USD", qty=33631.86, side="sell", order_type="market"),
    ]
    safe, blocked = broker._verify_sell_qtys(orders)
    assert len(safe) == 0
    assert len(blocked) == 1
    assert blocked[0]["status"] == "error"
    assert "pre-submit guard" in blocked[0]["error"]
    assert "33631.86" in blocked[0]["error"]


def test_guard_blocks_sell_against_zero_position(broker):
    """Sell against position we don't hold at all gets blocked."""
    broker.api.list_positions.return_value = []
    orders = [OrderRequest(symbol="XRP/USD", qty=100.0, side="sell", order_type="market")]
    safe, blocked = broker._verify_sell_qtys(orders)
    assert len(safe) == 0
    assert len(blocked) == 1


def test_guard_lets_buys_through_unchanged(broker):
    """Buys are never blocked, even when an adjacent sell is."""
    broker.api.list_positions.return_value = [_mock_position("BTCUSD", 0.001)]
    orders = [
        OrderRequest(symbol="BTC/USD", qty=10.0, side="sell", order_type="market"),
        OrderRequest(symbol="LINK/USD", qty=0, side="buy", order_type="market", notional=5000),
    ]
    safe, blocked = broker._verify_sell_qtys(orders)
    safe_sides = sorted(o.side for o in safe)
    assert safe_sides == ["buy"]
    assert len(blocked) == 1


def test_guard_fail_open_on_position_fetch_error(broker):
    """If list_positions throws, proceed without the guard rather than block
    everything (fail-open). Network blip shouldn't take the rebalance down."""
    broker.api.list_positions.side_effect = RuntimeError("network down")
    orders = [
        OrderRequest(symbol="BTC/USD", qty=0.5, side="sell", order_type="market"),
        OrderRequest(symbol="LINK/USD", qty=0, side="buy", order_type="market", notional=5000),
    ]
    safe, blocked = broker._verify_sell_qtys(orders)
    assert len(safe) == 2
    assert len(blocked) == 0


def test_submit_orders_blocked_sell_recorded_in_results(broker):
    """End-to-end: submit_orders includes blocked sells in its result list
    as status=error so the journal captures the attempt."""
    broker.api.list_positions.return_value = [_mock_position("XRPUSD", 67.6)]
    # submit_order isn't called for blocked sells; mock to detect any leakage.
    submit_called = []
    def _capture_submit(order):
        submit_called.append(order)
        return {"order_id": "x", "symbol": order.symbol, "qty": order.qty,
                "notional": order.notional, "side": order.side, "type": "market",
                "status": "filled", "submitted_at": "now"}
    broker.submit_order = _capture_submit
    orders = [OrderRequest(symbol="XRP/USD", qty=33631.86, side="sell", order_type="market")]
    results = broker.submit_orders(orders)
    assert len(submit_called) == 0  # blocked sell never reached submit_order
    assert len(results) == 1
    assert results[0]["status"] == "error"
    assert "pre-submit guard" in results[0]["error"]
