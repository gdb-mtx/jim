"""Tests for rebalance logic — order generation, sell-before-buy, etc."""

from unittest.mock import MagicMock, patch

import pandas as pd

import numpy as np
import pytest

from execution.rebalance import compute_rebalance, RebalanceResult, check_price_staleness, get_current_signals
from execution.alpaca_broker import OrderRequest
from execution.risk_manager import RiskManager


def _snapshots(equity_values: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range(start="2026-03-01", periods=len(equity_values))
    return pd.DataFrame({"equity": equity_values}, index=idx)


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


@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_basic_rebalance_generates_orders(mock_signals, _gate):
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


@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_rebalance_generates_sells(mock_signals, _gate):
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


@patch("execution.rebalance.require_validated")
@patch("data.snapshots.load_snapshots")
@patch("execution.rebalance.get_current_signals")
def test_catastrophe_halt_latches_and_blocks_rebalance(mock_signals, mock_load, _gate):
    """Snapshots show peak $100k; live equity $60k = -40% DD → halt latches, orders empty."""
    mock_signals.return_value = {"AAPL": 0.10}
    mock_load.return_value = _snapshots([100_000, 95_000, 80_000])

    broker = _mock_broker(positions={}, value=60_000)
    rm = RiskManager(persist=False)

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=rm,
    )

    assert result.orders == []
    assert result.risk_check["halted"] is True
    assert rm.halted is True


@patch("execution.rebalance.require_validated")
@patch("data.snapshots.load_snapshots")
@patch("execution.rebalance.get_current_signals")
def test_drawdown_alert_does_not_block_rebalance(mock_signals, mock_load, _gate):
    """Snapshots peak $100k; live $88k = -12% DD → alert_active but NOT halted; orders flow."""
    mock_signals.return_value = {"AAPL": 0.10}
    mock_load.return_value = _snapshots([100_000, 95_000])

    broker = _mock_broker(
        positions={},
        value=88_000,
        prices={"AAPL": 100.0},
    )
    rm = RiskManager(persist=False)

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=rm,
    )

    assert result.risk_check["halted"] is False
    assert result.risk_check["alert_active"] is True
    assert result.risk_check["drawdown"] < -0.10
    assert len(result.orders) > 0


@patch("execution.rebalance.require_validated")
@patch("data.snapshots.load_snapshots")
@patch("execution.rebalance.get_current_signals")
def test_prelatched_halt_blocks_even_if_dd_recovered(mock_signals, mock_load, _gate):
    """Once the halt is latched, recovered equity still can't trade until manual reset."""
    mock_signals.return_value = {"AAPL": 0.10}
    mock_load.return_value = _snapshots([100_000])

    broker = _mock_broker(positions={}, value=99_000)
    rm = RiskManager(persist=False)
    # Simulate a prior latch (e.g., last run hit -40% before recovery)
    rm.check_and_latch_halt(drawdown=-0.40, equity_peak=100_000, current_equity=60_000)

    result = compute_rebalance(
        broker=broker,
        strategy_id="test_strategy",
        risk_manager=rm,
    )

    assert result.orders == []
    assert result.risk_check["halted"] is True


@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_no_orders_when_at_target(mock_signals, _gate):
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


@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_missing_prices_flagged(mock_signals, _gate):
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


@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_missing_current_position_prices_block_execution(mock_signals, _gate):
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


# ---- AUDIT_MONTH2_REVIEW N2: filter-scalar NaN guards ----
#
# NaN scalar × weights → all NaN → downstream `abs(w) > 1e-6` filter strips
# them → empty target → full-book liquidation. Loud failure beats silent exit.


@patch("execution.rebalance.compute_spy_trend_filter")
@patch("execution.rebalance.download_vix")
@patch("execution.rebalance.download_sp500_prices")
@patch("strategies.stock_momentum.StockMomentum.generate_signals")
def test_spy_filter_nan_raises_rather_than_liquidating(
    mock_signals, mock_sp500, mock_vix, mock_spy_filter
):
    ts = pd.Timestamp("2026-04-21")
    mock_signals.return_value = pd.DataFrame({"AAPL": [0.1]}, index=[ts])
    mock_sp500.return_value = pd.DataFrame({"AAPL": [100.0]}, index=[ts])
    mock_vix.return_value = pd.Series([20.0], index=[ts])
    mock_spy_filter.return_value = pd.Series([np.nan], index=[ts])

    with pytest.raises(RuntimeError, match="SPY filter scalar is NaN"):
        get_current_signals("sm_filtered")


@patch("execution.rebalance.compute_btc_trend_filter")
@patch("execution.rebalance.download_btc_prices")
@patch("execution.rebalance.download_crypto_prices")
@patch("strategies.crypto_momentum.CryptoMomentum.generate_signals")
def test_btc_filter_nan_raises_rather_than_liquidating(
    mock_signals, mock_crypto, mock_btc_prices, mock_btc_filter, monkeypatch
):
    # Currently no portfolio uses btc_filter=True at the portfolio level (BTC
    # filter is built into CryptoMomentum). Guard is defensive for future
    # configs — enable on crypto_momentum_filtered for the test.
    import strategies.portfolio as portfolio_mod
    monkeypatch.setitem(
        portfolio_mod.PORTFOLIOS["crypto_momentum_filtered"], "btc_filter", True
    )

    ts = pd.Timestamp("2026-04-21")
    mock_signals.return_value = pd.DataFrame({"BTC-USD": [0.5]}, index=[ts])
    mock_crypto.return_value = pd.DataFrame({"BTC-USD": [50000.0]}, index=[ts])
    mock_btc_prices.return_value = pd.Series([50000.0], index=[ts])
    mock_btc_filter.return_value = pd.Series([np.nan], index=[ts])

    with pytest.raises(RuntimeError, match="BTC filter scalar is NaN"):
        get_current_signals("crypto_momentum_filtered")


# ---- T4 (AUDIT_MONTH2_REVIEW §4): retired-account block through compute_rebalance ----
#
# The validation gate is enforced at three call sites (API route, APScheduler,
# filter_check). If a future 4th call site forgets `require_validated`, the
# hard safety net inside `compute_rebalance` must still reject account=3.
# This pins the invariant: no order submission path to a retired account.


def test_rebalance_against_retired_account_is_blocked(tmp_path, monkeypatch):
    """compute_rebalance must refuse to run against a retired account, even if
    the caller bypasses the call-site validation check. This is the hard safety
    net — catastrophic-fail invariant, AUDIT_MONTH2_REVIEW T4.
    """
    from execution import validation_gate
    from execution.validation_gate import ValidationGateError

    # Point the gate at a fresh state file with A3 marked retired.
    state_path = tmp_path / "validation_state.json"
    state_path.write_text(
        '{"account_3": {"status": "retired", "retired_reason": "test"}}'
    )
    monkeypatch.setattr(validation_gate, "STATE_PATH", state_path)

    # Broker set to account=3. Construction itself succeeds (A3 is a valid
    # account slot); the gate must catch it inside compute_rebalance.
    broker = _mock_broker(positions={}, value=100_000)
    broker.account = 3

    with pytest.raises(ValidationGateError, match="RETIRED"):
        compute_rebalance(
            broker=broker,
            strategy_id="test_strategy",
            risk_manager=RiskManager(persist=False),
        )


def test_rebalance_retired_block_not_bypassable_by_override(tmp_path, monkeypatch):
    """Even with FIRE_VALIDATION_OVERRIDE=1 set, the retired-account block
    must still fire. Matches validation_gate's R2 semantics at the
    compute_rebalance layer.
    """
    from execution import validation_gate
    from execution.validation_gate import ValidationGateError

    state_path = tmp_path / "validation_state.json"
    state_path.write_text(
        '{"account_3": {"status": "retired", "retired_reason": "test"}}'
    )
    monkeypatch.setattr(validation_gate, "STATE_PATH", state_path)
    monkeypatch.setenv("FIRE_VALIDATION_OVERRIDE", "1")
    monkeypatch.setenv("FIRE_VALIDATION_OVERRIDE_ACCT3", "1")

    broker = _mock_broker(positions={}, value=100_000)
    broker.account = 3

    with pytest.raises(ValidationGateError, match="RETIRED"):
        compute_rebalance(
            broker=broker,
            strategy_id="test_strategy",
            risk_manager=RiskManager(persist=False),
        )


# ---- Rotation-day sizing regression (2026-05-03 incident) ----
#
# A4's first true rotation (sell ETH → buy XRP) had the buy notional capped
# to pre-sell cash because `available_cash = broker.get_cash()` was queried
# before sells freed their proceeds. ETH sell freed $47K; XRP buy got $134
# notional; $47K sat idle for 24h. Fix sums in `expected_sell_proceeds` so
# the buy can be funded from the same-batch sells. This test pins the
# invariant: a fully-invested rotation does NOT collapse the buy.

@patch("execution.rebalance.require_validated")
@patch("execution.rebalance.get_current_signals")
def test_crypto_rotation_buy_notional_uses_post_sell_cash(mock_signals, _gate):
    """Rotation day: hold 100% in ETH, signal flips to BTC+XRP, near-zero cash.
    Buy notionals must be sized against (cash + sell proceeds), not pre-sell
    cash alone — otherwise the buys collapse to dust and the rotation strands
    the sell proceeds in cash for a full day.
    """
    mock_signals.return_value = {"BTC/USD": 0.5, "XRP/USD": 0.5}

    # Fully invested in ETH ($100K), ~nothing in cash.
    broker = _mock_broker(
        positions={"ETH/USD": 40.0},
        value=100_000,
        prices={"ETH/USD": 2500.0, "BTC/USD": 50_000.0, "XRP/USD": 1.0},
    )
    broker.account = 4
    broker.get_cash.return_value = 10.0  # pre-sell cash, mostly invested

    result = compute_rebalance(
        broker=broker,
        strategy_id="crypto_momentum",  # in CRYPTO_STRATEGIES, not PORTFOLIOS
        risk_manager=RiskManager(persist=False),
    )

    sells = [o for o in result.orders if o.side == "sell"]
    buys = [o for o in result.orders if o.side == "buy"]

    # Sell: full ETH position liquidated.
    assert len(sells) == 1
    assert sells[0].symbol == "ETH/USD"
    assert sells[0].qty == 40.0
    assert sells[0].notional is None  # sells use qty, not notional

    # Buys: each ≈ 50% of portfolio. With sell proceeds folded in, the cash
    # budget covers ~$100K of buys (× 0.999 safety), so each buy lands at
    # ~$49,950, NOT the ~$5 the bug produced.
    assert len(buys) == 2
    by_symbol = {o.symbol: o for o in buys}
    assert set(by_symbol) == {"BTC/USD", "XRP/USD"}
    for sym in ("BTC/USD", "XRP/USD"):
        n = by_symbol[sym].notional
        assert n is not None, f"{sym} buy missing notional (notional path is the live behavior)"
        # Tight band: must be > 99% of intended $50K and ≤ $50K.
        assert 49_500 < n <= 50_000, f"{sym} notional {n} collapsed — sell proceeds not credited?"
