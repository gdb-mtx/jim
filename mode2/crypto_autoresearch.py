"""
Crypto Strategy Autoresearch — Comprehensive Parameter Sweep.

Tests all tunable levers on the Crypto Momentum Rotation strategy:
1. BTC trend filter type + period (from filter_backtest results: 150d family wins)
2. Momentum lookback period (7, 14, 21, 30, 42, 60 days)
3. Number of coins to hold (1, 2, 3, 4, 5)
4. Rebalance frequency (1, 2, 3, 5, 7 days)
5. Vol-scaling target (0.10, 0.15, 0.20, 0.25)
6. Momentum type (simple return vs risk-adjusted)

Two-pass approach:
  Pass 1: Sweep each parameter independently (holding others at current defaults)
  Pass 2: Combine the best from each dimension into candidate configurations

Usage:
    uv run python3 -m mode2.crypto_autoresearch
"""

import warnings
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from backtesting.metrics import full_report
from data.crypto import download_crypto_prices, download_btc_prices
from strategies.crypto_momentum import CryptoMomentum
from strategies.portfolio import apply_vol_scaling

warnings.filterwarnings("ignore")

START_DATE = "2018-01-01"


@dataclass
class Config:
    name: str
    filter_type: str  # "sma", "ema", "dual", "none"
    filter_period: int
    filter_fast: int  # For dual MA only
    lookback: int
    top_n: int
    rebal_days: int
    vol_target: float
    risk_adj_momentum: bool  # Divide momentum by rolling vol


@dataclass
class Result:
    config: Config
    sharpe: float
    cagr: float
    max_dd: float
    calmar: float
    total_return: float
    win_rate: float
    pct_invested: float


# Current defaults
DEFAULTS = Config(
    name="Current",
    filter_type="sma",
    filter_period=200,
    filter_fast=0,
    lookback=21,
    top_n=3,
    rebal_days=1,
    vol_target=0.15,
    risk_adj_momentum=False,
)


def run_config(prices: pd.DataFrame, btc: pd.Series, cfg: Config) -> Result:
    """Run strategy with a specific configuration and return results."""
    strat = CryptoMomentum(
        lookback_days=cfg.lookback,
        top_n=cfg.top_n,
        holding_period_days=cfg.rebal_days,
        btc_ma_period=cfg.filter_period,
    )

    btc_aligned = btc.reindex(prices.index).ffill()

    # MAs computed on full BTC history (strict min_periods) then reindexed to
    # prices.index, so half-sliced backtests use pre-slice BTC for warmup.
    if cfg.filter_type == "none":
        filter_scalar = pd.Series(1.0, index=prices.index)
        pct_invested = 100.0
    elif cfg.filter_type == "sma":
        ma_full = btc.rolling(cfg.filter_period, min_periods=cfg.filter_period).mean()
        ma = ma_full.reindex(prices.index).ffill()
        filter_scalar = pd.Series(np.where(btc_aligned > ma, 1.0, 0.0), index=prices.index)
        pct_invested = (btc_aligned > ma).mean() * 100
    elif cfg.filter_type == "ema":
        ma_full = btc.ewm(span=cfg.filter_period, min_periods=cfg.filter_period).mean()
        ma = ma_full.reindex(prices.index).ffill()
        filter_scalar = pd.Series(np.where(btc_aligned > ma, 1.0, 0.0), index=prices.index)
        pct_invested = (btc_aligned > ma).mean() * 100
    elif cfg.filter_type == "dual":
        fast_full = btc.rolling(cfg.filter_fast, min_periods=cfg.filter_fast).mean()
        slow_full = btc.rolling(cfg.filter_period, min_periods=cfg.filter_period).mean()
        fast_ma = fast_full.reindex(prices.index).ffill()
        slow_ma = slow_full.reindex(prices.index).ffill()
        filter_scalar = pd.Series(np.where(fast_ma > slow_ma, 1.0, 0.0), index=prices.index)
        pct_invested = (fast_ma > slow_ma).mean() * 100
    else:
        raise ValueError(f"Unknown filter type: {cfg.filter_type}")

    # Generate momentum signals — optionally use risk-adjusted momentum
    if cfg.risk_adj_momentum:
        # Risk-adjusted momentum: return / rolling volatility
        raw_returns = prices.pct_change()
        rolling_vol = raw_returns.rolling(cfg.lookback, min_periods=max(cfg.lookback // 2, 5)).std()
        momentum = prices.pct_change(cfg.lookback) / (rolling_vol + 1e-8)
    else:
        momentum = prices.pct_change(cfg.lookback)

    # Rank and select top N
    n_coins = prices.shape[1]
    ranks = momentum.rank(axis=1, ascending=True, method="average")
    effective_top_n = min(cfg.top_n, max(1, n_coins))
    cutoff = n_coins - effective_top_n
    selected = (ranks > cutoff).astype(float)
    n_selected = selected.sum(axis=1).replace(0, 1)
    weights = selected.div(n_selected, axis=0)

    # Apply filter
    weights = weights.mul(filter_scalar, axis=0)

    # Apply rebalance frequency
    if cfg.rebal_days > 1:
        rebalance_mask = pd.Series(False, index=prices.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[::cfg.rebal_days]
            rebalance_mask.loc[rebalance_dates] = True
        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

    weights = weights.fillna(0)

    # Calculate returns
    daily_returns = prices.pct_change()
    returns = (weights.shift(1) * daily_returns).sum(axis=1)

    # Trim warmup
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    # Apply vol-scaling
    if cfg.vol_target > 0:
        returns = apply_vol_scaling(
            returns,
            vol_target=cfg.vol_target,
            vol_halflife=30,
            scalar_floor=0.1,
            scalar_cap=2.0,
        )

    report = full_report(returns, periods_per_year=365)
    cagr = report["annualized_return"]
    years = report["total_periods"] / 365
    total_ret = (1 + cagr) ** years - 1 if years > 0 else 0

    return Result(
        config=cfg,
        sharpe=report["sharpe_ratio"],
        cagr=cagr * 100,
        max_dd=report["max_drawdown"] * 100,
        calmar=report["calmar_ratio"],
        total_return=total_ret * 100,
        win_rate=report.get("win_rate", 0) * 100,
        pct_invested=pct_invested,
    )


def print_sweep(title: str, results: list[Result], sort_by: str = "sharpe"):
    """Print sweep results table."""
    sorted_results = sorted(results, key=lambda r: getattr(r, sort_by), reverse=True)
    print(f"\n{'─' * 85}")
    print(f"  {title}")
    print(f"{'─' * 85}")
    print(f"  {'Config':<30} {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8} {'Calmar':>8} {'TotRet':>9} {'%Inv':>6}")
    for r in sorted_results:
        print(f"  {r.config.name:<30} {r.sharpe:>6.2f}  {r.cagr:>+7.1f}% {r.max_dd:>7.1f}% "
              f"{r.calmar:>7.2f} {r.total_return:>+8.1f}% {r.pct_invested:>5.0f}%")
    best = sorted_results[0]
    print(f"  → Best: {best.config.name} (Sharpe {best.sharpe:.2f})")


def main():
    print("Loading crypto data...")
    prices = download_crypto_prices(start=START_DATE)
    btc = download_btc_prices()
    print(f"  {prices.shape[0]} days, {prices.shape[1]} coins, "
          f"BTC {btc.index[0].date()} to {btc.index[-1].date()}")

    # ════════════════════════════════════════════════
    # PASS 1: Sweep each parameter independently
    # ════════════════════════════════════════════════
    print("\n" + "=" * 85)
    print("PASS 1: Independent Parameter Sweeps")
    print("=" * 85)

    # ── 1. Filter type (already done in filter_backtest, confirm top picks) ──
    filter_results = []
    for ftype, period, fast in [
        ("sma", 150, 0), ("ema", 150, 0), ("dual", 150, 50),
        ("sma", 200, 0), ("none", 200, 0),
    ]:
        cfg = Config(
            name=f"{'Dual-50/' if ftype == 'dual' else ''}{ftype.upper()}-{period}" if ftype != "none" else "No Filter",
            filter_type=ftype, filter_period=period, filter_fast=fast,
            lookback=21, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
        )
        filter_results.append(run_config(prices, btc, cfg))
    print_sweep("1. FILTER TYPE (others at defaults)", filter_results)

    # ── 2. Momentum lookback period ──
    lookback_results = []
    for lb in [7, 10, 14, 21, 30, 42, 60]:
        cfg = Config(
            name=f"Lookback-{lb}d",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=lb, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
        )
        lookback_results.append(run_config(prices, btc, cfg))
    print_sweep("2. MOMENTUM LOOKBACK (filter=SMA-150)", lookback_results)

    # ── 3. Number of coins ──
    topn_results = []
    for n in [1, 2, 3, 4, 5, 7]:
        cfg = Config(
            name=f"Top-{n} coins",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=21, top_n=n, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
        )
        topn_results.append(run_config(prices, btc, cfg))
    print_sweep("3. NUMBER OF COINS (filter=SMA-150)", topn_results)

    # ── 4. Rebalance frequency ──
    rebal_results = []
    for days in [1, 2, 3, 5, 7]:
        cfg = Config(
            name=f"Rebal every {days}d",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=21, top_n=3, rebal_days=days, vol_target=0.15, risk_adj_momentum=False,
        )
        rebal_results.append(run_config(prices, btc, cfg))
    print_sweep("4. REBALANCE FREQUENCY (filter=SMA-150)", rebal_results)

    # ── 5. Vol-scaling target ──
    vol_results = []
    for vt in [0, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25]:
        cfg = Config(
            name=f"VolTarget-{vt:.0%}" if vt > 0 else "No Vol-Scale",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=21, top_n=3, rebal_days=1, vol_target=vt, risk_adj_momentum=False,
        )
        vol_results.append(run_config(prices, btc, cfg))
    print_sweep("5. VOL-SCALING TARGET (filter=SMA-150)", vol_results)

    # ── 6. Risk-adjusted momentum ──
    riskadj_results = []
    for ra in [False, True]:
        cfg = Config(
            name="Simple Momentum" if not ra else "Risk-Adj Momentum",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=21, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=ra,
        )
        riskadj_results.append(run_config(prices, btc, cfg))
    print_sweep("6. MOMENTUM TYPE (filter=SMA-150)", riskadj_results)

    # ════════════════════════════════════════════════
    # PASS 2: Combine best from each dimension
    # ════════════════════════════════════════════════
    print("\n" + "=" * 85)
    print("PASS 2: Candidate Configurations (combining best parameters)")
    print("=" * 85)

    # Find best from each sweep
    best_filter = max(filter_results, key=lambda r: r.sharpe).config
    best_lookback = max(lookback_results, key=lambda r: r.sharpe).config.lookback
    best_topn = max(topn_results, key=lambda r: r.sharpe).config.top_n
    best_rebal = max(rebal_results, key=lambda r: r.sharpe).config.rebal_days
    best_vol = max(vol_results, key=lambda r: r.sharpe).config.vol_target
    best_riskadj = max(riskadj_results, key=lambda r: r.sharpe).config.risk_adj_momentum

    print(f"\n  Best per dimension:")
    print(f"    Filter: {best_filter.filter_type.upper()}-{best_filter.filter_period}")
    print(f"    Lookback: {best_lookback}d")
    print(f"    Top N: {best_topn}")
    print(f"    Rebalance: {best_rebal}d")
    print(f"    Vol target: {best_vol:.0%}")
    print(f"    Risk-adj: {best_riskadj}")

    # Build candidate configs
    candidates = []

    # Current baseline
    candidates.append(run_config(prices, btc, Config(
        name="CURRENT (SMA-200/21d/top3/daily/15%)",
        filter_type="sma", filter_period=200, filter_fast=0,
        lookback=21, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
    )))

    # Best of each dimension combined
    candidates.append(run_config(prices, btc, Config(
        name="COMBINED BEST",
        filter_type=best_filter.filter_type,
        filter_period=best_filter.filter_period,
        filter_fast=best_filter.filter_fast,
        lookback=best_lookback, top_n=best_topn,
        rebal_days=best_rebal, vol_target=best_vol,
        risk_adj_momentum=best_riskadj,
    )))

    # Just filter upgrade (minimal change)
    candidates.append(run_config(prices, btc, Config(
        name="FILTER ONLY (SMA-150)",
        filter_type="sma", filter_period=150, filter_fast=0,
        lookback=21, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
    )))

    # Filter + best lookback
    candidates.append(run_config(prices, btc, Config(
        name=f"SMA-150 + {best_lookback}d lookback",
        filter_type="sma", filter_period=150, filter_fast=0,
        lookback=best_lookback, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
    )))

    # Conservative: Dual-50/150 (best Calmar from filter test)
    candidates.append(run_config(prices, btc, Config(
        name="CONSERVATIVE (Dual-50/150)",
        filter_type="dual", filter_period=150, filter_fast=50,
        lookback=21, top_n=3, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
    )))

    # Aggressive: combine best filter + lookback + topn
    candidates.append(run_config(prices, btc, Config(
        name=f"AGGRESSIVE ({best_lookback}d/top{best_topn})",
        filter_type="sma", filter_period=150, filter_fast=0,
        lookback=best_lookback, top_n=best_topn,
        rebal_days=1, vol_target=best_vol, risk_adj_momentum=best_riskadj,
    )))

    # Test a few more interesting combos
    for lb, tn in [(14, 2), (14, 3), (21, 2), (30, 3)]:
        candidates.append(run_config(prices, btc, Config(
            name=f"SMA-150/{lb}d/top{tn}",
            filter_type="sma", filter_period=150, filter_fast=0,
            lookback=lb, top_n=tn, rebal_days=1, vol_target=0.15, risk_adj_momentum=False,
        )))

    print_sweep("CANDIDATE CONFIGURATIONS", candidates)

    # Final recommendation
    best = max(candidates, key=lambda r: r.sharpe)
    current = candidates[0]
    print(f"\n{'=' * 85}")
    print(f"  RECOMMENDATION")
    print(f"{'=' * 85}")
    print(f"  Best config: {best.config.name}")
    print(f"    Sharpe: {best.sharpe:.2f} (current: {current.sharpe:.2f}, delta: {best.sharpe - current.sharpe:+.2f})")
    print(f"    CAGR:   {best.cagr:+.1f}% (current: {current.cagr:+.1f}%, delta: {best.cagr - current.cagr:+.1f}%)")
    print(f"    MaxDD:  {best.max_dd:.1f}% (current: {current.max_dd:.1f}%, delta: {best.max_dd - current.max_dd:+.1f}%)")
    print(f"    Calmar: {best.calmar:.2f} (current: {current.calmar:.2f})")
    print(f"\n  Parameters:")
    c = best.config
    print(f"    Filter: {c.filter_type.upper()}-{c.filter_period}" +
          (f" (fast={c.filter_fast})" if c.filter_type == "dual" else ""))
    print(f"    Lookback: {c.lookback} days")
    print(f"    Top N: {c.top_n} coins")
    print(f"    Rebalance: every {c.rebal_days} day(s)")
    print(f"    Vol target: {c.vol_target:.0%}")
    print(f"    Risk-adj momentum: {c.risk_adj_momentum}")


if __name__ == "__main__":
    main()
