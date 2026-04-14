"""
Rebalance Engine — converts strategy signals into executable orders.

Flow:
1. Run strategy on recent prices to get current target weights
2. Get current Alpaca positions
3. Compute target positions (weights * portfolio_value / price)
4. Diff target vs actual → generate buy/sell orders
5. Apply risk checks (circuit breakers, position limits)
6. Return order list for preview or execution

Supports both individual strategies and portfolio blends with SPY filter.
"""

import logging

import pandas as pd
from dataclasses import dataclass, field
from execution.alpaca_broker import AlpacaBroker, OrderRequest
from execution.risk_manager import RiskManager, RiskLimits

log = logging.getLogger("fire.rebalance")
from strategies.portfolio import (
    PORTFOLIOS,
    compute_spy_trend_filter,
    compute_btc_trend_filter,
    ETF_STRATEGIES,
    STOCK_STRATEGIES,
    CRYPTO_STRATEGIES,
)
from data.pipeline import download_prices, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from data.crypto import download_crypto_prices, download_btc_prices, to_alpaca_symbol


def to_alpaca_equity_symbol(sym: str) -> str:
    """Convert yfinance equity ticker to Alpaca format.

    yfinance uses hyphens for share classes (BF-B, BRK-B),
    Alpaca uses dots (BF.B, BRK.B).
    """
    return sym.replace("-", ".")


@dataclass
class RebalanceResult:
    """Result of a rebalance computation."""
    strategy_id: str
    portfolio_value: float
    target_weights: dict[str, float]
    target_positions: dict[str, float]   # symbol -> target qty (float for crypto)
    current_positions: dict[str, float]  # symbol -> current qty (float for crypto)
    orders: list[OrderRequest]
    risk_check: dict
    spy_filter_active: bool = False
    spy_filter_scalar: float = 1.0
    btc_filter_active: bool = False
    btc_filter_scalar: float = 1.0
    prices: dict[str, float] = field(default_factory=dict)
    missing_prices: list[str] = field(default_factory=list)
    price_error: bool = False


def get_current_signals(
    strategy_id: str,
    lookback_start: str = "2023-01-01",
    broker: "AlpacaBroker | None" = None,
) -> dict[str, float]:
    """Run a strategy on recent data and return the latest target weights.

    Args:
        strategy_id: Strategy or portfolio ID
        lookback_start: How far back to fetch prices (strategies need history for signals)
        broker: Optional broker for real-time price quotes (used by trend filters)

    Returns:
        Dict of {symbol: weight} for the most recent signal date.
    """
    if strategy_id in PORTFOLIOS:
        return _get_portfolio_signals(strategy_id, lookback_start, broker=broker)

    if strategy_id in CRYPTO_STRATEGIES:
        return _get_crypto_strategy_signals(strategy_id, lookback_start)

    if strategy_id in STOCK_STRATEGIES:
        return _get_stock_strategy_signals(strategy_id, lookback_start)

    if strategy_id in ETF_STRATEGIES:
        return _get_etf_strategy_signals(strategy_id, lookback_start)

    raise ValueError(f"Unknown strategy: {strategy_id}")


def _get_stock_strategy_signals(
    strategy_id: str, lookback_start: str
) -> dict[str, float]:
    """Get latest signals from a stock-based strategy."""
    prices = download_sp500_prices(start=lookback_start)
    vix = download_vix()

    strategy = STOCK_STRATEGIES[strategy_id]()
    strategy.set_vix(vix)
    signals = strategy.generate_signals(prices)

    # Get the most recent row of weights
    latest = signals.iloc[-1]
    # Filter to non-zero weights, convert tickers to Alpaca format
    return {to_alpaca_equity_symbol(sym): w for sym, w in latest.items() if abs(w) > 1e-6}


def _get_etf_strategy_signals(
    strategy_id: str, lookback_start: str
) -> dict[str, float]:
    """Get latest signals from an ETF-based strategy."""
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    prices = download_prices(symbols, start=lookback_start)

    strategy = ETF_STRATEGIES[strategy_id]()
    signals = strategy.generate_signals(prices)

    latest = signals.iloc[-1]
    return {sym: w for sym, w in latest.items() if abs(w) > 1e-6}


def _get_crypto_strategy_signals(
    strategy_id: str, lookback_start: str
) -> dict[str, float]:
    """Get latest signals from a crypto strategy.

    Returns weights keyed by Alpaca symbols (BTC/USD, not BTC-USD).
    """
    crypto_prices = download_crypto_prices(start=lookback_start)
    btc_prices = download_btc_prices()

    strategy = CRYPTO_STRATEGIES[strategy_id]()
    strategy.set_btc(btc_prices)
    signals = strategy.generate_signals(crypto_prices)

    latest = signals.iloc[-1]
    # Convert yfinance symbols to Alpaca symbols
    return {to_alpaca_symbol(sym): w for sym, w in latest.items() if abs(w) > 1e-6}


def _get_portfolio_signals(
    portfolio_id: str,
    lookback_start: str,
    broker: "AlpacaBroker | None" = None,
) -> dict[str, float]:
    """Get latest signals from a portfolio blend.

    Combines component strategy signals with their portfolio weights,
    then applies the SPY trend filter if configured.
    """
    config = PORTFOLIOS[portfolio_id]
    weights = config["weights"]
    use_spy_filter = config["spy_filter"]

    use_btc_filter = config.get("btc_filter", False)

    # Load data
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    etf_prices = download_prices(symbols, start=lookback_start)

    stock_prices = None
    vix = None
    if any(sid in STOCK_STRATEGIES for sid in weights):
        stock_prices = download_sp500_prices(start=lookback_start)
        vix = download_vix()

    crypto_prices = None
    btc_prices = None
    if any(sid in CRYPTO_STRATEGIES for sid in weights):
        crypto_prices = download_crypto_prices(start=lookback_start)
        btc_prices = download_btc_prices()

    # Get latest signals from each component
    combined_weights: dict[str, float] = {}
    for strategy_id, blend_weight in weights.items():
        if strategy_id in CRYPTO_STRATEGIES:
            strategy = CRYPTO_STRATEGIES[strategy_id]()
            if btc_prices is not None:
                strategy.set_btc(btc_prices)
            signals = strategy.generate_signals(crypto_prices)
            latest = signals.iloc[-1]
            # Convert crypto symbols to Alpaca format
            for sym, w in latest.items():
                if abs(w) > 1e-6:
                    alpaca_sym = to_alpaca_symbol(sym)
                    combined_weights[alpaca_sym] = combined_weights.get(alpaca_sym, 0) + w * blend_weight
        elif strategy_id in STOCK_STRATEGIES:
            strategy = STOCK_STRATEGIES[strategy_id]()
            if vix is not None:
                strategy.set_vix(vix)
            signals = strategy.generate_signals(stock_prices)
            latest = signals.iloc[-1]
            for sym, w in latest.items():
                if abs(w) > 1e-6:
                    alpaca_sym = to_alpaca_equity_symbol(sym)
                    combined_weights[alpaca_sym] = combined_weights.get(alpaca_sym, 0) + w * blend_weight
        else:
            strategy = ETF_STRATEGIES[strategy_id]()
            signals = strategy.generate_signals(etf_prices)
            latest = signals.iloc[-1]
            for sym, w in latest.items():
                if abs(w) > 1e-6:
                    combined_weights[sym] = combined_weights.get(sym, 0) + w * blend_weight

    # Apply SPY trend filter
    if use_spy_filter:
        live_spy = None
        if broker:
            try:
                live_spy = broker.get_latest_price("SPY")
            except Exception:
                log.warning("Could not fetch live SPY price from Alpaca, using cached")
        spy_filter = compute_spy_trend_filter(start=lookback_start, live_price=live_spy)
        scalar = spy_filter.iloc[-1]  # Latest filter value (1.0 or 0.5)
        combined_weights = {sym: w * scalar for sym, w in combined_weights.items()}

    # Apply BTC trend filter (binary: 1.0 or 0.0)
    if use_btc_filter:
        live_btc = None
        if broker:
            try:
                live_btc = broker.get_latest_price("BTC/USD")
            except Exception:
                log.warning("Could not fetch live BTC price from Alpaca, using cached")
        btc_filter = compute_btc_trend_filter(start=lookback_start, live_price=live_btc)
        scalar = btc_filter.iloc[-1]
        combined_weights = {sym: w * scalar for sym, w in combined_weights.items()}

    return combined_weights


def compute_rebalance(
    broker: AlpacaBroker,
    strategy_id: str,
    risk_manager: RiskManager | None = None,
    order_type: str = "market",
) -> RebalanceResult:
    """Compute the full rebalance: target weights → order list.

    Args:
        broker: Connected Alpaca broker
        strategy_id: Strategy or portfolio ID to rebalance to
        risk_manager: Optional risk manager for circuit breakers
        order_type: "market" or "limit"

    Returns:
        RebalanceResult with orders ready to preview or execute.
    """
    if risk_manager is None:
        risk_manager = RiskManager()

    # 1. Get current portfolio state
    portfolio_value = broker.get_portfolio_value()
    current_positions = broker.get_position_map()

    # 2. Check portfolio-level circuit breaker
    risk_check = risk_manager.check_circuit_breakers(portfolio_value)
    if not risk_manager.can_trade():
        return RebalanceResult(
            strategy_id=strategy_id,
            portfolio_value=portfolio_value,
            target_weights={},
            target_positions={},
            current_positions=current_positions,
            orders=[],
            risk_check=risk_check,
        )

    # 3. Get target weights from strategy (broker provides real-time prices for filters)
    target_weights = get_current_signals(strategy_id, broker=broker)

    # 3b. Check tradeability for NEW target symbols (not currently held)
    # This catches delisted/acquired stocks before we try to buy them
    new_symbols = [s for s in target_weights if s not in current_positions]
    if new_symbols:
        tradeable = broker.check_tradeable(new_symbols)
        for s in new_symbols:
            if s not in tradeable:
                log.warning(f"Removing untradeable target: {s} (weight={target_weights[s]:.4f})")
                del target_weights[s]

    # 4. Get prices for all relevant symbols
    all_symbols = set(list(target_weights.keys()) + list(current_positions.keys()))
    prices = broker.get_latest_prices(list(all_symbols))

    # Detect missing prices for target symbols
    missing_prices = [
        s for s in target_weights
        if s not in prices or prices.get(s, 0) <= 0
    ]
    # Also check current positions — if we hold something we can't price,
    # that's dangerous (can't compute sell qty properly)
    missing_current = [
        s for s in current_positions
        if s not in prices or prices.get(s, 0) <= 0
    ]
    # Block execution only if we can't price current holdings (sell sizing
    # would be wrong). Missing target prices are warned but not blocking —
    # those symbols are excluded from target_positions and the rest trades
    # correctly. Preview always shows missing_prices for user visibility.
    price_error = len(missing_current) > 0

    # 5. Convert weights to target quantities
    # Detect if this is a crypto strategy (needs fractional quantities)
    is_crypto = (
        strategy_id in CRYPTO_STRATEGIES
        or (strategy_id in PORTFOLIOS and any(
            sid in CRYPTO_STRATEGIES for sid in PORTFOLIOS[strategy_id]["weights"]
        ))
    )

    target_positions: dict[str, float] = {}
    for symbol, weight in target_weights.items():
        if symbol not in prices or prices[symbol] <= 0:
            log.warning(f"Skipping {symbol} (weight={weight:.4f}): no live price — may be delisted or suspended")
            continue
        # Reject negative weights — system is long-only (no shorting)
        if weight < 0:
            log.warning(f"Negative weight for {symbol}: {weight:.4f}, skipping (long-only system)")
            continue
        # Cap individual position at max_position_pct
        capped_weight = min(weight, risk_manager.limits.max_position_pct)
        dollar_amount = portfolio_value * capped_weight
        if is_crypto:
            qty = round(dollar_amount / prices[symbol], 8)
        else:
            qty = int(dollar_amount / prices[symbol])
        if qty > 0:
            target_positions[symbol] = qty

    # 6. Compute order diffs
    orders: list[OrderRequest] = []

    # Sells: positions we hold but shouldn't, or need to reduce
    for symbol, current_qty in current_positions.items():
        target_qty = target_positions.get(symbol, 0)
        if current_qty > target_qty:
            sell_qty = current_qty - target_qty
            orders.append(OrderRequest(
                symbol=symbol,
                qty=sell_qty,
                side="sell",
                order_type=order_type,
                limit_price=prices.get(symbol) if order_type == "limit" else None,
            ))

    # Buys: positions we need to open or increase
    for symbol, target_qty in target_positions.items():
        current_qty = current_positions.get(symbol, 0)
        if target_qty > current_qty:
            buy_qty = target_qty - current_qty
            orders.append(OrderRequest(
                symbol=symbol,
                qty=buy_qty,
                side="buy",
                order_type=order_type,
                limit_price=prices.get(symbol) if order_type == "limit" else None,
            ))

    # Check SPY filter status (use live prices consistent with signal generation)
    spy_filter_active = False
    spy_filter_scalar = 1.0
    if strategy_id in PORTFOLIOS and PORTFOLIOS[strategy_id].get("spy_filter"):
        live_spy = None
        try:
            live_spy = broker.get_latest_price("SPY")
        except Exception:
            pass
        spy_filter = compute_spy_trend_filter(live_price=live_spy)
        spy_filter_scalar = float(spy_filter.iloc[-1])
        spy_filter_active = spy_filter_scalar < 1.0

    # Check BTC filter status
    btc_filter_active = False
    btc_filter_scalar = 1.0
    if strategy_id in PORTFOLIOS and PORTFOLIOS[strategy_id].get("btc_filter"):
        live_btc = None
        try:
            live_btc = broker.get_latest_price("BTC/USD")
        except Exception:
            pass
        btc_filter = compute_btc_trend_filter(live_price=live_btc)
        btc_filter_scalar = float(btc_filter.iloc[-1])
        btc_filter_active = btc_filter_scalar < 1.0

    return RebalanceResult(
        strategy_id=strategy_id,
        portfolio_value=portfolio_value,
        target_weights=target_weights,
        target_positions=target_positions,
        current_positions=current_positions,
        orders=orders,
        risk_check=risk_check,
        spy_filter_active=spy_filter_active,
        spy_filter_scalar=spy_filter_scalar,
        btc_filter_active=btc_filter_active,
        btc_filter_scalar=btc_filter_scalar,
        prices=prices,
        missing_prices=missing_prices,
        price_error=price_error,
    )


def check_price_staleness(
    broker: AlpacaBroker,
    compute_prices: dict[str, float],
    threshold: float = 0.02,
) -> list[dict]:
    """Re-fetch prices and compare to compute-time prices.

    Returns list of drifted symbols (empty if all prices are within threshold).
    Used as a safety guard before executing orders — blocks execution if any
    price moved >threshold since computation.
    """
    fresh = broker.get_latest_prices(list(compute_prices.keys()))
    drifted = []
    for sym, old_price in compute_prices.items():
        new_price = fresh.get(sym)
        if new_price and old_price > 0:
            pct = abs(new_price - old_price) / old_price
            if pct > threshold:
                drifted.append({
                    "symbol": sym,
                    "compute_price": old_price,
                    "current_price": new_price,
                    "drift_pct": round(pct * 100, 2),
                })
    return drifted


def execute_rebalance(
    broker: AlpacaBroker,
    rebalance: RebalanceResult,
) -> list[dict]:
    """Execute the orders from a rebalance computation.

    Args:
        broker: Connected Alpaca broker
        rebalance: Result from compute_rebalance()

    Returns:
        List of order execution results.
    """
    if not rebalance.orders:
        return []

    return broker.submit_orders(rebalance.orders)
