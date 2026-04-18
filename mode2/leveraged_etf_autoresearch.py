"""
Leveraged ETF Momentum Rotation — Research Thread 6.

Applies the crypto strategy template (concentrated momentum + binary trend filter
+ vol-scaling) to 3x leveraged ETFs. These have crypto-like volatility (40-60%
annualized) — the raw material for momentum strategies.

Key hypothesis: The same properties that make crypto momentum work (high vol,
strong trends, binary filter cutting drawdowns) should transfer to leveraged ETFs.

Dimensions swept:
1. Filter type: SPY 200d MA (binary), SPY 150d, no filter
2. Momentum lookback: 10, 14, 21, 30, 42, 63 days
3. Number of ETFs to hold: 1, 2, 3, 4, 5
4. Rebalance frequency: 1, 2, 3, 5 days
5. Vol-scaling target: 0%, 10%, 15%, 20%, 25%
6. Momentum type: simple return vs risk-adjusted (return/vol)

Universe: 12 liquid 3x leveraged ETFs with 15+ years of history (2010+)
  TQQQ (Nasdaq 3x), UPRO (S&P 3x), SOXL (Semis 3x), TNA (Russell 2000 3x),
  TECL (Tech 3x), FAS (Financials 3x), SPXL (S&P 3x), ERX (Energy 3x),
  MIDU (MidCap 3x), UMDD (MidCap 3x), URTY (Russell 2000 3x), RETL (Retail 3x)

Usage:
    uv run python3 -m mode2.leveraged_etf_autoresearch
"""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
import yfinance as yf

from backtesting.metrics import full_report
from strategies.portfolio import apply_vol_scaling

warnings.filterwarnings("ignore")

# ── Universe ────────────────────────────────────────────────────────
# Core 3x leveraged ETFs with 15+ years of history
LEVERAGED_UNIVERSE = [
    "TQQQ",  # Nasdaq-100 3x
    "UPRO",  # S&P 500 3x
    "SOXL",  # Semiconductors 3x
    "TNA",   # Russell 2000 3x
    "TECL",  # Technology 3x
    "FAS",   # Financials 3x
    "SPXL",  # S&P 500 3x (Direxion)
    "ERX",   # Energy 3x
    "MIDU",  # MidCap 400 3x
    "UMDD",  # MidCap 400 3x (ProShares)
    "URTY",  # Russell 2000 3x (ProShares)
    "RETL",  # Retail 3x
]

# Note: UPRO and SPXL both track S&P 500 3x (different issuers).
# MIDU and UMDD both track MidCap 400 3x. TNA and URTY both track Russell 2000 3x.
# This gives the strategy a choice — the one with better recent momentum wins.
# If we want to avoid overlap, we can reduce to a "unique sector" subset.

UNIQUE_SECTOR_UNIVERSE = [
    "TQQQ",  # Nasdaq-100
    "UPRO",  # S&P 500
    "SOXL",  # Semiconductors
    "TNA",   # Russell 2000
    "TECL",  # Technology
    "FAS",   # Financials
    "ERX",   # Energy
    "MIDU",  # MidCap 400
    "RETL",  # Retail
]

START_DATE = "2010-07-15"  # When RETL starts — ensures all ETFs have data


@dataclass
class Config:
    name: str
    filter_type: str   # "spy_sma", "spy_ema", "none"
    filter_period: int
    lookback: int
    top_n: int
    rebal_days: int
    vol_target: float
    risk_adj_momentum: bool
    universe: list[str] | None = None  # None = use default


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


# Defaults — starting point for sweeps
DEFAULTS = Config(
    name="Baseline",
    filter_type="spy_sma",
    filter_period=200,
    lookback=21,
    top_n=3,
    rebal_days=1,
    vol_target=0.15,
    risk_adj_momentum=False,
)


def download_leveraged_prices(
    symbols: list[str] | None = None,
    start: str = START_DATE,
) -> pd.DataFrame:
    """Download leveraged ETF prices from yfinance."""
    if symbols is None:
        symbols = LEVERAGED_UNIVERSE
    df = yf.download(symbols, start=start, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        prices = df["Close"]
    else:
        prices = df[["Close"]]
        prices.columns = symbols
    prices = prices.dropna(how="all").ffill(limit=5)
    return prices


def download_spy_prices(start: str = START_DATE) -> pd.Series:
    """Download SPY prices for trend filter."""
    df = yf.download("SPY", start=start, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        return df["Close"]["SPY"].dropna()
    return df["Close"].dropna()


def run_config(prices: pd.DataFrame, spy: pd.Series, cfg: Config) -> Result:
    """Run the momentum rotation strategy with a specific configuration."""
    # Use subset of universe if specified
    if cfg.universe is not None:
        available = [s for s in cfg.universe if s in prices.columns]
        p = prices[available].copy()
    else:
        p = prices.copy()

    spy_aligned = spy.reindex(p.index).ffill()

    # ── Build filter scalar ──
    if cfg.filter_type == "none":
        filter_scalar = pd.Series(1.0, index=p.index)
        pct_invested = 100.0
    elif cfg.filter_type == "spy_sma":
        ma = spy_aligned.rolling(cfg.filter_period, min_periods=1).mean()
        filter_scalar = pd.Series(
            np.where(spy_aligned > ma, 1.0, 0.0), index=p.index
        )
        pct_invested = (spy_aligned > ma).mean() * 100
    elif cfg.filter_type == "spy_ema":
        ma = spy_aligned.ewm(span=cfg.filter_period, min_periods=1).mean()
        filter_scalar = pd.Series(
            np.where(spy_aligned > ma, 1.0, 0.0), index=p.index
        )
        pct_invested = (spy_aligned > ma).mean() * 100
    else:
        raise ValueError(f"Unknown filter type: {cfg.filter_type}")

    # ── Momentum signal ──
    if cfg.risk_adj_momentum:
        raw_returns = p.pct_change()
        rolling_vol = raw_returns.rolling(
            cfg.lookback, min_periods=max(cfg.lookback // 2, 5)
        ).std()
        momentum = p.pct_change(cfg.lookback) / (rolling_vol + 1e-8)
    else:
        momentum = p.pct_change(cfg.lookback)

    # ── Rank and select top N ──
    n_assets = p.shape[1]
    ranks = momentum.rank(axis=1, ascending=True, method="average")
    effective_top_n = min(cfg.top_n, max(1, n_assets))
    cutoff = n_assets - effective_top_n
    selected = (ranks > cutoff).astype(float)
    n_selected = selected.sum(axis=1).replace(0, 1)
    weights = selected.div(n_selected, axis=0)

    # ── Apply filter ──
    weights = weights.mul(filter_scalar, axis=0)

    # ── Apply rebalance frequency ──
    if cfg.rebal_days > 1:
        rebalance_mask = pd.Series(False, index=p.index)
        valid_idx = weights.dropna(how="all").index
        if len(valid_idx) > 0:
            rebalance_dates = valid_idx[:: cfg.rebal_days]
            rebalance_mask.loc[rebalance_dates] = True
        weights[~rebalance_mask] = np.nan
        weights = weights.ffill()

    weights = weights.fillna(0)

    # ── Calculate returns ──
    daily_returns = p.pct_change()
    returns = (weights.shift(1) * daily_returns).sum(axis=1)

    # Trim warmup
    non_zero = returns[returns != 0]
    if len(non_zero) > 0:
        returns = returns.loc[non_zero.index[0]:]

    # ── Vol-scaling ──
    if cfg.vol_target > 0:
        returns = apply_vol_scaling(
            returns,
            vol_target=cfg.vol_target,
            vol_halflife=30,
            scalar_floor=0.1,
            scalar_cap=2.0,
        )

    if len(returns) < 60:
        return Result(
            config=cfg, sharpe=0, cagr=0, max_dd=0,
            calmar=0, total_return=0, win_rate=0, pct_invested=pct_invested,
        )

    report = full_report(returns, periods_per_year=252)
    cagr = report["annualized_return"]
    years = report["total_periods"] / 252
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
    sorted_results = sorted(
        results, key=lambda r: getattr(r, sort_by), reverse=True
    )
    print(f"\n{'─' * 90}")
    print(f"  {title}")
    print(f"{'─' * 90}")
    print(
        f"  {'Config':<32} {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8} "
        f"{'Calmar':>8} {'TotRet':>10} {'%Inv':>6}"
    )
    for r in sorted_results:
        print(
            f"  {r.config.name:<32} {r.sharpe:>6.2f}  {r.cagr:>+7.1f}% "
            f"{r.max_dd:>7.1f}% {r.calmar:>7.2f} {r.total_return:>+9.1f}% "
            f"{r.pct_invested:>5.0f}%"
        )
    best = sorted_results[0]
    print(f"  → Best: {best.config.name} (Sharpe {best.sharpe:.2f})")


def main():
    print("=" * 90)
    print("RESEARCH THREAD 6: Leveraged ETF Momentum Rotation")
    print("=" * 90)

    print("\nLoading data...")
    prices = download_leveraged_prices()
    spy = download_spy_prices()
    print(f"  Leveraged ETFs: {prices.shape[1]} assets, {prices.shape[0]} days")
    print(f"  Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
    print(f"  SPY: {len(spy)} days")

    # Show which ETFs we have
    coverage = {col: prices[col].dropna().shape[0] for col in prices.columns}
    print(f"\n  ETF coverage (trading days):")
    for etf, days in sorted(coverage.items(), key=lambda x: -x[1]):
        start = prices[etf].dropna().index[0].date()
        print(f"    {etf:6s}: {days:4d} days (from {start})")

    # ── Benchmarks ──
    print("\n" + "=" * 90)
    print("BENCHMARKS")
    print("=" * 90)

    benchmarks = []
    # SPY buy-and-hold
    spy_ret = spy.pct_change().dropna()
    spy_report = full_report(spy_ret, periods_per_year=252)
    benchmarks.append(Result(
        config=Config("SPY Buy & Hold", "none", 0, 0, 0, 0, 0, False),
        sharpe=spy_report["sharpe_ratio"],
        cagr=spy_report["annualized_return"] * 100,
        max_dd=spy_report["max_drawdown"] * 100,
        calmar=spy_report["calmar_ratio"],
        total_return=((1 + spy_report["annualized_return"])
                      ** (spy_report["total_periods"] / 252) - 1) * 100,
        win_rate=spy_report.get("win_rate", 0) * 100,
        pct_invested=100.0,
    ))

    # TQQQ buy-and-hold (as a leveraged benchmark)
    tqqq_ret = prices["TQQQ"].pct_change().dropna()
    tqqq_report = full_report(tqqq_ret, periods_per_year=252)
    benchmarks.append(Result(
        config=Config("TQQQ Buy & Hold", "none", 0, 0, 0, 0, 0, False),
        sharpe=tqqq_report["sharpe_ratio"],
        cagr=tqqq_report["annualized_return"] * 100,
        max_dd=tqqq_report["max_drawdown"] * 100,
        calmar=tqqq_report["calmar_ratio"],
        total_return=((1 + tqqq_report["annualized_return"])
                      ** (tqqq_report["total_periods"] / 252) - 1) * 100,
        win_rate=tqqq_report.get("win_rate", 0) * 100,
        pct_invested=100.0,
    ))

    print_sweep("BENCHMARKS", benchmarks)

    # ════════════════════════════════════════════════
    # PASS 1: Independent Parameter Sweeps
    # ════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("PASS 1: Independent Parameter Sweeps")
    print("=" * 90)

    # ── 1. Filter type ──
    filter_results = []
    for ftype, period in [
        ("spy_sma", 100), ("spy_sma", 150), ("spy_sma", 200),
        ("spy_sma", 250), ("spy_ema", 150), ("spy_ema", 200),
        ("none", 0),
    ]:
        name = f"{ftype.upper()}-{period}" if ftype != "none" else "No Filter"
        cfg = Config(
            name=name,
            filter_type=ftype, filter_period=period,
            lookback=21, top_n=3, rebal_days=1,
            vol_target=0.15, risk_adj_momentum=False,
        )
        filter_results.append(run_config(prices, spy, cfg))
    print_sweep("1. FILTER TYPE (others at defaults)", filter_results)

    # ── 2. Momentum lookback ──
    lookback_results = []
    best_filter = max(filter_results, key=lambda r: r.sharpe).config
    for lb in [5, 10, 14, 21, 30, 42, 63]:
        cfg = Config(
            name=f"Lookback-{lb}d",
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=lb, top_n=3, rebal_days=1,
            vol_target=0.15, risk_adj_momentum=False,
        )
        lookback_results.append(run_config(prices, spy, cfg))
    print_sweep(f"2. MOMENTUM LOOKBACK (filter={best_filter.name})", lookback_results)

    # ── 3. Number of ETFs ──
    topn_results = []
    best_lb = max(lookback_results, key=lambda r: r.sharpe).config.lookback
    for n in [1, 2, 3, 4, 5, 6]:
        cfg = Config(
            name=f"Top-{n} ETFs",
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=best_lb, top_n=n, rebal_days=1,
            vol_target=0.15, risk_adj_momentum=False,
        )
        topn_results.append(run_config(prices, spy, cfg))
    print_sweep(f"3. NUMBER OF ETFs (lookback={best_lb}d)", topn_results)

    # ── 4. Rebalance frequency ──
    rebal_results = []
    best_topn = max(topn_results, key=lambda r: r.sharpe).config.top_n
    for days in [1, 2, 3, 5, 7, 10]:
        cfg = Config(
            name=f"Rebal every {days}d",
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=best_lb, top_n=best_topn, rebal_days=days,
            vol_target=0.15, risk_adj_momentum=False,
        )
        rebal_results.append(run_config(prices, spy, cfg))
    print_sweep(f"4. REBALANCE FREQUENCY (top{best_topn}/{best_lb}d)", rebal_results)

    # ── 5. Vol-scaling target ──
    vol_results = []
    best_rebal = max(rebal_results, key=lambda r: r.sharpe).config.rebal_days
    for vt in [0, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30]:
        name = f"VolTarget-{vt:.0%}" if vt > 0 else "No Vol-Scale"
        cfg = Config(
            name=name,
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=best_lb, top_n=best_topn, rebal_days=best_rebal,
            vol_target=vt, risk_adj_momentum=False,
        )
        vol_results.append(run_config(prices, spy, cfg))
    print_sweep(f"5. VOL-SCALING TARGET", vol_results)

    # ── 6. Risk-adjusted momentum ──
    best_vol = max(vol_results, key=lambda r: r.sharpe).config.vol_target
    riskadj_results = []
    for ra in [False, True]:
        cfg = Config(
            name="Simple Momentum" if not ra else "Risk-Adj Momentum",
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=best_lb, top_n=best_topn, rebal_days=best_rebal,
            vol_target=best_vol, risk_adj_momentum=ra,
        )
        riskadj_results.append(run_config(prices, spy, cfg))
    print_sweep("6. MOMENTUM TYPE", riskadj_results)

    # ── 7. Universe: full vs unique-sector ──
    universe_results = []
    best_riskadj = max(riskadj_results, key=lambda r: r.sharpe).config.risk_adj_momentum
    for univ_name, univ in [("Full (12 ETFs)", None), ("Unique Sectors (9)", UNIQUE_SECTOR_UNIVERSE)]:
        cfg = Config(
            name=univ_name,
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=best_lb, top_n=best_topn, rebal_days=best_rebal,
            vol_target=best_vol, risk_adj_momentum=best_riskadj,
            universe=univ,
        )
        universe_results.append(run_config(prices, spy, cfg))
    print_sweep("7. UNIVERSE SIZE", universe_results)

    # ════════════════════════════════════════════════
    # PASS 2: Candidate Configurations
    # ════════════════════════════════════════════════
    print("\n" + "=" * 90)
    print("PASS 2: Candidate Configurations (combining best parameters)")
    print("=" * 90)

    best_univ = max(universe_results, key=lambda r: r.sharpe).config.universe

    print(f"\n  Best per dimension:")
    print(f"    Filter: {best_filter.filter_type.upper()}-{best_filter.filter_period}")
    print(f"    Lookback: {best_lb}d")
    print(f"    Top N: {best_topn}")
    print(f"    Rebalance: {best_rebal}d")
    print(f"    Vol target: {best_vol:.0%}" if best_vol > 0 else "    Vol target: None")
    print(f"    Risk-adj: {best_riskadj}")
    print(f"    Universe: {'Unique Sectors' if best_univ else 'Full'}")

    candidates = []

    # Naive baseline: equal-weight all ETFs, no filter, no vol-scaling
    candidates.append(run_config(prices, spy, Config(
        name="NAIVE (no filter/vol-scale)",
        filter_type="none", filter_period=0,
        lookback=21, top_n=3, rebal_days=1,
        vol_target=0, risk_adj_momentum=False,
    )))

    # Current crypto-style defaults
    candidates.append(run_config(prices, spy, Config(
        name="CRYPTO TEMPLATE (SMA-200/21d/3)",
        filter_type="spy_sma", filter_period=200,
        lookback=21, top_n=3, rebal_days=1,
        vol_target=0.15, risk_adj_momentum=False,
    )))

    # Combined best from all dimensions
    candidates.append(run_config(prices, spy, Config(
        name="COMBINED BEST",
        filter_type=best_filter.filter_type,
        filter_period=best_filter.filter_period,
        lookback=best_lb, top_n=best_topn, rebal_days=best_rebal,
        vol_target=best_vol, risk_adj_momentum=best_riskadj,
        universe=best_univ,
    )))

    # Filter-only upgrade
    candidates.append(run_config(prices, spy, Config(
        name=f"FILTER ONLY ({best_filter.name})",
        filter_type=best_filter.filter_type,
        filter_period=best_filter.filter_period,
        lookback=21, top_n=3, rebal_days=1,
        vol_target=0.15, risk_adj_momentum=False,
    )))

    # Test some interesting combos
    for lb, tn in [(10, 1), (10, 2), (14, 2), (21, 2), (21, 1), (30, 2), (42, 3)]:
        candidates.append(run_config(prices, spy, Config(
            name=f"{best_filter.filter_type.upper()}-{best_filter.filter_period}/{lb}d/top{tn}",
            filter_type=best_filter.filter_type,
            filter_period=best_filter.filter_period,
            lookback=lb, top_n=tn, rebal_days=1,
            vol_target=best_vol, risk_adj_momentum=best_riskadj,
            universe=best_univ,
        )))

    # Conservative: longer filter, more diversified
    candidates.append(run_config(prices, spy, Config(
        name="CONSERVATIVE (SMA-200/top4/42d)",
        filter_type="spy_sma", filter_period=200,
        lookback=42, top_n=4, rebal_days=1,
        vol_target=0.15, risk_adj_momentum=False,
    )))

    # Aggressive: concentrated, fast lookback
    candidates.append(run_config(prices, spy, Config(
        name="AGGRESSIVE (top1/10d)",
        filter_type=best_filter.filter_type,
        filter_period=best_filter.filter_period,
        lookback=10, top_n=1, rebal_days=1,
        vol_target=best_vol, risk_adj_momentum=best_riskadj,
        universe=best_univ,
    )))

    print_sweep("CANDIDATE CONFIGURATIONS", candidates)

    # ── Final recommendation ──
    best = max(candidates, key=lambda r: r.sharpe)
    baseline = candidates[1]  # Crypto template
    print(f"\n{'=' * 90}")
    print(f"  RECOMMENDATION")
    print(f"{'=' * 90}")
    print(f"  Best config: {best.config.name}")
    print(f"    Sharpe: {best.sharpe:.2f} (baseline: {baseline.sharpe:.2f}, "
          f"delta: {best.sharpe - baseline.sharpe:+.2f})")
    print(f"    CAGR:   {best.cagr:+.1f}% (baseline: {baseline.cagr:+.1f}%, "
          f"delta: {best.cagr - baseline.cagr:+.1f}%)")
    print(f"    MaxDD:  {best.max_dd:.1f}% (baseline: {baseline.max_dd:.1f}%, "
          f"delta: {best.max_dd - baseline.max_dd:+.1f}%)")
    print(f"    Calmar: {best.calmar:.2f} (baseline: {baseline.calmar:.2f})")
    print(f"    Total Return: {best.total_return:+.1f}%")
    print(f"\n  Parameters:")
    c = best.config
    print(f"    Filter: {c.filter_type.upper()}-{c.filter_period}")
    print(f"    Lookback: {c.lookback} days")
    print(f"    Top N: {c.top_n} ETFs")
    print(f"    Rebalance: every {c.rebal_days} day(s)")
    print(f"    Vol target: {c.vol_target:.0%}" if c.vol_target > 0 else "    Vol target: None")
    print(f"    Risk-adj momentum: {c.risk_adj_momentum}")
    print(f"    Universe: {'Unique Sectors' if c.universe else 'Full 12 ETFs'}")

    # Compare to crypto strategy
    print(f"\n  vs Crypto Strategy (for reference):")
    print(f"    Crypto: Sharpe 2.01, CAGR +45.6%, MaxDD -14.1%, Calmar 3.24")
    print(f"    This:   Sharpe {best.sharpe:.2f}, CAGR {best.cagr:+.1f}%, "
          f"MaxDD {best.max_dd:.1f}%, Calmar {best.calmar:.2f}")


if __name__ == "__main__":
    main()
