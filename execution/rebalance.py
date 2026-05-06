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
from execution.risk_manager import RiskManager, compute_drawdown
from execution.validation_gate import require_validated

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
    vol_scalar: float = 1.0
    vol_scalar_diagnostics: dict | None = None
    # N4 (AUDIT_MONTH2_REVIEW): intermediate weight snapshots for post-mortem
    # reconstruction. `raw_signal_weights` = strategy output pre-overlay;
    # `post_filter_weights` = after SPY/BTC filter, before vol-scaling.
    raw_signal_weights: dict[str, float] = field(default_factory=dict)
    post_filter_weights: dict[str, float] = field(default_factory=dict)
    prices: dict[str, float] = field(default_factory=dict)
    missing_prices: list[str] = field(default_factory=list)
    price_error: bool = False


def get_current_signals(
    strategy_id: str,
    lookback_start: str = "2023-01-01",
    broker: "AlpacaBroker | None" = None,
    stages_out: dict | None = None,
) -> dict[str, float]:
    """Run a strategy on recent data and return the latest target weights.

    Args:
        strategy_id: Strategy or portfolio ID
        lookback_start: How far back to fetch prices (strategies need history for signals)
        broker: Optional broker for real-time price quotes (used by trend filters)
        stages_out: Optional dict; if provided, gets populated with keys
            "raw" (pre-filter strategy output) and "post_filter" (after
            SPY+BTC filter). Used by `compute_rebalance` to persist the
            intermediate weight vectors to the rebalance journal (N4,
            AUDIT_MONTH2_REVIEW). For non-portfolio paths no filter runs,
            so raw == post_filter.

    Returns:
        Dict of {symbol: weight} for the most recent signal date.
    """
    if strategy_id in PORTFOLIOS:
        return _get_portfolio_signals(
            strategy_id, lookback_start, broker=broker, stages_out=stages_out
        )

    if strategy_id in CRYPTO_STRATEGIES:
        weights = _get_crypto_strategy_signals(strategy_id, lookback_start, broker=broker)
    elif strategy_id in STOCK_STRATEGIES:
        weights = _get_stock_strategy_signals(strategy_id, lookback_start)
    elif strategy_id in ETF_STRATEGIES:
        weights = _get_etf_strategy_signals(strategy_id, lookback_start)
    else:
        raise ValueError(f"Unknown strategy: {strategy_id}")

    if stages_out is not None:
        stages_out["raw"] = dict(weights)
        stages_out["post_filter"] = dict(weights)
    return weights


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


def _live_augmented_btc(broker, btc_prices):
    """Overwrite the last row of `btc_prices` with the live BTC quote.

    The strategy's internal BTC trend filter operates on `set_btc()`'d
    daily closes, which lag real-time by up to a day. Augmenting the
    latest close with the live Alpaca quote keeps in-session previews
    and executes consistent with `filter_check.py` and
    `compute_btc_trend_filter(live_price=...)`, which already use the
    live quote for the same flip detection.

    No-op if broker is None (e.g. backtest paths) or the live fetch
    fails — falls back to whatever cached close we have.
    """
    if broker is None or btc_prices is None or len(btc_prices) == 0:
        return btc_prices
    try:
        live_btc = broker.get_latest_price("BTC/USD")
    except Exception:
        return btc_prices
    if live_btc is None:
        return btc_prices
    btc_prices = btc_prices.copy()
    btc_prices.iloc[-1] = float(live_btc)
    return btc_prices


def _get_crypto_strategy_signals(
    strategy_id: str, lookback_start: str, broker=None
) -> dict[str, float]:
    """Get latest signals from a crypto strategy.

    Returns weights keyed by Alpaca symbols (BTC/USD, not BTC-USD).
    """
    crypto_prices = download_crypto_prices(start=lookback_start)
    btc_prices = download_btc_prices()
    btc_prices = _live_augmented_btc(broker, btc_prices)

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
    stages_out: dict | None = None,
) -> dict[str, float]:
    """Get latest signals from a portfolio blend.

    Combines component strategy signals with their portfolio weights,
    then applies the SPY trend filter if configured. When `stages_out`
    is provided, populates it with "raw" (pre-filter) and "post_filter"
    snapshots for the rebalance journal (N4).
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
        btc_prices = _live_augmented_btc(broker, btc_prices)

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

    # N4: snapshot the raw (pre-overlay) weights before any filter runs.
    if stages_out is not None:
        stages_out["raw"] = dict(combined_weights)

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
        # NaN scalar would silently liquidate the book (NaN × weights → all
        # NaN → filtered to {} → empty target → full exit). Most likely on
        # cloud cold-start when 200d MA warmup is incomplete.
        if pd.isna(scalar):
            raise RuntimeError(
                f"SPY filter scalar is NaN for portfolio {portfolio_id}; refusing to rebalance. "
                f"Check SPY cache has >=200d of history."
            )
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
        if pd.isna(scalar):
            raise RuntimeError(
                f"BTC filter scalar is NaN for portfolio {portfolio_id}; refusing to rebalance. "
                f"Check BTC cache has >=125d of history."
            )
        combined_weights = {sym: w * scalar for sym, w in combined_weights.items()}

    # N4: snapshot the post-filter weights (before vol-scaling in compute_rebalance).
    if stages_out is not None:
        stages_out["post_filter"] = dict(combined_weights)

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

    # 0. Validation gate — hard safety net. Three call sites
    # (API route, APScheduler, filter_check) already check before
    # reaching here; this guarantees a future 4th call site can't
    # silently bypass the gate. Retired accounts raise unconditionally
    # (no override bypass possible — see validation_gate.check). T4,
    # AUDIT_MONTH2_REVIEW §4.
    require_validated(broker.account)

    # 1. Get current portfolio state
    portfolio_value = broker.get_portfolio_value()
    current_positions = broker.get_position_map()

    # 2. Drawdown check — peak derived from snapshots; -35% latches the
    #    catastrophe halt (blocks trading, manual reset required). The -10%
    #    alert is surfaced in `risk_check` for the dashboard banner but
    #    does not block. See AUDIT_MONTH2 C5 for the design rationale.
    dd = compute_drawdown(broker.account, portfolio_value, risk_manager.limits)
    risk_manager.check_and_latch_halt(dd.drawdown, dd.equity_peak, portfolio_value)
    risk_check = {
        "halted": risk_manager.halted,
        "alert_active": dd.alert_active,
        "drawdown": dd.drawdown,
        "equity_peak": dd.equity_peak,
    }
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

    # 3. Get target weights from strategy (broker provides real-time prices for filters).
    # N4: capture the raw (pre-overlay) and post-filter (pre-vol-scaling) stages
    # for the rebalance journal.
    stages: dict = {}
    target_weights = get_current_signals(strategy_id, broker=broker, stages_out=stages)
    raw_signal_weights = stages.get("raw", dict(target_weights))
    post_filter_weights = stages.get("post_filter", dict(target_weights))

    # 3a. Vol-scaling overlay (AUDIT_MONTH2 C4) — applies to strategies whose
    # backtest uses `apply_vol_scaling`. Keeps sim/live parity by multiplying
    # strategy weights by EWMA-vol-inverse × vol_target, clipped [floor, cap].
    # Cap forced to 1.0 here regardless of config — Alpaca paper is spot-only /
    # no margin, so the backtest's cap=1.5 was never reachable live either way.
    vol_scalar = 1.0
    vol_scalar_diagnostics: dict | None = None
    portfolio_cfg = PORTFOLIOS.get(strategy_id, {})
    if portfolio_cfg.get("vol_scaling"):
        from execution.vol_scaling import compute_live_vol_scalar
        params = {**portfolio_cfg.get("vol_scaling_params", {}), "scalar_cap": 1.0}
        vol_scalar, vol_scalar_diagnostics = compute_live_vol_scalar(
            broker.account, **params
        )
        log.info(
            f"vol_scaling account={broker.account} strategy={strategy_id} "
            f"scalar={vol_scalar:.4f} diag={vol_scalar_diagnostics}"
        )
        if vol_scalar != 1.0:
            target_weights = {s: w * vol_scalar for s, w in target_weights.items()}

    # Invariant check — strategies should produce sane weight distributions.
    # Guards against a strategy bug producing extreme/pathological output.
    # Loud failure beats silent clamping (see AUDIT_MONTH2 C7 resolution).
    _weight_sum = sum(target_weights.values())
    if _weight_sum > 1.0 + 1e-6:
        raise ValueError(
            f"Strategy {strategy_id} produced weights summing to {_weight_sum:.4f} > 1.0. "
            f"Refusing to trade. Investigate signal generation before retrying."
        )
    for sym, w in target_weights.items():
        if w < 0 or w > 1.0 + 1e-6:
            raise ValueError(
                f"Strategy {strategy_id} produced out-of-range weight for {sym}: {w:.4f}. "
                f"Expected [0, 1]. Refusing to trade."
            )

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
        # Per-symbol weight from the strategy is the sizing. Concentration is
        # controlled by strategy shape (top_n + equal-weight), not a runtime cap.
        # See AUDIT_MONTH2 C7: the old 20% cap silently kneecapped A4's top-2
        # crypto design (capped 50/50 to 20/20 + 60% cash).
        dollar_amount = portfolio_value * weight
        if is_crypto:
            qty = round(dollar_amount / prices[symbol], 8)
        else:
            qty = int(dollar_amount / prices[symbol])
        if qty > 0:
            target_positions[symbol] = qty

    # 5b. Cash-constrained sizing for crypto buys, via Alpaca's notional
    # (dollar-amount) order path. Crypto prices can drift 1-2% in the
    # seconds between preview and fill; a qty-based order at a stale
    # price then exceeds available cash and gets rejected with
    # "insufficient balance". Specifying a dollar amount lets Alpaca
    # compute qty at fill price, so we spend exactly what we have.
    #
    # Per-symbol notional = target_weight × portfolio_value, capped so
    # the total crypto buy notional fits inside available cash with a
    # small safety margin for spread + fees. Sells still use qty (we
    # know exactly what we hold). Discovered 2026-04-22 on A4's first
    # trade — three qty-based ETH buys got rejected as ETH rose 2%
    # between preview and fill; the notional path settles cleanly.
    crypto_buy_notionals: dict[str, float] = {}
    if is_crypto and target_positions:
        available_cash = broker.get_cash()
        # Sells run before buys in `submit_orders`, so the proceeds they
        # free fund the buys in the same batch. Without including them in
        # the cap, a rotation day (sell A → buy B) sizes B against pre-sell
        # cash (~$0 when fully invested), leaving the proceeds stranded.
        # Surfaced 2026-05-03 on A4's first ETH→XRP rotation: ETH sell
        # freed $47K, XRP buy got notional $134, $47K idle for 24h.
        expected_sell_proceeds = sum(
            (current_qty - target_positions.get(s, 0)) * prices[s]
            for s, current_qty in current_positions.items()
            if current_qty > target_positions.get(s, 0) and prices.get(s, 0) > 0
        )
        # Raw dollar target = weight × portfolio_value (not qty × price,
        # so we aren't re-exposed to stale prices).
        raw_target_notionals = {
            s: target_weights[s] * portfolio_value
            for s in target_positions
            if target_weights.get(s, 0) > 0
        }
        # What still needs to be bought, in dollars at current price.
        remaining_buy_notionals = {
            s: max(0.0, n - current_positions.get(s, 0) * prices[s])
            for s, n in raw_target_notionals.items()
        }
        total_buy_notional = sum(remaining_buy_notionals.values())
        cash_budget = (available_cash + expected_sell_proceeds) * 0.999
        if total_buy_notional > 0:
            scale = min(1.0, cash_budget / total_buy_notional)
            if scale < 1.0:
                log.warning(
                    f"Crypto buy notional ${total_buy_notional:.2f} exceeds "
                    f"cash budget ${cash_budget:.2f} "
                    f"(cash=${available_cash:.2f} + sells=${expected_sell_proceeds:.2f}). "
                    f"Scaling by {scale:.4f}."
                )
            for s, n in remaining_buy_notionals.items():
                scaled = round(n * scale, 2)
                if scaled >= 1.0:  # skip dust (< $1 Alpaca crypto minimum)
                    crypto_buy_notionals[s] = scaled

    # 6. Compute order diffs
    orders: list[OrderRequest] = []

    # Alpaca rejects time_in_force="day" on crypto orders with "invalid
    # crypto time_in_force" (discovered 2026-04-22 on A4's first trade).
    # Crypto supports gtc/ioc; use gtc so the order survives a brief
    # connectivity hiccup. Equities keep the existing "day" default.
    tif = "gtc" if is_crypto else "day"

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
                time_in_force=tif,
            ))

    # Buys: positions we need to open or increase. For crypto, use
    # notional (dollar-amount) orders — see 5b above.
    for symbol, target_qty in target_positions.items():
        current_qty = current_positions.get(symbol, 0)
        if target_qty > current_qty:
            buy_qty = target_qty - current_qty
            notional = crypto_buy_notionals.get(symbol) if is_crypto else None
            if is_crypto and notional is None:
                continue  # crypto buy was dust-filtered or cash-zero'd
            orders.append(OrderRequest(
                symbol=symbol,
                qty=buy_qty,
                side="buy",
                order_type=order_type,
                limit_price=prices.get(symbol) if order_type == "limit" else None,
                time_in_force=tif,
                notional=notional,
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
        vol_scalar=vol_scalar,
        vol_scalar_diagnostics=vol_scalar_diagnostics,
        raw_signal_weights=raw_signal_weights,
        post_filter_weights=post_filter_weights,
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
    price moved >threshold since computation, OR if a symbol became
    unfetchable (AUDIT_MONTH2 R11: previously unfetchable symbols were
    silently skipped, so a halt/delist between preview and execute would not
    block execution).
    """
    fresh = broker.get_latest_prices(list(compute_prices.keys()))
    drifted = []
    for sym, old_price in compute_prices.items():
        new_price = fresh.get(sym)
        if not new_price:
            # Unfetchable — treat as drifted so caller forces re-preview
            # instead of trading on a stale price.
            drifted.append({
                "symbol": sym,
                "compute_price": old_price,
                "current_price": None,
                "drift_pct": None,
                "reason": "unfetchable",
            })
            continue
        if old_price > 0:
            pct = abs(new_price - old_price) / old_price
            if pct > threshold:
                drifted.append({
                    "symbol": sym,
                    "compute_price": old_price,
                    "current_price": new_price,
                    "drift_pct": round(pct * 100, 2),
                    "reason": "drift",
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

    # `submit_orders_settled` waits for crypto sells to fill and rescales
    # buys against actual post-sell cash before submitting them — closes
    # the recurring "insufficient non_marginable_buying_power" race that
    # bit the daily A4 rebalance ~3-4 times. For equity batches and
    # crypto batches without sells, this falls through to the original
    # `submit_orders` fast path with no added latency.
    return broker.submit_orders_settled(rebalance.orders)
