"""
Performance Metrics — CAGR-first scorecard for a wealth compounder.

This project's thesis (reaffirmed 2026-04-18): maximize CAGR subject to
tolerable drawdowns over a 3-5 year horizon. Sharpe is explicitly
de-emphasized — it penalizes upside volatility and normalizes away the
absolute return magnitude, which is the wrong objective for compounding.

The primary scorecard is:
  - CAGR                  — what are we actually compounding at
  - MaxDD                 — worst peak-to-trough pain (survivability gate)
  - Calmar = CAGR/|MaxDD| — return per unit of worst-case pain
  - MAR                   — Calmar using full-history worst drawdown
  - Sterling              — CAGR over average annual drawdown
  - Ulcer Index + UPI     — sustained-pain measure (the "how does holding
                            this actually feel" metric)
  - Sortino               — Sharpe variant that rewards positive skew
  - Omega                 — full-distribution return quality
  - Pain ratio            — CAGR over average ongoing drawdown
  - Burke ratio           — CAGR over sum-of-squared drawdowns
  - Gain-to-Pain          — Schwager's intuitive upside/downside ratio
  - Time underwater %     — how often you are below prior peak
  - Max recovery (days)   — longest stretch below prior peak

Sharpe is still computed and returned (for comparison to external
benchmarks) but is informational — no pass/fail threshold is anchored to
it. See VALIDATION_PLAN.md for the current thresholds.
"""

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0, periods_per_year: int = 252) -> float:
    """Annualized Sharpe ratio.

    Args:
        returns: Series of periodic returns
        risk_free_rate: Annual risk-free rate (default 0)
        periods_per_year: Trading periods per year (252 for daily)

    Returns:
        Annualized Sharpe ratio
    """
    excess = returns - risk_free_rate / periods_per_year
    if excess.std() == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / excess.std())


def max_drawdown(returns: pd.Series) -> float:
    """Maximum drawdown from peak to trough.

    Args:
        returns: Series of periodic returns

    Returns:
        Maximum drawdown as a negative decimal (e.g., -0.25 = -25%)
    """
    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    return float(drawdown.min())


def drawdown_series(returns: pd.Series) -> pd.Series:
    """Full drawdown time series.

    Args:
        returns: Series of periodic returns

    Returns:
        Series of drawdown values at each point in time
    """
    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    return (cumulative - peak) / peak


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calmar ratio — annualized return / max drawdown.

    Args:
        returns: Series of periodic returns
        periods_per_year: Trading periods per year

    Returns:
        Calmar ratio (higher is better)
    """
    ann_return = annualized_return(returns, periods_per_year)
    mdd = max_drawdown(returns)
    if mdd == 0:
        return 0.0
    return float(ann_return / abs(mdd))


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Compound annualized growth rate (CAGR).

    Args:
        returns: Series of periodic returns
        periods_per_year: Trading periods per year

    Returns:
        Annualized return as decimal
    """
    total = (1 + returns).prod()
    n_years = len(returns) / periods_per_year
    if n_years <= 0 or total <= 0:
        return 0.0
    return float(total ** (1 / n_years) - 1)


def win_rate(returns: pd.Series) -> float:
    """Percentage of *active* periods with positive returns.

    Excludes zero-return days (strategy in cash due to filter) from the
    denominator — those days are neither wins nor losses. Without this
    exclusion, filtered strategies (A1/A2/A4) look artificially bad.
    """
    if len(returns) == 0:
        return 0.0
    active = returns[returns != 0]
    if len(active) == 0:
        return 0.0
    return float((active > 0).sum() / len(active))


def profit_factor(returns: pd.Series) -> float:
    """Gross profits / gross losses over active periods (> 1.0 = profitable).

    Cash days (zero returns) don't affect the ratio either way — filtering
    them keeps parity with win_rate and kelly_criterion.
    """
    active = returns[returns != 0]
    gains = active[active > 0].sum()
    losses = abs(active[active < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def kelly_criterion(returns: pd.Series) -> float:
    """Kelly optimal fraction — how much of capital to risk.

    Formula: f* = (bp - q) / b
      b = win/loss ratio, p = win probability, q = 1 - p

    Computed over *active* periods only — zero-return (cash filter) days
    would otherwise drag p down and push Kelly to the negative floor.
    Floored at 0 (negative Kelly means don't trade).
    """
    active = returns[returns != 0]
    wins = active[active > 0]
    losses = active[active < 0]

    if len(active) == 0 or len(wins) == 0 or len(losses) == 0:
        return 0.0

    p = len(wins) / len(active)
    q = 1 - p
    b = wins.mean() / abs(losses.mean())

    kelly = (b * p - q) / b
    return float(max(kelly, 0))


def sortino_ratio(
    returns: pd.Series,
    mar: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Sortino ratio — like Sharpe but only penalizes downside deviation.

    (mean(excess) / downside_deviation) * sqrt(periods_per_year)
    where downside_deviation = sqrt(mean((r - MAR)^2 for r < MAR)).

    Upside volatility is free — right for skewed/fat-tailed strategies
    that would be unfairly penalized by Sharpe.

    Args:
        returns: Series of periodic returns.
        mar: Minimum acceptable return per period (default 0).
        periods_per_year: 252 for equity, 365 for crypto.
    """
    if len(returns) == 0:
        return 0.0
    excess = returns - mar
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 0.0
    downside_dev = float(np.sqrt((downside ** 2).mean()))
    if downside_dev == 0:
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / downside_dev)


def ulcer_index(returns: pd.Series) -> float:
    """Ulcer Index (Martin 1987) — sustained-drawdown measure.

    sqrt(mean(drawdown^2)) where drawdown is continuous (0 at peaks,
    negative when underwater). Punishes long underwater stretches much
    harder than MaxDD does. Expressed as a positive number in decimal
    form (0.10 = 10% Ulcer).
    """
    if len(returns) == 0:
        return 0.0
    dd = drawdown_series(returns)
    return float(np.sqrt((dd ** 2).mean()))


def ulcer_performance_index(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Ulcer Performance Index = (CAGR - rf) / Ulcer Index.

    The "how does this actually feel to hold" ratio. A strategy with one
    sharp crash and quick recovery has the same Calmar as one with a
    gradual 2-year drawdown, but this metric punishes the second much
    harder — correctly reflecting behavioral tolerance.
    """
    ui = ulcer_index(returns)
    if ui == 0:
        return 0.0
    return float((annualized_return(returns, periods_per_year) - risk_free_rate) / ui)


def mar_ratio(returns: pd.Series, worst_dd: float | None = None, periods_per_year: int = 252) -> float:
    """MAR ratio — Managed Accounts Reports style.

    CAGR / |longest-ever max drawdown|. Identical to Calmar when you only
    have test-period history; differs when you supply a worst_dd from a
    longer window (e.g. full-sample MaxDD when evaluating test-period
    CAGR). More conservative than Calmar.

    Args:
        returns: Test-period returns for the CAGR numerator.
        worst_dd: Optional worst drawdown over all history (negative
            number). If None, uses MaxDD of `returns` itself.
    """
    cagr = annualized_return(returns, periods_per_year)
    dd = worst_dd if worst_dd is not None else max_drawdown(returns)
    if dd == 0:
        return 0.0
    return float(cagr / abs(dd))


def sterling_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Sterling ratio — CAGR / mean(annual max drawdowns).

    Groups the return stream into calendar years, computes each year's
    MaxDD, averages. Less sensitive to one outlier crash than Calmar.
    If only one year is available, returns Calmar.
    """
    if len(returns) < periods_per_year // 2:
        return calmar_ratio(returns, periods_per_year)
    annual_dds = []
    for _, year_returns in returns.groupby(returns.index.year):
        if len(year_returns) >= 20:
            annual_dds.append(abs(max_drawdown(year_returns)))
    if not annual_dds:
        return calmar_ratio(returns, periods_per_year)
    avg_dd = float(np.mean(annual_dds))
    if avg_dd == 0:
        return 0.0
    return float(annualized_return(returns, periods_per_year) / avg_dd)


def burke_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Burke ratio — (CAGR - rf) / sqrt(sum of squared individual drawdowns).

    Treats each distinct drawdown event separately. A strategy with many
    small drawdowns scores worse than one with the same MaxDD but fewer
    events. Useful for distinguishing "smooth with one crash" from
    "constantly wobbling".
    """
    if len(returns) == 0:
        return 0.0
    dd = drawdown_series(returns)
    # Identify distinct drawdown episodes: each contiguous run of dd < 0
    episodes: list[float] = []
    current_min = 0.0
    for v in dd.values:
        if v < 0:
            current_min = min(current_min, float(v))
        else:
            if current_min < 0:
                episodes.append(current_min)
            current_min = 0.0
    if current_min < 0:
        episodes.append(current_min)
    if not episodes:
        return 0.0
    denom = float(np.sqrt(sum(e ** 2 for e in episodes)))
    if denom == 0:
        return 0.0
    cagr = annualized_return(returns, periods_per_year)
    return float((cagr - risk_free_rate) / denom)


def pain_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Pain ratio — CAGR / mean(|drawdown|).

    Continuous analog of Calmar — measures everyday drag, not just the
    worst moment. A strategy spending half its life at -5% drawdown
    has the same MaxDD as one spending 5% of its life there, but much
    worse Pain ratio.
    """
    if len(returns) == 0:
        return 0.0
    dd = drawdown_series(returns)
    avg_dd = float(abs(dd).mean())
    if avg_dd == 0:
        return 0.0
    return float(annualized_return(returns, periods_per_year) / avg_dd)


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    """Omega ratio — P-weighted gains above threshold / P-weighted losses below.

    Uses the full distribution shape, not just first two moments. A 1.0
    Omega means equal probability-weighted upside and downside; > 1 means
    more upside. Threshold of 0 is standard; use risk_free / periods for
    a stricter bar.
    """
    if len(returns) == 0:
        return 0.0
    excess = returns - threshold
    gains = excess[excess > 0].sum()
    losses = -excess[excess < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def gain_to_pain_ratio(returns: pd.Series) -> float:
    """Schwager Gain-to-Pain = sum(positive) / |sum(negative)|.

    Intuitive ratio: "how much total gain did I get for how much total
    pain?" Typically computed on monthly returns; daily works too. > 1
    means more gain than pain; > 2 is excellent.
    """
    if len(returns) == 0:
        return 0.0
    pos = returns[returns > 0].sum()
    neg = abs(returns[returns < 0].sum())
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return float(pos / neg)


def time_underwater_pct(returns: pd.Series) -> float:
    """Fraction of periods spent below prior peak (in drawdown).

    0.40 = 40% of the time you were holding at a loss relative to the
    prior peak. Behaviorally corrosive above ~0.30.
    """
    if len(returns) == 0:
        return 0.0
    dd = drawdown_series(returns)
    return float((dd < -1e-9).mean())


def max_recovery_days(returns: pd.Series) -> int:
    """Longest run of consecutive periods underwater.

    The "how long until I saw a new peak" metric. Over ~250 days (1
    trading year) is behaviorally hard to hold through.
    """
    if len(returns) == 0:
        return 0
    dd = drawdown_series(returns)
    longest = 0
    current = 0
    for v in dd.values:
        if v < -1e-9:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def full_scorecard(returns: pd.Series, periods_per_year: int = 252) -> dict:
    """Compute the complete CAGR-first scorecard for a returns series.

    This is the function the validation runner and dashboard should use.
    Sharpe is included for reference only — treat the drawdown-family
    and CAGR metrics as primary.
    """
    cagr = annualized_return(returns, periods_per_year)
    mdd = max_drawdown(returns)
    calmar = calmar_ratio(returns, periods_per_year)
    ui = ulcer_index(returns)
    return {
        "cagr": cagr,
        "max_drawdown": mdd,
        "calmar": calmar,
        "mar": mar_ratio(returns, periods_per_year=periods_per_year),
        "sterling": sterling_ratio(returns, periods_per_year),
        "ulcer_index": ui,
        "ulcer_performance_index": ulcer_performance_index(returns, periods_per_year=periods_per_year),
        "sortino": sortino_ratio(returns, periods_per_year=periods_per_year),
        "omega": omega_ratio(returns),
        "pain_ratio": pain_ratio(returns, periods_per_year),
        "burke": burke_ratio(returns, periods_per_year=periods_per_year),
        "gain_to_pain": gain_to_pain_ratio(returns),
        "time_underwater_pct": time_underwater_pct(returns),
        "max_recovery_days": max_recovery_days(returns),
        "total_periods": int(len(returns)),
        # Informational — not gated on
        "sharpe": sharpe_ratio(returns, periods_per_year=periods_per_year),
    }


def marginal_portfolio_contribution(
    candidate: pd.Series,
    existing: pd.Series,
    weight: float = 0.25,
    periods_per_year: int = 252,
) -> dict:
    """Measure how adding a candidate at `weight` changes combined CAGR + Calmar.

    For a satellite allocation (Account 4 is 25% of total), this is the
    metric that matters. A low-standalone-Sharpe candidate with low
    correlation to the core can improve the combined portfolio more
    than a high-standalone-Sharpe candidate that correlates to the core.

    Calendar alignment: uses `existing`'s calendar as the reference.
    `candidate`'s returns are compounded and reindexed onto that calendar,
    so Fri→Mon crypto weekend compounding is preserved on the equity
    trading calendar. `periods_per_year` should match `existing`'s
    calendar (252 for equity trading days).

    Returns:
        Dict with base/combined metrics and the deltas.
    """
    correlation = float(candidate.corr(existing))  # on native overlap

    cand_curve = (1.0 + candidate).cumprod()
    cand_on_cal = cand_curve.reindex(existing.index, method="ffill").pct_change()
    df = pd.DataFrame({"cand": cand_on_cal, "base": existing}).dropna()
    cand = df["cand"]
    base = df["base"]

    combined = weight * cand + (1 - weight) * base
    base_cagr = annualized_return(base, periods_per_year)
    base_dd = max_drawdown(base)
    base_calmar = calmar_ratio(base, periods_per_year)
    new_cagr = annualized_return(combined, periods_per_year)
    new_dd = max_drawdown(combined)
    new_calmar = calmar_ratio(combined, periods_per_year)
    return {
        "weight": weight,
        "correlation": correlation,
        "base_cagr": float(base_cagr),
        "combined_cagr": float(new_cagr),
        "delta_cagr": float(new_cagr - base_cagr),
        "base_maxdd": float(base_dd),
        "combined_maxdd": float(new_dd),
        "delta_maxdd": float(new_dd - base_dd),
        "base_calmar": float(base_calmar),
        "combined_calmar": float(new_calmar),
        "delta_calmar": float(new_calmar - base_calmar),
    }


def full_report(returns: pd.Series, name: str = "Strategy", periods_per_year: int = 252) -> dict:
    """Generate a complete performance report with the full scorecard.

    Keeps legacy keys (annualized_return, sharpe_ratio, calmar_ratio,
    max_drawdown, win_rate, profit_factor, kelly_*) for backward
    compatibility. Adds the CAGR-first scorecard metrics.

    Args:
        returns: Series of periodic returns
        name: Strategy name for display
        periods_per_year: Trading periods per year (252 for stocks, 365 for crypto)

    Returns:
        Dictionary of all metrics — legacy keys + scorecard keys.
    """
    kelly = kelly_criterion(returns)
    scorecard = full_scorecard(returns, periods_per_year)
    report = {
        "name": name,
        "total_periods": len(returns),
        # Legacy keys (kept for backward compat with API routes)
        "annualized_return": scorecard["cagr"],
        "sharpe_ratio": scorecard["sharpe"],
        "max_drawdown": scorecard["max_drawdown"],
        "calmar_ratio": scorecard["calmar"],
        "win_rate": win_rate(returns),
        "profit_factor": profit_factor(returns),
        "kelly_criterion": kelly,
        "kelly_half": kelly * 0.5,
        "kelly_quarter": kelly * 0.25,
    }
    # Scorecard keys (the ones we actually evaluate on)
    report.update(scorecard)
    return report


def print_report(returns: pd.Series, name: str = "Strategy", periods_per_year: int = 252) -> dict:
    """Print the CAGR-first scorecard for a strategy.

    Args:
        returns: Series of periodic returns.
        name: Strategy name for display.
        periods_per_year: 252 for equity, 365 for crypto.

    Returns:
        Dictionary of all metrics.
    """
    r = full_report(returns, name, periods_per_year)
    print(f"\n{'=' * 56}")
    print(f"  {name} — Scorecard")
    print(f"{'=' * 56}")
    print(f"  PRIMARY (CAGR-first)")
    print(f"    CAGR:                {r['cagr']:>+10.2%}")
    print(f"    Max Drawdown:        {r['max_drawdown']:>+10.2%}")
    print(f"    Calmar:              {r['calmar']:>10.2f}")
    print(f"  DRAWDOWN FAMILY")
    print(f"    MAR:                 {r['mar']:>10.2f}")
    print(f"    Sterling:            {r['sterling']:>10.2f}")
    print(f"    Burke:               {r['burke']:>10.2f}")
    print(f"    Pain Ratio:          {r['pain_ratio']:>10.2f}")
    print(f"    Ulcer Index:         {r['ulcer_index']:>+10.2%}")
    print(f"    Ulcer Perf Index:    {r['ulcer_performance_index']:>10.2f}")
    print(f"  DOWNSIDE / DISTRIBUTION")
    print(f"    Sortino:             {r['sortino']:>10.2f}")
    print(f"    Omega:               {r['omega']:>10.2f}")
    print(f"    Gain-to-Pain:        {r['gain_to_pain']:>10.2f}")
    print(f"  BEHAVIORAL")
    print(f"    Time underwater:     {r['time_underwater_pct']:>+10.1%}")
    print(f"    Max recovery (days): {r['max_recovery_days']:>10d}")
    print(f"  SIZING")
    print(f"    Win Rate:            {r['win_rate']:>+10.2%}")
    print(f"    Profit Factor:       {r['profit_factor']:>10.2f}")
    print(f"    Quarter-Kelly:       {r['kelly_quarter']:>+10.2%}")
    print(f"  INFORMATIONAL")
    print(f"    Sharpe (de-empha):   {r['sharpe']:>10.2f}")
    print(f"{'=' * 56}\n")
    return r
