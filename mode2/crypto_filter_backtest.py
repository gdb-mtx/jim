"""
Crypto Filter Optimization — Research Thread 5.

Tests different BTC trend filter configurations on the Crypto Momentum strategy:
- SMA periods: 100, 150, 200 (current), 250, 300 days
- EMA vs SMA
- Dual MA crossover (50d crossing above 200d, etc.)
- Hysteresis bands (enter at MA+X%, exit at MA-X%)
- No filter baseline

The goal: find whether earlier or smarter entries improve risk-adjusted returns
for Account 4's daily crypto momentum rotation.

Usage:
    uv run python3 -m mode2.crypto_filter_backtest
"""

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtesting.metrics import full_report
from data.crypto import download_crypto_prices, download_btc_prices
from strategies.crypto_momentum import CryptoMomentum
from strategies.portfolio import apply_vol_scaling

warnings.filterwarnings("ignore")

START_DATE = "2018-01-01"
VOL_SCALING_PARAMS = {"vol_target": 0.15, "vol_halflife": 30, "scalar_floor": 0.1, "scalar_cap": 2.0}


@dataclass
class FilterResult:
    name: str
    sharpe: float
    cagr: float
    max_dd: float
    calmar: float
    win_rate: float
    days_invested: float  # % of days actually invested (not in cash)
    total_return: float
    vol: float


def _make_result(name: str, report: dict, pct_invested: float) -> FilterResult:
    """Build FilterResult from full_report output."""
    cagr = report["annualized_return"]
    max_dd = report["max_drawdown"]
    n_periods = report["total_periods"]
    years = n_periods / 365
    total_ret = (1 + cagr) ** years - 1 if years > 0 else 0
    vol = cagr / report["sharpe_ratio"] if report["sharpe_ratio"] != 0 else 0
    return FilterResult(
        name=name,
        sharpe=report["sharpe_ratio"],
        cagr=cagr * 100,
        max_dd=max_dd * 100,
        calmar=report["calmar_ratio"],
        win_rate=report.get("win_rate", 0) * 100,
        days_invested=pct_invested,
        total_return=total_ret * 100,
        vol=abs(vol) * 100,
    )


def run_with_sma_filter(prices, btc, ma_period: int, vol_scale: bool = True) -> FilterResult:
    """Run crypto momentum with SMA-based BTC filter."""
    strat = CryptoMomentum(btc_ma_period=ma_period)
    strat.set_btc(btc)
    returns = strat.generate_returns(prices)

    # Calculate days invested (filter was on)
    btc_aligned = btc.reindex(prices.index).ffill()
    btc_ma = btc_aligned.rolling(ma_period, min_periods=1).mean()
    pct_invested = (btc_aligned > btc_ma).mean() * 100

    if vol_scale:
        returns = apply_vol_scaling(returns, **VOL_SCALING_PARAMS)

    report = full_report(returns, periods_per_year=365)
    return _make_result(f"SMA-{ma_period}", report, pct_invested)


def run_with_ema_filter(prices, btc, ma_period: int, vol_scale: bool = True) -> FilterResult:
    """Run crypto momentum with EMA-based BTC filter."""
    strat = CryptoMomentum(btc_ma_period=ma_period)

    # Override BTC trend scalar to use EMA instead of SMA
    btc_aligned = btc.reindex(prices.index).ffill()
    btc_ema = btc_aligned.ewm(span=ma_period, min_periods=1).mean()
    ema_scalar = pd.Series(np.where(btc_aligned > btc_ema, 1.0, 0.0), index=prices.index)
    pct_invested = (btc_aligned > btc_ema).mean() * 100

    # Generate momentum signals without BTC filter, then apply EMA filter manually
    strat._btc = None  # Disable built-in filter
    weights = strat.generate_signals(prices)
    weights = weights.mul(ema_scalar, axis=0)

    # Calculate returns from weights
    daily_returns = prices.pct_change()
    returns = (weights.shift(1) * daily_returns).sum(axis=1)
    returns = returns.loc[returns.index[0]:]

    if vol_scale:
        returns = apply_vol_scaling(returns, **VOL_SCALING_PARAMS)

    report = full_report(returns, periods_per_year=365)
    return _make_result(f"EMA-{ma_period}", report, pct_invested)


def run_with_dual_ma(prices, btc, fast: int, slow: int, vol_scale: bool = True) -> FilterResult:
    """Run crypto momentum with dual MA crossover filter (golden/death cross)."""
    strat = CryptoMomentum()

    btc_aligned = btc.reindex(prices.index).ffill()
    fast_ma = btc_aligned.rolling(fast, min_periods=1).mean()
    slow_ma = btc_aligned.rolling(slow, min_periods=1).mean()

    # Invest when fast MA > slow MA (golden cross), cash when below (death cross)
    cross_scalar = pd.Series(np.where(fast_ma > slow_ma, 1.0, 0.0), index=prices.index)
    pct_invested = (fast_ma > slow_ma).mean() * 100

    strat._btc = None
    weights = strat.generate_signals(prices)
    weights = weights.mul(cross_scalar, axis=0)

    daily_returns = prices.pct_change()
    returns = (weights.shift(1) * daily_returns).sum(axis=1)
    returns = returns.loc[returns.index[0]:]

    if vol_scale:
        returns = apply_vol_scaling(returns, **VOL_SCALING_PARAMS)

    report = full_report(returns, periods_per_year=365)
    return _make_result(f"Dual-{fast}/{slow}", report, pct_invested)


def run_with_hysteresis(prices, btc, ma_period: int, enter_pct: float,
                         exit_pct: float, vol_scale: bool = True) -> FilterResult:
    """Run with hysteresis bands around MA.

    Enter when BTC > MA * (1 + enter_pct), exit when BTC < MA * (1 - exit_pct).
    Prevents whipsaws around the MA line.
    """
    strat = CryptoMomentum()

    btc_aligned = btc.reindex(prices.index).ffill()
    btc_ma = btc_aligned.rolling(ma_period, min_periods=1).mean()

    # Build state machine: start in cash
    invested = pd.Series(0.0, index=prices.index)
    state = 0.0  # 0 = cash, 1 = invested
    for i in range(len(prices.index)):
        price = btc_aligned.iloc[i]
        ma = btc_ma.iloc[i]
        if pd.isna(price) or pd.isna(ma):
            invested.iloc[i] = state
            continue
        if state == 0.0 and price > ma * (1 + enter_pct):
            state = 1.0
        elif state == 1.0 and price < ma * (1 - exit_pct):
            state = 0.0
        invested.iloc[i] = state

    pct_invested = invested.mean() * 100

    strat._btc = None
    weights = strat.generate_signals(prices)
    weights = weights.mul(invested, axis=0)

    daily_returns = prices.pct_change()
    returns = (weights.shift(1) * daily_returns).sum(axis=1)
    returns = returns.loc[returns.index[0]:]

    if vol_scale:
        returns = apply_vol_scaling(returns, **VOL_SCALING_PARAMS)

    report = full_report(returns, periods_per_year=365)
    return _make_result(f"Hyst-{ma_period}(+{enter_pct*100:.0f}%/-{exit_pct*100:.0f}%)", report, pct_invested)


def run_no_filter(prices, btc, vol_scale: bool = True) -> FilterResult:
    """Run crypto momentum with NO trend filter (always invested)."""
    strat = CryptoMomentum()
    strat._btc = None  # No filter
    returns = strat.generate_returns(prices)

    if vol_scale:
        returns = apply_vol_scaling(returns, **VOL_SCALING_PARAMS)

    report = full_report(returns, periods_per_year=365)
    return _make_result("No Filter", report, 100.0)


def run_btc_only(btc, vol_scale: bool = False) -> FilterResult:
    """BTC buy-and-hold benchmark."""
    returns = btc.pct_change().dropna()
    report = full_report(returns, periods_per_year=365)
    return _make_result("BTC Hold", report, 100.0)


def print_results(results: list[FilterResult]):
    """Print comparison table."""
    print(f"\n{'=' * 95}")
    print("CRYPTO FILTER OPTIMIZATION — Crypto Momentum Rotation + Vol-Scaling")
    print(f"{'=' * 95}")
    print(f"\n{'Filter':<30} {'Sharpe':>7} {'CAGR':>8} {'MaxDD':>8} {'Calmar':>8} "
          f"{'TotRet':>9} {'Vol':>7} {'%Inv':>6}")
    print(f"{'─' * 95}")

    # Sort by Sharpe descending
    sorted_results = sorted(results, key=lambda r: r.sharpe, reverse=True)
    baseline_sharpe = next((r.sharpe for r in results if r.name == "SMA-200"), None)

    for r in sorted_results:
        marker = " ◀ current" if r.name == "SMA-200" else ""
        delta = ""
        if baseline_sharpe is not None and r.name != "SMA-200":
            d = r.sharpe - baseline_sharpe
            delta = f" ({d:+.2f})"
        print(f"  {r.name:<28} {r.sharpe:>6.2f}{delta:<8} {r.cagr:>+7.1f}% {r.max_dd:>7.1f}% "
              f"{r.calmar:>7.2f} {r.total_return:>+8.1f}% {r.vol:>6.1f}% {r.days_invested:>5.0f}%"
              f"{marker}")

    # Summary
    best = sorted_results[0]
    current = next((r for r in results if r.name == "SMA-200"), None)
    print(f"\n{'─' * 95}")
    print(f"  Best: {best.name} (Sharpe {best.sharpe:.2f}, CAGR {best.cagr:+.1f}%, MaxDD {best.max_dd:.1f}%)")
    if current and best.name != current.name:
        print(f"  vs Current SMA-200: Sharpe {best.sharpe - current.sharpe:+.2f}, "
              f"CAGR {best.cagr - current.cagr:+.1f}%, MaxDD {best.max_dd - current.max_dd:+.1f}%")


def main():
    print("Loading crypto data...")
    prices = download_crypto_prices(start=START_DATE)
    btc = download_btc_prices()
    print(f"  Crypto prices: {prices.shape[0]} days, {prices.shape[1]} coins")
    print(f"  BTC data: {len(btc)} days ({btc.index[0].date()} to {btc.index[-1].date()})")

    results = []

    # ── Benchmarks ──
    print("\nRunning benchmarks...")
    results.append(run_btc_only(btc))
    results.append(run_no_filter(prices, btc))

    # ── SMA filters (different periods) ──
    print("Testing SMA periods...")
    for period in [50, 100, 150, 200, 250, 300]:
        results.append(run_with_sma_filter(prices, btc, period))

    # ── EMA filters ──
    print("Testing EMA periods...")
    for period in [100, 150, 200, 250]:
        results.append(run_with_ema_filter(prices, btc, period))

    # ── Dual MA crossover ──
    print("Testing dual MA crossover...")
    for fast, slow in [(20, 100), (50, 150), (50, 200), (20, 200), (100, 300)]:
        results.append(run_with_dual_ma(prices, btc, fast, slow))

    # ── Hysteresis bands ──
    print("Testing hysteresis bands...")
    for ma, enter, exit_ in [
        (200, 0.0, 0.05),   # Enter at MA, exit at MA-5%
        (200, 0.03, 0.03),  # Symmetric 3% band
        (200, 0.05, 0.05),  # Symmetric 5% band
        (150, 0.0, 0.05),   # 150d MA, exit at -5%
        (150, 0.03, 0.03),  # 150d MA, symmetric 3%
    ]:
        results.append(run_with_hysteresis(prices, btc, ma, enter, exit_))

    print_results(results)


if __name__ == "__main__":
    main()
