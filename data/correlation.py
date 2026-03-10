"""Inter-account correlation monitoring.

Computes pairwise Pearson correlation between daily returns of all accounts.
Backtest expects 0.56-0.66 for equity accounts; crypto correlation ~0.12-0.18.
Alert threshold at 0.80 signals degrading diversification.
"""

import pandas as pd

from data.snapshots import get_all_daily_returns

# Backtest expected correlations (from PLAN.md / combined portfolio analysis)
BACKTEST_EXPECTED = {
    "acct_1_acct_2": 0.56,
    "acct_1_acct_3": 0.62,
    "acct_2_acct_3": 0.66,
    "acct_1_acct_4": 0.18,
    "acct_2_acct_4": 0.15,
    "acct_3_acct_4": 0.12,
}

ACCOUNT_PAIRS = [
    ("acct_1", "acct_2"), ("acct_1", "acct_3"), ("acct_2", "acct_3"),
    ("acct_1", "acct_4"), ("acct_2", "acct_4"), ("acct_3", "acct_4"),
]


def _pair_key(a: str, b: str) -> str:
    return f"{a}_{b}"


def compute_correlation_matrix(min_days: int = 20) -> dict[str, float] | None:
    """Compute pairwise Pearson correlation from daily returns.

    Returns None if fewer than min_days of aligned data.
    """
    returns = get_all_daily_returns()
    if returns.empty or len(returns) < min_days:
        return None

    corr = returns.corr()
    result = {}
    for a, b in ACCOUNT_PAIRS:
        if a in corr.columns and b in corr.columns:
            result[_pair_key(a, b)] = round(float(corr.loc[a, b]), 4)
    return result


def compute_rolling_correlation(window: int = 21) -> dict[str, list[dict]]:
    """Compute rolling pairwise correlation over a sliding window.

    Returns dict of pair_key -> [{time, value}, ...] for charting.
    """
    returns = get_all_daily_returns()
    if returns.empty or len(returns) < window:
        return {_pair_key(a, b): [] for a, b in ACCOUNT_PAIRS}

    result = {}
    for a, b in ACCOUNT_PAIRS:
        if a not in returns.columns or b not in returns.columns:
            result[_pair_key(a, b)] = []
            continue

        rolling = returns[a].rolling(window).corr(returns[b]).dropna()
        result[_pair_key(a, b)] = [
            {"time": idx.strftime("%Y-%m-%d"), "value": round(float(val), 4)}
            for idx, val in rolling.items()
        ]
    return result


def get_correlation_report(alert_threshold: float = 0.80) -> dict:
    """Full correlation report for the dashboard.

    Returns matrix, rolling series, alerts, confidence level, and backtest comparison.
    """
    returns = get_all_daily_returns()
    data_days = len(returns) if not returns.empty else 0

    matrix = compute_correlation_matrix()
    rolling = compute_rolling_correlation()

    # Determine confidence level
    if data_days < 20:
        confidence = None
    elif data_days < 30:
        confidence = "low"
    elif data_days < 60:
        confidence = "medium"
    else:
        confidence = "high"

    # Check for alert conditions
    alert_pairs = []
    if matrix:
        for pair, value in matrix.items():
            if value >= alert_threshold:
                alert_pairs.append(pair)

    return {
        "matrix": matrix,
        "rolling": rolling,
        "alert_pairs": alert_pairs,
        "data_days": data_days,
        "confidence": confidence,
        "alert_threshold": alert_threshold,
        "backtest_expected": BACKTEST_EXPECTED,
    }
