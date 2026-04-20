"""
Statistical Validation Framework — The overfitting defense system.

This is the most critical module in the project. No strategy goes to paper
trading without passing these tests. See PLAN.md Section 4.

Two walk-forward flavors:
  - `walk_forward_analysis` (legacy): rolling OOS evaluation with FIXED
    parameters. Measures per-window performance but does not refit params.
    Useful for detecting regime-driven failure of a fixed-default strategy.
  - `walk_forward_refit_analysis`: per-window parameter selection. At each
    window, sweep a parameter grid on the TRAIN slice, pick the best-scoring
    config, evaluate that config on the TEST slice. This is the "walk-forward
    optimization" sense — no design-time leakage at any evaluation point.
    Also reports per-window picked params for stability analysis.
"""

import itertools
import numpy as np
import pandas as pd
from backtesting.metrics import sharpe_ratio, annualized_return, max_drawdown, calmar_ratio, full_report


def walk_forward_analysis(
    prices: pd.DataFrame,
    strategy_fn,
    train_size: int = 504,  # ~2 years of trading days
    test_size: int = 252,   # ~1 year (longer for reliable Sharpe)
    step_size: int = 126,   # ~6 months (roll forward)
    warmup: int = 252,      # Lookback warmup included before test window
) -> list[dict]:
    """Walk-forward analysis — the primary defense against overfitting.

    Splits data into rolling train/test windows. The strategy is run on
    warmup+test data, but only the test period returns are evaluated.
    This ensures momentum strategies have enough history to generate signals.

    Args:
        prices: DataFrame of asset prices
        strategy_fn: Callable(prices) -> pd.Series of strategy returns.
                     The function receives a price DataFrame and returns
                     a Series of daily returns.
        train_size: Number of trading days in training window
        test_size: Number of trading days in test window
        step_size: Number of days to roll forward each iteration
        warmup: Days of data before test window for strategy warmup

    Returns:
        List of dicts with results for each out-of-sample window
    """
    results = []
    total_days = len(prices)
    start = 0

    while start + train_size + test_size <= total_days:
        train_end = start + train_size
        test_end = train_end + test_size

        # Include warmup data before test window so strategy can compute signals
        warmup_start = max(0, train_end - warmup)
        combined_prices = prices.iloc[warmup_start:test_end]

        # Run strategy on warmup+test, then slice to test-only returns
        all_returns = strategy_fn(combined_prices)
        test_start_date = prices.index[train_end]
        test_returns = all_returns.loc[test_start_date:]

        if len(test_returns) < 20:
            start += step_size
            continue

        window_result = {
            "window": len(results) + 1,
            "train_start": prices.index[start],
            "train_end": prices.index[train_end - 1],
            "test_start": prices.index[train_end],
            "test_end": prices.index[min(test_end - 1, total_days - 1)],
            "test_return": annualized_return(test_returns),
            "test_sharpe": sharpe_ratio(test_returns),
            "test_max_dd": max_drawdown(test_returns),
            "test_periods": len(test_returns),
        }
        results.append(window_result)
        start += step_size

    return results


def walk_forward_summary(results: list[dict]) -> dict:
    """Summarize walk-forward results.

    Args:
        results: Output from walk_forward_analysis

    Returns:
        Summary dict with pass/fail assessment
    """
    if not results:
        return {"pass": False, "reason": "No walk-forward windows generated"}

    sharpes = [r["test_sharpe"] for r in results]
    returns = [r["test_return"] for r in results]
    profitable_windows = sum(1 for r in returns if r > 0)

    summary = {
        "n_windows": len(results),
        "mean_sharpe": np.mean(sharpes),
        "median_sharpe": np.median(sharpes),
        "min_sharpe": min(sharpes),
        "max_sharpe": max(sharpes),
        "profitable_windows": profitable_windows,
        "profitable_pct": profitable_windows / len(results),
        "mean_return": np.mean(returns),
        "pass": np.median(sharpes) > 0.5 and profitable_windows >= 3,
        "reason": "",
    }

    if np.median(sharpes) <= 0.5:
        summary["reason"] = f"Median Sharpe {np.median(sharpes):.2f} <= 0.5"
    elif profitable_windows < 3:
        summary["reason"] = f"Only {profitable_windows} profitable windows (need 3+)"
    else:
        summary["reason"] = "All checks passed"

    return summary


def walk_forward_refit_analysis(
    prices: pd.DataFrame,
    strategy_fn_factory,
    param_grid: dict,
    train_size: int = 756,   # ~3 years
    test_size: int = 252,    # ~1 year
    step_size: int = 126,    # ~6 months
    warmup: int = 252,       # warmup days included before train slice
    objective: str = "calmar",
    periods_per_year: int = 252,
) -> list[dict]:
    """Walk-forward parameter refit — true OOS parameter selection.

    At each window:
      1. Slice into warmup + train + test.
      2. For each config in `param_grid`, build the strategy and run it on
         warmup+train only. Score it by `objective` on the train returns.
      3. Pick the best-scoring config.
      4. Run that config on warmup+train+test and report metrics on the
         test-only returns.

    No future data leaks into parameter selection at any window. Picked
    params per window are reported so stability can be assessed.

    Args:
        prices: DataFrame of asset prices.
        strategy_fn_factory: Callable(**params) -> Callable(prices) -> returns.
            The factory takes parameter kwargs and returns a runner function
            that mirrors the signature used by `walk_forward_analysis`.
        param_grid: Dict mapping parameter name -> list of values to try.
            Cartesian product is swept.
        train_size: Trading days in train slice (parameter selection).
        test_size: Trading days in test slice (OOS evaluation).
        step_size: Days to roll forward between windows.
        warmup: Days of data before train slice for signal warmup.
        objective: Scoring metric for train-slice selection.
            One of "calmar", "sharpe", "cagr".
        periods_per_year: For CAGR/Sharpe annualization.

    Returns:
        List of dicts per window, including picked params + test metrics.
    """
    keys = list(param_grid.keys())
    configs = [
        dict(zip(keys, combo))
        for combo in itertools.product(*[param_grid[k] for k in keys])
    ]
    if not configs:
        return []

    def _score(returns: pd.Series) -> float:
        if len(returns) < 20 or returns.isna().all():
            return -np.inf
        r = returns.dropna()
        if objective == "sharpe":
            return float(sharpe_ratio(r, periods_per_year=periods_per_year))
        if objective == "cagr":
            return float(annualized_return(r, periods_per_year=periods_per_year))
        # default: calmar
        dd = max_drawdown(r)
        if abs(dd) < 1e-9:
            return -np.inf
        return float(annualized_return(r, periods_per_year=periods_per_year) / abs(dd))

    results = []
    total_days = len(prices)
    start = 0

    while start + train_size + test_size <= total_days:
        train_end = start + train_size
        test_end = train_end + test_size

        warmup_start = max(0, start - warmup)
        # Strategy sees warmup+train for param selection; NO test data visible.
        train_slice = prices.iloc[warmup_start:train_end]
        # Full slice for final test evaluation (warmup+train+test).
        full_slice = prices.iloc[warmup_start:test_end]
        train_start_date = prices.index[start]
        test_start_date = prices.index[train_end]
        test_end_date = prices.index[min(test_end - 1, total_days - 1)]

        # 1) Score every config on the train slice only
        best_cfg = None
        best_score = -np.inf
        all_train_scores = []
        for cfg in configs:
            runner = strategy_fn_factory(**cfg)
            train_returns = runner(train_slice)
            train_returns = train_returns.loc[train_start_date:]
            score = _score(train_returns)
            all_train_scores.append((cfg, score))
            if score > best_score:
                best_score = score
                best_cfg = cfg

        # 2) Evaluate the winning config on the test slice
        runner = strategy_fn_factory(**best_cfg)
        all_returns = runner(full_slice)
        test_returns = all_returns.loc[test_start_date:test_end_date]

        if len(test_returns) < 20:
            start += step_size
            continue

        test_returns = test_returns.dropna()
        window_result = {
            "window": len(results) + 1,
            "train_start": prices.index[start],
            "train_end": prices.index[train_end - 1],
            "test_start": test_start_date,
            "test_end": test_end_date,
            "picked_params": best_cfg,
            "train_score": float(best_score),
            "train_objective": objective,
            "test_cagr": float(annualized_return(test_returns, periods_per_year=periods_per_year)),
            "test_maxdd": float(max_drawdown(test_returns)),
            "test_calmar": float(calmar_ratio(test_returns, periods_per_year=periods_per_year)),
            "test_sharpe": float(sharpe_ratio(test_returns, periods_per_year=periods_per_year)),
            "test_periods": len(test_returns),
            "n_configs_tried": len(configs),
        }
        results.append(window_result)
        start += step_size

    return results


def walk_forward_refit_summary(results: list[dict]) -> dict:
    """Summarize walk-forward-refit results: stability + OOS aggregate."""
    if not results:
        return {"n_windows": 0, "reason": "No windows"}

    # Parameter stability: how often is each picked config chosen?
    from collections import Counter
    picks = [tuple(sorted(r["picked_params"].items())) for r in results]
    counter = Counter(picks)
    most_common_pick, most_common_count = counter.most_common(1)[0]
    stability_pct = most_common_count / len(results)

    cagrs = [r["test_cagr"] for r in results]
    calmars = [r["test_calmar"] for r in results if np.isfinite(r["test_calmar"])]
    sharpes = [r["test_sharpe"] for r in results]
    profitable = sum(1 for c in cagrs if c > 0)

    return {
        "n_windows": len(results),
        "median_cagr": float(np.median(cagrs)),
        "mean_cagr": float(np.mean(cagrs)),
        "median_calmar": float(np.median(calmars)) if calmars else 0.0,
        "median_sharpe": float(np.median(sharpes)),
        "profitable_windows": profitable,
        "profitable_pct": profitable / len(results),
        "most_common_pick": dict(most_common_pick),
        "most_common_pick_count": most_common_count,
        "stability_pct": stability_pct,
        "unique_picks": len(counter),
        "n_configs_tried": results[0]["n_configs_tried"],
    }


def monte_carlo_simulation(
    returns: pd.Series,
    n_simulations: int = 1000,
    seed: int = 42,
) -> dict:
    """Monte Carlo simulation — test strategy robustness by randomizing trade order.

    If a strategy only works with trades in a specific order, it's fragile.
    Robust strategies are profitable regardless of trade sequence.

    Args:
        returns: Series of trade/period returns
        n_simulations: Number of random permutations
        seed: Random seed for reproducibility

    Returns:
        Dict with simulation results and pass/fail
    """
    rng = np.random.default_rng(seed)
    returns_arr = returns.values.copy()

    final_values = []
    sharpes = []

    for _ in range(n_simulations):
        shuffled = rng.permutation(returns_arr)
        cumulative = np.prod(1 + shuffled)
        final_values.append(cumulative)

        shuffled_series = pd.Series(shuffled)
        sharpes.append(sharpe_ratio(shuffled_series))

    final_values = np.array(final_values)
    sharpes = np.array(sharpes)
    profitable_runs = (final_values > 1.0).sum()

    result = {
        "n_simulations": n_simulations,
        "profitable_runs": int(profitable_runs),
        "profitable_pct": profitable_runs / n_simulations,
        "mean_final_value": float(np.mean(final_values)),
        "median_final_value": float(np.median(final_values)),
        "p5_final_value": float(np.percentile(final_values, 5)),
        "p95_final_value": float(np.percentile(final_values, 95)),
        "mean_sharpe": float(np.mean(sharpes)),
        "pass": profitable_runs / n_simulations > 0.70,
        "reason": "",
    }

    if result["pass"]:
        result["reason"] = f"{result['profitable_pct']:.0%} of runs profitable (>70% required)"
    else:
        result["reason"] = f"Only {result['profitable_pct']:.0%} of runs profitable (<70%)"

    return result


# Market regime date ranges for regime testing
MARKET_REGIMES = {
    "2008_crisis": ("2007-10-01", "2009-03-31"),
    "2020_covid": ("2020-01-01", "2020-06-30"),
    "2022_bear": ("2022-01-01", "2022-12-31"),
    "2024_2025_bull": ("2024-01-01", "2025-12-31"),
}


def regime_test(
    prices: pd.DataFrame,
    strategy_fn,
    regimes: dict[str, tuple[str, str]] | None = None,
    warmup_days: int = 252,
) -> dict:
    """Test strategy across distinct market regimes.

    A strategy that only works in bull markets is not a strategy — it's
    a bet on direction. Includes warmup data before each regime so
    momentum strategies can compute signals from day one.

    A regime is considered "not harmful" if the strategy doesn't lose more
    than -2% annualized (going to cash during a crash = acceptable).

    Args:
        prices: Full price DataFrame
        strategy_fn: Callable(prices) -> pd.Series of returns
        regimes: Dict of regime_name -> (start_date, end_date)
        warmup_days: Days of prior data to include for strategy warmup

    Returns:
        Dict with per-regime results and overall pass/fail
    """
    if regimes is None:
        regimes = MARKET_REGIMES

    results = {}
    pass_count = 0

    for name, (start, end) in regimes.items():
        regime_prices = prices.loc[start:end]
        if len(regime_prices) < 20:
            results[name] = {"skip": True, "reason": "Insufficient data"}
            continue

        # Include warmup data before regime start for strategy signals
        start_idx = prices.index.searchsorted(pd.Timestamp(start))
        warmup_start = max(0, start_idx - warmup_days)
        combined_prices = prices.iloc[warmup_start:].loc[:end]

        all_returns = strategy_fn(combined_prices)
        regime_returns = all_returns.loc[start:end]

        if len(regime_returns) < 10:
            results[name] = {"skip": True, "reason": "Insufficient returns after warmup"}
            continue

        ann_ret = annualized_return(regime_returns)

        # A return >= -2% is acceptable (going to cash in a crash is fine)
        regime_pass = ann_ret >= -0.02

        results[name] = {
            "annualized_return": ann_ret,
            "sharpe": sharpe_ratio(regime_returns),
            "max_drawdown": max_drawdown(regime_returns),
            "profitable": ann_ret > 0,
            "pass": regime_pass,
        }

        if regime_pass:
            pass_count += 1

    tested_regimes = sum(1 for r in results.values() if not r.get("skip"))

    return {
        "regimes": results,
        "profitable_count": sum(1 for r in results.values() if r.get("profitable")),
        "pass_count": pass_count,
        "tested_count": tested_regimes,
        "pass": pass_count >= 3,
        "reason": f"Acceptable in {pass_count}/{tested_regimes} regimes (need 3+)",
    }


def full_validation(
    prices: pd.DataFrame,
    strategy_fn,
    strategy_name: str = "Strategy",
) -> dict:
    """Run the complete validation suite.

    This is the gatekeeper. A strategy must pass ALL checks before
    it goes to paper trading.

    Args:
        prices: Full price DataFrame
        strategy_fn: Callable(prices) -> pd.Series of returns
        strategy_name: Name for reporting

    Returns:
        Complete validation report with overall pass/fail
    """
    print(f"\n{'='*60}")
    print(f"  VALIDATION: {strategy_name}")
    print(f"{'='*60}")

    # 1. Walk-forward analysis
    print("\n[1/3] Walk-Forward Analysis...")
    wf_results = walk_forward_analysis(prices, strategy_fn)
    wf_summary = walk_forward_summary(wf_results)
    status = "PASS" if wf_summary["pass"] else "FAIL"
    print(f"  {status}: {wf_summary['reason']}")
    print(f"  Windows: {wf_summary['n_windows']}, Median Sharpe: {wf_summary['median_sharpe']:.2f}")

    # 2. Monte Carlo simulation
    print("\n[2/3] Monte Carlo Simulation (1,000 runs)...")
    all_returns = strategy_fn(prices)
    mc_result = monte_carlo_simulation(all_returns)
    status = "PASS" if mc_result["pass"] else "FAIL"
    print(f"  {status}: {mc_result['reason']}")

    # 3. Regime testing
    print("\n[3/3] Market Regime Testing...")
    regime_result = regime_test(prices, strategy_fn)
    status = "PASS" if regime_result["pass"] else "FAIL"
    print(f"  {status}: {regime_result['reason']}")
    for name, data in regime_result["regimes"].items():
        if data.get("skip"):
            print(f"    {name}: SKIPPED ({data['reason']})")
        else:
            marker = "+" if data.get("pass") else "-"
            print(f"    {marker} {name}: {data['annualized_return']:.2%} (Sharpe: {data['sharpe']:.2f})")

    # Overall
    overall_pass = wf_summary["pass"] and mc_result["pass"] and regime_result["pass"]
    print(f"\n{'='*60}")
    print(f"  OVERALL: {'PASS — Ready for paper trading' if overall_pass else 'FAIL — Needs more work'}")
    print(f"{'='*60}\n")

    return {
        "strategy": strategy_name,
        "walk_forward": wf_summary,
        "monte_carlo": mc_result,
        "regime_test": regime_result,
        "overall_pass": overall_pass,
    }
