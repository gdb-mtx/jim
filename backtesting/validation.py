"""
Statistical Validation Framework — The overfitting defense system.

This is the most critical module in the project. No strategy goes to paper
trading without passing these tests. See PLAN.md Section 4.

Validation checklist (all must pass):
  - Walk-forward analysis: median Sharpe > 0.5 across rolling OOS windows
  - Monte Carlo simulation with >70% of runs profitable
  - Acceptable returns (> -2% annualized) in at least 3 of 4 market regimes
  - Walk-forward windows include warmup data for momentum signal computation
"""

import numpy as np
import pandas as pd
from backtesting.metrics import sharpe_ratio, annualized_return, max_drawdown, full_report


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
