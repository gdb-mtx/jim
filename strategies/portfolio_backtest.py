"""Research-path portfolio code — backtest runners + vol-scaling math.

Split out from strategies/portfolio.py per DEPLOYMENT_PLAN.md §Phase 0. This
module is the laptop-only research surface: runs full per-strategy backtests,
applies SPY/BTC trend filters and vol-scaling to historical return series,
and combines accounts into the live-book composite.

May import from strategies.portfolio_config (one-way). Live code paths
(execution/, scripts/filter_check.py, api/routes/) MUST NOT import from here.
"""

import numpy as np
import pandas as pd

from data.pipeline import download_and_cache, EXPANDED_UNIVERSE
from data.sp500 import download_sp500_prices, download_vix
from data.crypto import download_crypto_prices, download_btc_prices, LIVE_CRYPTO_UNIVERSE
from strategies.portfolio_config import (
    PORTFOLIOS,
    ETF_STRATEGIES,
    STOCK_STRATEGIES,
    CRYPTO_STRATEGIES,
    compute_spy_trend_filter,
    compute_btc_trend_filter,
)


def _generate_strategy_returns(
    strategy_id: str,
    etf_prices: pd.DataFrame,
    stock_prices: pd.DataFrame | None = None,
    vix: pd.Series | None = None,
    crypto_prices: pd.DataFrame | None = None,
    btc_prices: pd.Series | None = None,
    apply_costs: bool = True,
    strategy_params: dict | None = None,
) -> pd.Series:
    """Generate returns for a single strategy, net of transaction costs.

    C6 fix 2026-04-21: computes signals + returns inline (instead of calling
    `strategy.generate_returns`) so the signal DataFrame is available to
    price-in per-rebalance slippage / bid-ask via `apply_transaction_costs`.
    Set `apply_costs=False` to recover the pre-C6 gross-return behavior
    (useful for calibration / stress tests).

    `strategy_params` (research only): optional {strategy_id: {kwargs}} forwarded
    to the strategy constructor. A "market_caps" entry is injected via
    set_market_caps() rather than the constructor. Default None → unchanged
    live behavior.
    """
    params = dict((strategy_params or {}).get(strategy_id, {}))
    market_caps = params.pop("market_caps", None)

    if strategy_id in CRYPTO_STRATEGIES:
        strategy = CRYPTO_STRATEGIES[strategy_id](**params)
        if btc_prices is not None:
            strategy.set_btc(btc_prices)
        prices_df = crypto_prices
    elif strategy_id in STOCK_STRATEGIES:
        strategy = STOCK_STRATEGIES[strategy_id](**params)
        if vix is not None:
            strategy.set_vix(vix)
        if market_caps is not None and hasattr(strategy, "set_market_caps"):
            strategy.set_market_caps(market_caps)
        prices_df = stock_prices
    else:
        strategy = ETF_STRATEGIES[strategy_id](**params)
        prices_df = etf_prices

    signals = strategy.generate_signals(prices_df)
    asset_returns = prices_df.pct_change()
    returns = (signals.shift(1) * asset_returns).sum(axis=1).dropna()

    if apply_costs:
        from backtesting.costs import apply_transaction_costs, cost_bps_for_strategy
        returns = apply_transaction_costs(
            returns, signals, cost_bps_for_strategy(strategy_id)
        )

    # Trim warmup
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    return returns


def apply_vol_scaling(
    returns: pd.Series,
    vol_target: float = 0.15,
    vol_halflife: int = 21,
    scalar_floor: float = 0.5,
    scalar_cap: float = 1.0,
) -> pd.Series:
    """Apply volatility-scaling overlay to portfolio returns.

    Scales exposure inversely to recent realized volatility. When the market
    is calm, take more risk. When turbulent, take less.

    Academic basis:
    - Moreira & Muir (2017): "Volatility-Managed Portfolios"
      Scaling by inverse vol adds +0.1-0.3 Sharpe because high-vol periods
      do not compensate with proportionally higher returns.
    - Barroso & Santa-Clara (2015): Vol-scaling on momentum eliminates crashes.

    Args:
        returns: Daily strategy returns
        vol_target: Target annualized vol (0.15 = 15%)
        vol_halflife: EWMA half-life in days for vol estimation
        scalar_floor: Minimum exposure (0.5 = never below 50%)
        scalar_cap: Maximum exposure. 1.0 = no leverage; >1.0 extends into
                    Reg-T margin in calm regimes (equity accounts only —
                    Alpaca crypto is non-marginable and stays capped at 1.0
                    in the live path).

    Returns:
        Vol-scaled daily returns
    """
    # EWMA realized vol (responds faster to regime changes than rolling window)
    ewma_var = returns.ewm(halflife=vol_halflife).var()
    realized_vol = np.sqrt(ewma_var) * np.sqrt(252)

    # Scalar: target / realized, capped
    scalar = vol_target / realized_vol.replace(0, np.nan)
    scalar = scalar.clip(lower=scalar_floor, upper=scalar_cap)

    # Lag by 1 day (use yesterday's vol estimate for today's sizing)
    scalar = scalar.shift(1).fillna(1.0)

    return returns * scalar


def run_portfolio(
    portfolio_id: str,
    start: str = "2010-01-01",
    end: str | None = None,
    apply_costs: bool = True,
    strategy_params: dict | None = None,
) -> tuple[str, pd.Series]:
    """Run a combined portfolio and return (name, returns Series).

    Args:
        portfolio_id: Key into PORTFOLIOS dict
        start: Backtest start date
        end: Backtest end date (optional)
        apply_costs: Apply per-strategy transaction costs (C6 fix 2026-04-21).
            Default True — sim/live parity. Set False for gross-return
            calibration runs.
        strategy_params: Research-only {strategy_id: {kwargs}} forwarded to the
            component strategy (e.g. weighting_scheme, market_caps). Default
            None → unchanged live behavior.

    Returns:
        Tuple of (portfolio_name, combined_returns_series)
    """
    config = PORTFOLIOS[portfolio_id]
    weights = config["weights"]
    use_spy_filter = config["spy_filter"]
    use_btc_filter = config.get("btc_filter", False)
    use_vol_scaling = config.get("vol_scaling", False)
    vol_scaling_params = config.get("vol_scaling_params", {})

    # Load data
    symbols = EXPANDED_UNIVERSE + ["SHY"]
    etf_prices = download_and_cache(symbols, start=start, end=end, cache_name="etf_prices")

    stock_prices = None
    vix = None
    if any(sid in STOCK_STRATEGIES for sid in weights):
        stock_prices = download_sp500_prices(start=start)
        vix = download_vix()

    crypto_prices = None
    btc_prices = None
    if any(sid in CRYPTO_STRATEGIES for sid in weights):
        crypto_prices = download_crypto_prices(start=start, symbols=LIVE_CRYPTO_UNIVERSE)
        btc_prices = download_btc_prices()

    # Generate returns for each component strategy
    strategy_returns = {}
    for strategy_id in weights:
        strategy_returns[strategy_id] = _generate_strategy_returns(
            strategy_id, etf_prices, stock_prices, vix, crypto_prices, btc_prices,
            apply_costs=apply_costs, strategy_params=strategy_params,
        )

    # Align to common dates and compute weighted blend
    aligned = pd.DataFrame(strategy_returns).dropna()
    combined = sum(aligned[sid] * w for sid, w in weights.items())

    # Apply SPY trend filter
    if use_spy_filter:
        spy_filter = compute_spy_trend_filter(start=start)
        spy_aligned = spy_filter.reindex(combined.index).ffill().fillna(1.0)
        combined = combined * spy_aligned

    # Apply BTC trend filter (binary: 1.0 or 0.0)
    if use_btc_filter:
        btc_filter = compute_btc_trend_filter(start=start)
        btc_aligned = btc_filter.reindex(combined.index).ffill().fillna(1.0)
        combined = combined * btc_aligned

    # Apply vol-scaling overlay (Moreira & Muir 2017)
    if use_vol_scaling:
        combined = apply_vol_scaling(combined, **vol_scaling_params)

    return config["name"], combined


# Live book after A3 retirement (2026-04-21): A1 + A2 + A4 at 1/3 each.
LIVE_ACCOUNT_STRATEGIES = ["sm_filtered", "trend_lowvol", "crypto_momentum_filtered"]

# Equity-only core (A1 + A2) — base for A4's marginal portfolio contribution.
EQUITY_CORE_STRATEGIES = ["sm_filtered", "trend_lowvol"]


def run_equity_core(
    start: str = "2010-01-01",
    end: str | None = None,
    apply_costs: bool = True,
) -> tuple[str, pd.Series]:
    """Run the equity-only core (A1 + A2) at 50/50 on the equity calendar.

    Used as the "existing book" base when measuring A4's marginal
    portfolio contribution. Returns a 252-day-convention series.
    """
    account_returns = {}
    for pid in EQUITY_CORE_STRATEGIES:
        _, returns = run_portfolio(pid, start=start, end=end, apply_costs=apply_costs)
        account_returns[pid] = returns

    aligned = pd.DataFrame(account_returns).dropna()
    combined = aligned.mean(axis=1)
    return "Equity Core (A1 + A2)", combined


def run_combined_portfolio(
    start: str = "2010-01-01",
    end: str | None = None,
    apply_costs: bool = True,
) -> tuple[str, pd.Series]:
    """Run the full live book: A1 + A2 + A4 at 1/3 each on the equity calendar.

    A4's crypto returns are compounded across weekends so Monday's A4 return
    reflects the Fri→Mon cumulative BTC move. The series starts from the
    latest strategy's first day (A4 inception = 2020-09-11). Callers
    annualize with periods_per_year=252.
    """
    account_returns = {}
    for pid in LIVE_ACCOUNT_STRATEGIES:
        _, returns = run_portfolio(pid, start=start, end=end, apply_costs=apply_costs)
        non_zero = returns[(returns != 0) & returns.notna()]
        if len(non_zero):
            returns = returns.loc[non_zero.index[0]:]
        account_returns[pid] = returns

    eq_cal = account_returns["sm_filtered"].index.union(
        account_returns["trend_lowvol"].index
    )
    latest_start = max(s.index[0] for s in account_returns.values())
    eq_cal = eq_cal[eq_cal >= latest_start]

    def _to_equity_calendar(r: pd.Series) -> pd.Series:
        equity_curve = (1.0 + r).cumprod()
        on_eq = equity_curve.reindex(eq_cal, method="ffill")
        return on_eq.pct_change()

    on_calendar = {k: _to_equity_calendar(v) for k, v in account_returns.items()}
    df = pd.DataFrame(on_calendar).dropna()
    combined = df.mean(axis=1)
    return "Combined Live Portfolio (A1 + A2 + A4)", combined
