"""Macro composite — pre-registered one-shot evaluation.

Applies the composite scalar (lagged one day) to (a) SPY and (b) the
current validated book (50/50 sm_filtered + trend_lowvol, both with their
2026-07-18 vol-scaling configs), and reports:
  - CAGR / MaxDD / Calmar with vs without, full sample and OOS 2023+.
  - Crisis timing: for 2018Q4, 2020, 2022 — the date the composite first
    cut exposure (scalar < 1.0) vs the date SPY closed below its 200d SMA,
    and drawdown depth with vs without.
  - Bull-market cost: return give-up in 2023-2025.
  - Today's votes.

The spec in strategies/macro_composite.py is pre-registered; this script
reports whatever comes out. No threshold tuning against these results.

Usage: uv run python3 scripts/macro_composite_eval.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.sp500 import download_sp500_prices
from strategies.macro_composite import compute_macro_composite
from strategies.portfolio_backtest import run_portfolio


def perf(r: pd.Series, label: str) -> str:
    r = r.dropna()
    if len(r) < 50:
        return f"{label}: insufficient data"
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    return f"{label:42s} CAGR {cagr:+6.1%}  MaxDD {dd:+6.1%}  Calmar {cagr / abs(dd):5.2f}"


def main():
    px = yf.download(
        ["HYG", "IEF", "UUP", "XLU", "SPY", "^VIX9D", "^VIX3M"],
        start="2007-01-01", progress=False, auto_adjust=True,
    )["Close"]
    sp500 = download_sp500_prices(start="2007-01-01")
    comp = compute_macro_composite(
        px[["HYG", "IEF", "UUP", "XLU", "SPY"]].dropna(subset=["HYG", "IEF"]),
        vix9d=px["^VIX9D"], vix3m=px["^VIX3M"], sp500_prices=sp500,
    )
    scalar = comp["scalar"].shift(1).fillna(1.0)

    print(f"composite coverage: {comp.index[0].date()} → {comp.index[-1].date()}")
    print(f"scalar distribution: {comp['scalar'].value_counts(normalize=True).sort_index().round(3).to_dict()}")

    # --- SPY stress test ---
    spy_r = px["SPY"].pct_change()
    print("\n=== SPY 2008→now ===")
    print(perf(spy_r, "SPY buy-hold"))
    print(perf(spy_r * scalar.reindex(spy_r.index).fillna(1.0), "SPY x composite"))

    # --- the current validated book ---
    _, a1 = run_portfolio("sm_filtered", start="2010-01-01")
    _, a2 = run_portfolio("trend_lowvol", start="2010-01-01")
    book = (a1.fillna(0) + a2.fillna(0)) / 2
    s = scalar.reindex(book.index).fillna(1.0)
    for tag, sl in [("full 2010→now", slice(None, None)), ("OOS 2023→now", slice("2023-01-03", None))]:
        print(f"\n=== book (A1+A2, current configs) — {tag} ===")
        print(perf(book[sl], "book"))
        print(perf((book * s)[sl], "book x composite"))

    # --- bull-market cost ---
    print("\n=== bull-cost (calendar years) ===")
    for y in ["2013", "2017", "2019", "2021", "2023", "2024", "2025"]:
        b = (1 + book[y]).prod() - 1
        bc = (1 + (book * s)[y]).prod() - 1
        print(f"  {y}: book {b:+7.2%} → with composite {bc:+7.2%}  (give-up {bc - b:+.2%})")

    # --- crisis timing vs SPY 200d ---
    spy_ma = px["SPY"].rolling(200).mean()
    below = px["SPY"] < spy_ma
    print("\n=== crisis timing: first de-risk (scalar<1) vs SPY<200d ===")
    for label, start, end in [
        ("2018Q4", "2018-09-01", "2019-01-01"),
        ("COVID", "2020-01-01", "2020-04-01"),
        ("2022", "2021-11-01", "2022-07-01"),
    ]:
        win = comp.loc[start:end]
        first_derisk = win.index[win["scalar"] < 1.0]
        spy_win = below.loc[start:end]
        first_spy = spy_win.index[spy_win]
        d1 = first_derisk[0].date() if len(first_derisk) else None
        d2 = first_spy[0].date() if len(first_spy) else None
        lead = (pd.Timestamp(d2) - pd.Timestamp(d1)).days if d1 and d2 else None
        print(f"  {label}: composite {d1}  SPY-200d {d2}  lead {lead} days")
        peak = px["SPY"].loc[start:end].idxmax()
        print(f"    votes at first de-risk: "
              f"{win.loc[first_derisk[0], ['credit','dollar','vix_ts','breadth','defense']].to_dict() if len(first_derisk) else 'n/a'}")

    # --- today ---
    last = comp.iloc[-1]
    print(f"\n=== today ({comp.index[-1].date()}) ===")
    print(f"votes: credit={last['credit']} dollar={last['dollar']} vix_ts={last['vix_ts']} "
          f"breadth={last['breadth']} defense={last['defense']} → total {last['votes']:.0f}, scalar {last['scalar']}")


if __name__ == "__main__":
    main()
