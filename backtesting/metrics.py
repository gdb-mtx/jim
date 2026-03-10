"""
Performance Metrics — Sharpe, drawdown, Kelly, and more.

Every metric here is used to evaluate strategies before they go anywhere
near real money. See PLAN.md Section 4 for validation requirements.
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
    """Percentage of trades/periods with positive returns.

    Args:
        returns: Series of periodic returns

    Returns:
        Win rate as decimal (0.55 = 55%)
    """
    if len(returns) == 0:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def profit_factor(returns: pd.Series) -> float:
    """Gross profits / gross losses.

    Args:
        returns: Series of periodic returns

    Returns:
        Profit factor (> 1.0 means profitable)
    """
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def kelly_criterion(returns: pd.Series) -> float:
    """Kelly optimal fraction — how much of capital to risk.

    Uses the simplified Kelly formula: f* = (bp - q) / b
    where b = win/loss ratio, p = win probability, q = loss probability

    Args:
        returns: Series of trade returns

    Returns:
        Kelly fraction (optimal % of capital to risk)
    """
    wins = returns[returns > 0]
    losses = returns[returns < 0]

    if len(wins) == 0 or len(losses) == 0:
        return 0.0

    p = len(wins) / len(returns)  # Win probability
    q = 1 - p  # Loss probability
    b = wins.mean() / abs(losses.mean())  # Win/loss ratio

    kelly = (b * p - q) / b
    return float(max(kelly, 0))  # Never negative (means don't trade)


def full_report(returns: pd.Series, name: str = "Strategy") -> dict:
    """Generate a complete performance report.

    Args:
        returns: Series of periodic returns
        name: Strategy name for display

    Returns:
        Dictionary of all metrics
    """
    report = {
        "name": name,
        "total_periods": len(returns),
        "annualized_return": annualized_return(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "calmar_ratio": calmar_ratio(returns),
        "win_rate": win_rate(returns),
        "profit_factor": profit_factor(returns),
        "kelly_criterion": kelly_criterion(returns),
        "kelly_half": kelly_criterion(returns) * 0.5,
        "kelly_quarter": kelly_criterion(returns) * 0.25,
    }
    return report


def print_report(returns: pd.Series, name: str = "Strategy") -> dict:
    """Print a formatted performance report.

    Args:
        returns: Series of periodic returns
        name: Strategy name for display

    Returns:
        Dictionary of all metrics
    """
    report = full_report(returns, name)
    print(f"\n{'='*50}")
    print(f"  {report['name']} — Performance Report")
    print(f"{'='*50}")
    print(f"  Annualized Return:  {report['annualized_return']:>8.2%}")
    print(f"  Sharpe Ratio:       {report['sharpe_ratio']:>8.2f}")
    print(f"  Max Drawdown:       {report['max_drawdown']:>8.2%}")
    print(f"  Calmar Ratio:       {report['calmar_ratio']:>8.2f}")
    print(f"  Win Rate:           {report['win_rate']:>8.2%}")
    print(f"  Profit Factor:      {report['profit_factor']:>8.2f}")
    print(f"  Kelly Criterion:    {report['kelly_criterion']:>8.2%}")
    print(f"  Half-Kelly:         {report['kelly_half']:>8.2%}")
    print(f"  Quarter-Kelly:      {report['kelly_quarter']:>8.2%}")
    print(f"{'='*50}\n")
    return report
