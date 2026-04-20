"""Walk-forward REFIT for Account 2's Low-Volatility leg (70% of A2).

Same methodology as walk_forward_refit_a1.py — per-window grid search on
train slice, picked config evaluated OOS on test slice. Sweeps over the
LowVolatility parameters against the S&P 500 universe.

A2's other leg (30% MultiAssetTrend on 5 ETFs) is not searched here —
different universe, smaller parameter surface, separate exercise if needed.

Usage:  uv run python3 scripts/walk_forward_refit_a2.py [--grid small|medium]
"""
from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtesting.validation import (  # noqa: E402
    walk_forward_refit_analysis,
    walk_forward_refit_summary,
    walk_forward_analysis,
)
from data.sp500 import download_sp500_prices, download_vix  # noqa: E402
from strategies.low_volatility import LowVolatility  # noqa: E402
from strategies.portfolio import compute_spy_trend_filter  # noqa: E402


GRIDS = {
    "small": {
        "vol_lookback_days": [42, 63, 84],
        "momentum_lookback_days": [126, 189, 252],
        "top_n": [20, 30, 40],
    },
    "medium": {
        "vol_lookback_days": [21, 42, 63, 84, 126],
        "momentum_lookback_days": [126, 168, 189, 210, 252],
        "top_n": [15, 20, 25, 30, 35, 40],
    },
}


def make_factory(vix, spy_scalar):
    def factory(**params):
        def runner(slice_prices):
            s = LowVolatility(**params)
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

    print("Loading A2/LowVolatility inputs...")
    prices = download_sp500_prices(start="2010-01-01")
    vix = download_vix()
    spy_scalar = compute_spy_trend_filter(start="2008-01-01", ma_period=200, reduction=0.5)
    factory = make_factory(vix, spy_scalar)

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

    t0 = time.time()
    print(f"\n[1/2] Walk-forward REFIT ({n_configs} configs × windows)...")
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
    print(f"  done in {time.time()-t0:.1f}s — {len(refit_results)} windows")
    refit_summary = walk_forward_refit_summary(refit_results)

    print(f"\n[2/2] Fixed-default baseline...")
    t0 = time.time()
    default_runner = factory()
    default_results = walk_forward_analysis(
        prices,
        strategy_fn=default_runner,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        warmup=252,
    )
    print(f"  done in {time.time()-t0:.1f}s — {len(default_results)} windows")

    # Per-window table
    print(f"\n{'=' * 120}")
    print(f"  PER-WINDOW: refit vs fixed-default  (A2 Low-Vol, grid={args.grid})")
    print(f"{'=' * 120}")
    print(f"{'#':>3}  {'test window':<24}  {'picked params':<55}  {'refit CAGR':>10} {'def CAGR':>9}  {'Δ':>7}")
    print("-" * 120)
    for r, d in zip(refit_results, default_results):
        w = r["window"]
        win = f"{r['test_start'].date()} → {r['test_end'].date()}"
        picked = ", ".join(f"{k}={v}" for k, v in r["picked_params"].items())
        delta = r["test_cagr"] - d["test_return"]
        print(f"{w:>3}  {win:<24}  {picked:<55}  {r['test_cagr']*100:>+9.1f}% {d['test_return']*100:>+8.1f}%  {delta*100:>+6.1f}")

    # Aggregates
    print(f"\n{'=' * 120}")
    print(f"  AGGREGATE (OOS test windows)")
    print(f"{'=' * 120}")
    def_cagrs = [r["test_return"] for r in default_results]
    def_sharpes = [r["test_sharpe"] for r in default_results]
    def_mdds = [r["test_max_dd"] for r in default_results]
    def_calmars = [c / abs(d) if abs(d) > 1e-6 else 0.0 for c, d in zip(def_cagrs, def_mdds)]

    print(f"  Walk-forward REFIT      ({len(refit_results)} windows):")
    print(f"    median CAGR {refit_summary['median_cagr']*100:+.1f}%   mean CAGR {refit_summary['mean_cagr']*100:+.1f}%   median Calmar {refit_summary['median_calmar']:.2f}   median Sharpe {refit_summary['median_sharpe']:.2f}")
    print(f"    profitable {refit_summary['profitable_windows']}/{refit_summary['n_windows']}   unique picks {refit_summary['unique_picks']}/{refit_summary['n_configs_tried']}")
    print(f"  Fixed-default baseline  ({len(default_results)} windows):")
    print(f"    median CAGR {np.median(def_cagrs)*100:+.1f}%   mean CAGR {np.mean(def_cagrs)*100:+.1f}%   median Calmar {np.median(def_calmars):.2f}   median Sharpe {np.median(def_sharpes):.2f}")
    prof = sum(1 for c in def_cagrs if c > 0)
    print(f"    profitable {prof}/{len(default_results)}")

    # Stability
    print(f"\n{'=' * 120}")
    print(f"  PARAMETER STABILITY")
    print(f"{'=' * 120}")
    picks = [tuple(sorted(r["picked_params"].items())) for r in refit_results]
    counter = Counter(picks)
    for cfg, count in counter.most_common(15):
        cfg_str = ", ".join(f"{k}={v}" for k, v in cfg)
        pct = count / len(refit_results) * 100
        bar = "█" * int(pct / 3)
        print(f"  {cfg_str:<65}  {count:>2}/{len(refit_results)}  ({pct:>4.0f}%)  {bar}")
    print(f"\n  Current defaults: vol_lookback_days=63, momentum_lookback_days=252, top_n=30, vol_target=0.15")
    most = refit_summary["most_common_pick"]
    print(f"  Most-picked:      {', '.join(f'{k}={v}' for k, v in most.items())}  ({refit_summary['stability_pct']*100:.0f}% of windows)")


if __name__ == "__main__":
    main()
