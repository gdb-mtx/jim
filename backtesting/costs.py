"""Turnover-weighted transaction-cost layer for the backtest.

Cost = `bps_round_trip × one_way_turnover` subtracted from each day's return.
Turnover is computed from the strategy's signal series (post-shift to match the
`signals.shift(1) × asset_returns` convention in `BaseStrategy.generate_returns`).

Per-strategy rates in `STRATEGY_COST_BPS`: ~5 bps equity (Alpaca zero-commission,
slippage only) and ~20 bps crypto (Alpaca spot ~10-15 bps half-spread × 2 sides).
"""

from __future__ import annotations

import pandas as pd


# Round-trip cost in basis points per one-way turnover = 1.0.
# Format: bps_round_trip where actual cost = (bps_round_trip / 10000) × turnover
# Equity strategies: ~5 bps (Alpaca zero-commission, slippage + modest spread).
# Crypto strategies: ~20 bps (Alpaca spot half-spread 10-15 bps × 2 sides,
#   conservative midpoint).
STRATEGY_COST_BPS: dict[str, float] = {
    # Equity
    "stock_momentum": 5.0,
    "low_volatility": 5.0,
    "short_term_reversal": 5.0,
    "multi_asset_trend": 5.0,
    "cross_sectional": 5.0,
    "dual_momentum": 5.0,
    "ts_momentum": 5.0,
    "multi_tf_momentum": 5.0,
    # Crypto
    "crypto_momentum": 20.0,
}

DEFAULT_COST_BPS = 5.0  # Fallback for strategies not in the dict


def compute_one_way_turnover(signals: pd.DataFrame) -> pd.Series:
    """Daily one-way turnover = 0.5 × sum(|Δw|) across assets.

    Aligned to the `signals.shift(1) × asset_returns` convention in
    `BaseStrategy.generate_returns`: turnover on day `t` reflects the
    trades executed *before* the return on day `t` is realized.
    """
    shifted = signals.shift(1)
    turnover = shifted.diff().abs().sum(axis=1) / 2.0
    return turnover.fillna(0.0)


def apply_transaction_costs(
    returns: pd.Series,
    signals: pd.DataFrame,
    bps_round_trip: float,
) -> pd.Series:
    """Subtract `bps_round_trip × turnover` from each day's return.

    Args:
        returns: Gross daily returns (from `generate_returns`).
        signals: Weights DataFrame (from `generate_signals`) — used to
            compute turnover.
        bps_round_trip: Cost in basis points per unit of one-way turnover.
            Equity ~5 bps, crypto ~20 bps (see `STRATEGY_COST_BPS`).

    Returns:
        Net-of-cost daily returns, same index as `returns`.
    """
    turnover = compute_one_way_turnover(signals)
    cost_drag = (bps_round_trip / 10_000.0) * turnover
    cost_drag = cost_drag.reindex(returns.index).fillna(0.0)
    return returns - cost_drag


def cost_bps_for_strategy(strategy_id: str) -> float:
    """Lookup helper — returns the default cost rate in bps round-trip."""
    return STRATEGY_COST_BPS.get(strategy_id, DEFAULT_COST_BPS)


def generate_costed_returns(
    strategy,
    prices: pd.DataFrame,
    strategy_id: str,
) -> pd.Series:
    """Convenience: `strategy.generate_returns(prices)` + transaction costs.

    Used by the validation adapters so Test 2 (rolling OOS) / Test 6
    (walk-forward refit) apply the same cost basis as Test 1 (OOS holdout
    via `run_portfolio`).
    """
    signals = strategy.generate_signals(prices)
    asset_returns = prices.pct_change()
    gross = (signals.shift(1) * asset_returns).sum(axis=1).dropna()
    return apply_transaction_costs(gross, signals, cost_bps_for_strategy(strategy_id))
