"""Walk-forward REFIT analysis for Account 1 (Stock Momentum + SPY Filter).

At each rolling window:
  1. Sweep a parameter grid on the TRAIN slice only (no test-data peek).
  2. Pick the best config by train-slice Calmar.
  3. Evaluate that config on the TEST slice, record metrics + picked params.

Reports:
  - Per-window table: picked params, test CAGR/Calmar.
  - Param stability: how often each config is picked.
  - Aggregate OOS metrics vs the fixed-default baseline.

Usage:  uv run python3 scripts/walk_forward_refit_a1.py [--grid small|medium|large]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.validation import (  # noqa: E402
    walk_forward_refit_analysis,
    walk_forward_refit_summary,
    walk_forward_analysis,
    walk_forward_summary,
)
from data.sp500 import download_sp500_prices, download_vix  # noqa: E402
from strategies.stock_momentum import StockMomentum  # noqa: E402
from strategies.portfolio import compute_spy_trend_filter  # noqa: E402


GRIDS = {
    "small": {
        "lookback_days": [126, 189, 252],
        "top_n": [10, 15, 20],
    },
    "medium": {
        "lookback_days": [126, 168, 189, 210, 252],
        "skip_recent": [10, 21, 42],
        "top_n": [10, 15, 20, 25],
    },
    "large": {
        "lookback_days": [63, 126, 168, 189, 210, 252, 315],
        "skip_recent": [5, 10, 21, 42],
        "top_n": [10, 15, 20, 25, 30],
        "vol_target": [0.15, 0.20, 0.25],
    },
}


def make_strategy_runner_factory(vix, spy_scalar):
    """Returns factory(**params) -> runner(prices) -> returns."""
    def factory(**params):
        def runner(slice_prices):
            s = StockMomentum(**params)
            s.set_vix(vix)
            raw = s.generate_returns(slice_prices)
            spy_aligned = spy_scalar.reindex(raw.index).ffill().fillna(1.0)
            return raw * spy_aligned
        return runner
    return factory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", choices=GRIDS.keys(), default="small")
    parser.add_argument("--train-years", type=int, default=3)
    parser.add_argument("--test-years", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=6)
    args = parser.parse_args()

    print(f"Loading A1 inputs...")
    prices = download_sp500_prices(start="2010-01-01")
    vix = download_vix()
    spy_scalar = compute_spy_trend_filter(start="2008-01-01", ma_period=200, reduction=0.5)
    factory = make_strategy_runner_factory(vix, spy_scalar)

    grid = GRIDS[args.grid]
    n_configs = 1
    for v in grid.values():
        n_configs *= len(v)
    print(f"Grid '{args.grid}': {n_configs} configs across {list(grid.keys())}")
    print(f"Universe: {prices.shape[1]} tickers × {prices.shape[0]} days")

    PPY = 252
    train_size = args.train_years * PPY
    test_size = args.test_years * PPY
    step_size = int(args.step_months * PPY / 12)

    # ── Run the refit analysis ─────────────────────────────────────
    t0 = time.time()
    print(f"\n[1/2] Running walk-forward REFIT ({n_configs} configs × windows)...")
    refit_results = walk_forward_refit_analysis(
        prices,
        strategy_fn_factory=factory,
        param_grid=grid,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        warmup=252,
        objective="calmar",
        periods_per_year=PPY,
    )
    t_refit = time.time() - t0
    print(f"  done in {t_refit:.1f}s — {len(refit_results)} windows")

    refit_summary = walk_forward_refit_summary(refit_results)

    # ── Fixed-default baseline for side-by-side comparison ────────
    print(f"\n[2/2] Running fixed-default baseline on same windows...")
    t0 = time.time()
    default_runner = factory()  # all defaults
    default_results = walk_forward_analysis(
        prices,
        strategy_fn=default_runner,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        warmup=252,
    )
    t_default = time.time() - t0
    print(f"  done in {t_default:.1f}s — {len(default_results)} windows")

    # ── Build comparable default summary ───────────────────────────
    import numpy as np
    default_cagrs = [r["test_return"] for r in default_results]
    default_sharpes = [r["test_sharpe"] for r in default_results]
    default_mdds = [r["test_max_dd"] for r in default_results]
    default_calmars = [c / abs(d) if abs(d) > 1e-6 else 0.0 for c, d in zip(default_cagrs, default_mdds)]

    # ── Per-window side-by-side table ──────────────────────────────
    print(f"\n{'=' * 110}")
    print(f"  PER-WINDOW: refit vs fixed-default  (A1, grid={args.grid})")
    print(f"{'=' * 110}")
    header = f"{'#':>3}  {'test window':<24}  {'picked params':<40}  {'refit CAGR':>10} {'def CAGR':>9}  {'Δ':>7}"
    print(header)
    print("-" * 110)
    for r, d in zip(refit_results, default_results):
        w = r["window"]
        win = f"{r['test_start'].date()} → {r['test_end'].date()}"
        picked = ", ".join(f"{k}={v}" for k, v in r["picked_params"].items())
        delta = r["test_cagr"] - d["test_return"]
        print(f"{w:>3}  {win:<24}  {picked:<40}  {r['test_cagr']*100:>+9.1f}% {d['test_return']*100:>+8.1f}%  {delta*100:>+6.1f}")

    # ── Aggregates ─────────────────────────────────────────────────
    print(f"\n{'=' * 110}")
    print(f"  AGGREGATE (OOS test windows only, equal-weighted across windows)")
    print(f"{'=' * 110}")
    def median(x): return float(np.median(x)) if len(x) else 0.0
    def mean(x):   return float(np.mean(x))   if len(x) else 0.0
    print(f"  Walk-forward REFIT      ({len(refit_results)} windows):")
    print(f"    median CAGR {refit_summary['median_cagr']*100:+.1f}%   mean CAGR {refit_summary['mean_cagr']*100:+.1f}%   median Calmar {refit_summary['median_calmar']:.2f}   median Sharpe {refit_summary['median_sharpe']:.2f}")
    print(f"    profitable {refit_summary['profitable_windows']}/{refit_summary['n_windows']}   unique picks {refit_summary['unique_picks']}/{refit_summary['n_configs_tried']}")
    print(f"  Fixed-default baseline  ({len(default_results)} windows):")
    print(f"    median CAGR {median(default_cagrs)*100:+.1f}%   mean CAGR {mean(default_cagrs)*100:+.1f}%   median Calmar {median(default_calmars):.2f}   median Sharpe {median(default_sharpes):.2f}")
    prof_def = sum(1 for c in default_cagrs if c > 0)
    print(f"    profitable {prof_def}/{len(default_results)}")

    # ── Param stability ────────────────────────────────────────────
    print(f"\n{'=' * 110}")
    print(f"  PARAMETER STABILITY  (how often each config was picked)")
    print(f"{'=' * 110}")
    picks = [tuple(sorted(r["picked_params"].items())) for r in refit_results]
    counter = Counter(picks)
    for cfg, count in counter.most_common():
        cfg_str = ", ".join(f"{k}={v}" for k, v in cfg)
        pct = count / len(refit_results) * 100
        bar = "█" * int(pct / 3)
        print(f"  {cfg_str:<50}  {count:>2}/{len(refit_results)}  ({pct:>4.0f}%)  {bar}")

    default_params = "lookback_days=189, skip_recent=21, top_n=15, vol_target=0.20"
    print(f"\n  Current defaults: {default_params}")
    print(f"  Most-picked:      {', '.join(f'{k}={v}' for k, v in refit_summary['most_common_pick'].items())}  ({refit_summary['stability_pct']*100:.0f}% of windows)")


if __name__ == "__main__":
    main()
