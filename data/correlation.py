"""Inter-account correlation monitoring.

Computes pairwise Pearson correlation between daily returns of active accounts.
After A3 retirement the monitored pairs are A1-A2 / A1-A4 / A2-A4.
Alert threshold at 0.80 signals degrading diversification.
"""

from itertools import combinations

import pandas as pd

from data.snapshots import get_all_daily_returns
from execution.alpaca_broker import active_accounts

# Backtest expected correlations (OOS 2023+, confirmed 2026-04-18).
# Retired-account pairs removed; live book is A1+A2+A4.
BACKTEST_EXPECTED = {
    "acct_1_acct_2": 0.38,
    "acct_1_acct_4": 0.18,
    "acct_2_acct_4": 0.15,
}


def _pair_list() -> list[tuple[str, str]]:
    """Pairs of active accounts, e.g. [(acct_1, acct_2), (acct_1, acct_4), ...]."""
    keys = [f"acct_{n}" for n in active_accounts()]
    return list(combinations(keys, 2))


ACCOUNT_PAIRS = _pair_list()


def _pair_key(a: str, b: str) -> str:
    return f"{a}_{b}"


def compute_correlation_matrix(min_days: int = 20) -> dict[str, float] | None:
    """Compute pairwise Pearson correlation from daily returns.

    For each pair, trims both series to start at the later of their two
    "first non-zero return" dates ("effective inception"). Why: A4 in
    particular existed for 30+ days as a cash-mode bootstrap before its
    first live entry on 2026-04-22, and recorded zero returns through
    that period. Computing pair correlation over the full period mixes
    those constant-zero days with live-trading days, dragging the result
    toward zero by mathematical construction (correlation between a
    varying series and a constant series is pulled to zero regardless of
    relationship). The rolling chart implicitly avoids this because
    pandas rolling.corr() returns NaN when one side has zero variance —
    the matrix had no such filter until 2026-05-07.

    Per-pair trimming (rather than trimming the joint frame to the
    latest of all inceptions) preserves more data for pairs that share
    longer histories: A1↔A2 still uses the full ~45-day overlap, while
    A1↔A4 / A2↔A4 use the ~14-day live overlap.

    Returns None if any pair has fewer than min_days of aligned data
    after trimming. Soft gate so a freshly-launched account doesn't
    suppress matrix display for older pairs — but currently we render
    nothing if matrix is empty (frontend gates on matrix presence too).
    """
    returns = get_all_daily_returns()
    if returns.empty:
        return None

    result = {}
    for a, b in ACCOUNT_PAIRS:
        if a not in returns.columns or b not in returns.columns:
            continue
        sa = returns[a]
        sb = returns[b]
        sa_first_nz = sa[sa != 0].index.min() if (sa != 0).any() else None
        sb_first_nz = sb[sb != 0].index.min() if (sb != 0).any() else None
        if sa_first_nz is None or sb_first_nz is None:
            continue
        start = max(sa_first_nz, sb_first_nz)
        pair_df = pd.concat({a: sa, b: sb}, axis=1).loc[start:].dropna()
        if len(pair_df) < min_days:
            continue
        val = float(pair_df[a].corr(pair_df[b]))
        result[_pair_key(a, b)] = round(val, 4) if pd.notna(val) else None

    return result if result else None


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

        rolling = returns[a].rolling(window).corr(returns[b])
        result[_pair_key(a, b)] = [
            {"time": idx.strftime("%Y-%m-%d"), "value": round(float(val), 4)}
            for idx, val in rolling.items()
            if pd.notna(val)
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
            if value is not None and value >= alert_threshold:
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
