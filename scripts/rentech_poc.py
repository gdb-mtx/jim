"""
RenTech-flavored weak-signal ensemble POC for Account 5.

Per HUNT_APR2026 addendum, this is the 3-day scout-recommended POC for the
ensemble thesis. "Try harder than normal" directive (2026-04-23): go beyond
the scout's 4-signal baseline and run 5 orthogonal cross-sectional signals
plus market-timing overlays, with full diagnostics.

Signals (cross-sectional ranks, all price-only):
  1. short_reversal        — Jegadeesh 1990, rank worst 5d return up
  2. near_52wh             — George & Hwang 2004, rank nearness to 252d high
  3. low_ivol              — Ang-Hodrick-Xing 2006, residual vol vs SPY
  4. trend_quality         — R² of log-price on time, signed by slope
  5. price_acceleration    — 5d return minus 21d return

Overlays:
  - turn_of_month_boost    — Ariel 1987 / Ogden 1990, exposure multiplier
  - spy_trend_filter       — Faber 2007, 200d MA regime binary 0.5/1.0

Gate (CAGR-first framework per VALIDATION.md):
  - OOS CAGR      ≥ 15%
  - OOS Calmar    ≥ 1.2
  - OOS/IS CAGR   ≥ 70%

Any two gate hits = GREEN LIGHT for full 6-test validation. Otherwise KILL
and document null in HUNT_APR2026.md per the pattern.

Usage:
    uv run python3 scripts/rentech_poc.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore")

from data.sp500 import download_sp500_prices  # noqa: E402
from strategies.rentech_signals import (  # noqa: E402
    combine_ranks,
    low_ivol,
    near_52wh,
    price_acceleration,
    short_reversal,
    signal_orthogonality_matrix,
    spy_trend_filter,
    trend_quality,
    turn_of_month_boost,
)


# --- Config ---
IS_END = "2022-12-31"
OOS_START = "2023-01-01"
OOS_END = "2026-04-20"
TOP_DECILE = 0.10  # Long top-decile composite rank
REBALANCE_DAYS = 21  # Monthly
COST_BPS_ROUNDTRIP = 5.0  # Equity cost layer (AUDIT_MONTH2 C6)
PERIODS_PER_YEAR = 252

GATE_CAGR = 0.15
GATE_CALMAR = 1.20
GATE_OOS_IS_RATIO = 0.70


def _load_spy() -> pd.Series:
    """Load SPY price series from yfinance via the pipeline helper."""
    from data.pipeline import download_with_retry, write_parquet_atomic
    import time

    cache_path = ROOT / "data" / "raw" / "spy.parquet"
    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 16:
            df = pd.read_parquet(cache_path)
            if list(df.columns) == ["SPY"]:
                print(f"Loaded SPY from cache ({len(df)} rows)")
                return df.squeeze()

    print("Downloading SPY from yfinance...")
    df = download_with_retry(["SPY"], start="2009-01-01", min_coverage_ratio=1.0)
    s = df.iloc[:, 0]
    s.name = "SPY"
    write_parquet_atomic(s.to_frame(), cache_path)
    return s


def run_backtest(
    weights: pd.DataFrame,
    prices: pd.DataFrame,
    label: str,
) -> tuple[pd.Series, dict]:
    """Given target weights and prices, compute net daily returns and stats.

    Weights on day t are applied to returns from t to t+1 (standard no-lookahead
    convention — weights.shift(1) at return calc). Cost: 5 bps round-trip per
    unit turnover (half on buy, half on sell).
    """
    price_returns = prices.pct_change().fillna(0)
    gross = (price_returns * weights.shift(1)).sum(axis=1)

    turnover = weights.diff().abs().sum(axis=1).fillna(0)
    cost = turnover * (COST_BPS_ROUNDTRIP / 10_000.0 / 2)
    net = gross - cost

    r = net.dropna()
    if len(r) == 0:
        return net, {}
    cagr = (1 + r).prod() ** (PERIODS_PER_YEAR / len(r)) - 1
    sharpe = (r.mean() / r.std()) * np.sqrt(PERIODS_PER_YEAR) if r.std() > 0 else 0.0
    cum = (1 + r).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(maxdd) if maxdd else 0.0

    return net, {
        "label": label,
        "cagr": cagr,
        "sharpe": sharpe,
        "maxdd": maxdd,
        "calmar": calmar,
        "bars": len(r),
    }


def build_weights_from_rank(
    rank_df: pd.DataFrame,
    top_frac: float,
    rebalance_days: int,
    overlay_mult: pd.Series | None = None,
) -> pd.DataFrame:
    """Given a cross-sectional rank [0,1], select top_frac each rebalance day,
    equal-weight. Optional overlay_mult scales total exposure [0,1]."""
    # Select top_frac each day (rank >= 1 - top_frac)
    threshold = 1 - top_frac
    selected = (rank_df >= threshold).astype(float)
    n_selected = selected.sum(axis=1).replace(0, 1)
    weights = selected.div(n_selected, axis=0)

    # Rebalance cadence: blank non-rebalance days, ffill last rebalance
    rebalance_mask = pd.Series(False, index=rank_df.index)
    valid_idx = weights.dropna(how="all").index
    if len(valid_idx) > 0:
        rebalance_dates = valid_idx[::rebalance_days]
        rebalance_mask.loc[rebalance_dates] = True
    weights[~rebalance_mask] = np.nan
    weights = weights.ffill().fillna(0)

    # Apply exposure overlay
    if overlay_mult is not None:
        aligned = overlay_mult.reindex(weights.index).ffill().fillna(1.0)
        weights = weights.mul(aligned, axis=0)

    return weights


def stats_over_window(net: pd.Series, lo: str, hi: str, label: str) -> dict:
    sliced = net.loc[lo:hi].dropna()
    if len(sliced) == 0:
        return {"label": label, "bars": 0}
    cagr = (1 + sliced).prod() ** (PERIODS_PER_YEAR / len(sliced)) - 1
    sharpe = (sliced.mean() / sliced.std()) * np.sqrt(PERIODS_PER_YEAR) if sliced.std() > 0 else 0
    cum = (1 + sliced).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    calmar = cagr / abs(maxdd) if maxdd else 0.0
    return {
        "label": label,
        "cagr": cagr, "sharpe": sharpe, "maxdd": maxdd, "calmar": calmar,
        "bars": len(sliced),
    }


def main() -> int:
    print("Loading S&P 500 prices + SPY...")
    prices = download_sp500_prices(start="2010-01-01")
    spy = _load_spy().reindex(prices.index).ffill()

    print(f"  prices: {prices.shape[0]} rows × {prices.shape[1]} tickers")
    print(f"  window: {prices.index[0].date()} → {prices.index[-1].date()}")

    # --- Compute signals ---
    print("\nComputing 5 cross-sectional signals...")
    signals = {}
    signals["short_reversal"] = short_reversal(prices, lookback=5)
    print("  [1/5] short_reversal")
    signals["near_52wh"] = near_52wh(prices, lookback=252)
    print("  [2/5] near_52wh")
    signals["low_ivol"] = low_ivol(prices, spy, lookback=63)
    print("  [3/5] low_ivol")
    signals["trend_quality"] = trend_quality(prices, lookback=63)
    print("  [4/5] trend_quality")
    signals["price_acceleration"] = price_acceleration(prices, short=5, long=21)
    print("  [5/5] price_acceleration")

    # --- Orthogonality diagnostic ---
    print("\nSignal orthogonality (pairwise Pearson on stacked ranks):")
    orth = signal_orthogonality_matrix(signals)
    print(orth.round(2).to_string())
    max_pair_corr = orth.where(~np.eye(len(orth)).astype(bool)).abs().max().max()
    print(f"\n  Max non-diagonal |corr|: {max_pair_corr:.2f} "
          f"(< 0.70 = good, > 0.70 = redundant)")

    # --- Per-signal solo backtest (attribution) ---
    print("\n" + "=" * 74)
    print("  PER-SIGNAL SOLO BACKTEST (top decile, monthly, SPY filter, 5bps)")
    print("=" * 74)
    spy_filter = spy_trend_filter(spy, ma_period=200)
    tom = turn_of_month_boost(prices.index)
    overlay = spy_filter.reindex(prices.index).ffill() * tom.reindex(prices.index).ffill()

    solo_results = []
    for name, ranks in signals.items():
        w = build_weights_from_rank(ranks, TOP_DECILE, REBALANCE_DAYS, overlay)
        _, stats = run_backtest(w, prices, name)
        solo_results.append(stats)
        print(
            f"  {name:<22} CAGR {stats['cagr']:+7.1%}  "
            f"Sharpe {stats['sharpe']:>5.2f}  "
            f"MaxDD {stats['maxdd']:+7.1%}  Calmar {stats['calmar']:>5.2f}"
        )

    # --- Ensemble backtest ---
    print("\n" + "=" * 74)
    print("  ENSEMBLE BACKTEST (equal-weight rank composite, top decile)")
    print("=" * 74)
    composite = combine_ranks(signals)
    w_ens = build_weights_from_rank(composite, TOP_DECILE, REBALANCE_DAYS, overlay)
    ens_net, ens_full = run_backtest(w_ens, prices, "ensemble_full")

    is_stats = stats_over_window(ens_net, "2010-01-01", IS_END, "IS 2010-2022")
    oos_stats = stats_over_window(ens_net, OOS_START, OOS_END, "OOS 2023-2026")

    for s in [ens_full, is_stats, oos_stats]:
        print(
            f"  {s['label']:<22} CAGR {s['cagr']:+7.1%}  "
            f"Sharpe {s['sharpe']:>5.2f}  "
            f"MaxDD {s['maxdd']:+7.1%}  Calmar {s['calmar']:>5.2f}  "
            f"({s['bars']} bars)"
        )

    # --- Ensemble without overlays (diagnostic: is the overlay helping?) ---
    print("\n  ENSEMBLE without overlays (pure signal, no SPY filter / TOM)")
    w_raw = build_weights_from_rank(composite, TOP_DECILE, REBALANCE_DAYS, None)
    raw_net, raw_full = run_backtest(w_raw, prices, "ensemble_no_overlay")
    is_raw = stats_over_window(raw_net, "2010-01-01", IS_END, "IS no-overlay")
    oos_raw = stats_over_window(raw_net, OOS_START, OOS_END, "OOS no-overlay")
    for s in [raw_full, is_raw, oos_raw]:
        print(
            f"  {s['label']:<22} CAGR {s['cagr']:+7.1%}  "
            f"Sharpe {s['sharpe']:>5.2f}  "
            f"MaxDD {s['maxdd']:+7.1%}  Calmar {s['calmar']:>5.2f}"
        )

    # --- Gate check ---
    bar = "=" * 74
    print(f"\n{bar}")
    print("  GATE CHECK (CAGR-first framework)")
    print(bar)

    oos_cagr_ok = oos_stats["cagr"] >= GATE_CAGR
    oos_calmar_ok = oos_stats["calmar"] >= GATE_CALMAR
    ratio = (
        oos_stats["cagr"] / is_stats["cagr"]
        if is_stats["cagr"] > 1e-6 else 0.0
    )
    ratio_ok = ratio >= GATE_OOS_IS_RATIO

    print(f"  OOS CAGR       {oos_stats['cagr']:+.1%}  "
          f"(gate ≥ {GATE_CAGR:.0%})   {'PASS' if oos_cagr_ok else 'FAIL'}")
    print(f"  OOS Calmar     {oos_stats['calmar']:.2f}  "
          f"(gate ≥ {GATE_CALMAR:.2f})  {'PASS' if oos_calmar_ok else 'FAIL'}")
    print(f"  OOS/IS CAGR    {ratio:.0%}  "
          f"(gate ≥ {GATE_OOS_IS_RATIO:.0%})  "
          f"{'PASS' if ratio_ok else 'FAIL'}")
    print()
    n_pass = sum([oos_cagr_ok, oos_calmar_ok, ratio_ok])
    if n_pass == 3:
        print("  VERDICT: FULL PASS → proceed to 6-test validation + expand to 8-10 signals")
    elif n_pass == 2:
        print("  VERDICT: 2/3 PASS → conditional GO; investigate failed gate; worth a second round")
    elif n_pass == 1:
        print("  VERDICT: 1/3 PASS → GREY ZONE; parameter exploration before committing or killing")
    else:
        print("  VERDICT: KILL — ensemble null, document in HUNT_APR2026.md")
    print(bar)

    # Yearly breakdown for context
    print("\n  YEARLY TOTAL RETURN (ensemble net, for regime visibility)")
    yearly = ens_net.groupby(ens_net.index.year).apply(lambda s: (1 + s).prod() - 1)
    for year, r in yearly.items():
        print(f"    {year}     {r:+7.1%}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
