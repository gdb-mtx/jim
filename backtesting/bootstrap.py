"""
Block Bootstrap — Monte Carlo confidence intervals on strategy returns.

VALIDATION.md Test 4: resample 20-day blocks with replacement to
preserve short-horizon autocorrelation, then compute Sharpe / MaxDD on
each resample. The distribution gives a confidence interval on the
claimed headline number.

Why blocks, not single-day: daily returns are autocorrelated (momentum,
vol clustering). Shuffling individual days destroys that structure and
overstates confidence. 20-day blocks roughly match the strategies'
rebalance horizons and preserve the realistic dependency length.
"""

import numpy as np
import pandas as pd

from backtesting.metrics import sharpe_ratio, max_drawdown


def block_bootstrap(
    returns: pd.Series,
    block_size: int = 20,
    n_simulations: int = 1000,
    periods_per_year: int = 252,
    seed: int = 42,
) -> dict:
    """Block bootstrap for Sharpe / MaxDD confidence intervals.

    Args:
        returns: Strategy daily returns.
        block_size: Length of each resampled block (days).
        n_simulations: Number of bootstrap iterations.
        periods_per_year: 252 for equity, 365 for crypto.
        seed: RNG seed for reproducibility.

    Returns:
        Dict with percentile Sharpes, MaxDDs, and pass/fail against the
        5th-percentile threshold from VALIDATION.md (Sharpe > 0.3).
    """
    rng = np.random.default_rng(seed)
    arr = returns.dropna().values
    n = len(arr)

    if n < block_size * 2:
        return {
            "pass": False,
            "reason": f"Insufficient data ({n} days) for {block_size}-day blocks",
        }

    n_blocks_per_sim = n // block_size

    sharpes = np.empty(n_simulations)
    maxdds = np.empty(n_simulations)
    finals = np.empty(n_simulations)

    for i in range(n_simulations):
        start_idx = rng.integers(0, n - block_size + 1, size=n_blocks_per_sim)
        sample = np.concatenate([arr[s : s + block_size] for s in start_idx])
        sample_s = pd.Series(sample)

        sharpes[i] = sharpe_ratio(sample_s, periods_per_year=periods_per_year)
        maxdds[i] = max_drawdown(sample_s)
        finals[i] = float(np.prod(1 + sample))

    sharpe_p5 = float(np.percentile(sharpes, 5))
    sharpe_p50 = float(np.percentile(sharpes, 50))
    sharpe_p95 = float(np.percentile(sharpes, 95))
    maxdd_p5 = float(np.percentile(maxdds, 5))
    maxdd_p95 = float(np.percentile(maxdds, 95))
    positive_sharpe_pct = float((sharpes > 0.5).mean())
    profitable_pct = float((finals > 1.0).mean())

    passes = sharpe_p5 >= 0.3

    return {
        "n_simulations": n_simulations,
        "block_size": block_size,
        "sharpe_p5": sharpe_p5,
        "sharpe_p50": sharpe_p50,
        "sharpe_p95": sharpe_p95,
        "maxdd_p5": maxdd_p5,
        "maxdd_p95": maxdd_p95,
        "sharpe_above_0.5_pct": positive_sharpe_pct,
        "profitable_pct": profitable_pct,
        "pass": passes,
        "reason": (
            f"5th-pct Sharpe {sharpe_p5:.2f} {'>=' if passes else '<'} 0.3 threshold"
        ),
    }
