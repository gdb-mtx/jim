"""A1 overlay research (2026-10-21): sign-aware vol scaling + idle-cash yield.

Backtest-only — nothing here touches the live path. Reproduces run_portfolio's
raw (post-filter, pre-overlay, net-of-cost) A1 returns and re-applies the
vol overlay under alternative gates, then prices the T-bill yield the
backtest currently forgoes on idle cash. No look-ahead: every gate uses
information through D-1, exactly like the production scalar (shift(1)).

Usage: uv run python3 scripts/a1_overlay_research.py
"""

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.sp500 import download_sp500_prices, download_vix  # noqa: E402
from strategies.portfolio_backtest import run_portfolio  # noqa: E402
from strategies.portfolio_config import PORTFOLIOS, STOCK_STRATEGIES, compute_spy_trend_filter  # noqa: E402

P = PORTFOLIOS["sm_filtered"]["vol_scaling_params"]
TARGET, HL, FLOOR, CAP = P["vol_target"], P["vol_halflife"], P["scalar_floor"], P["scalar_cap"]
BORROW = 0.055
OOS = "2023-01-01"


def metrics(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod(); yrs = len(r) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1).min()
    return {"CAGR": cagr, "maxDD": dd, "Calmar": cagr / abs(dd), "vol": r.std() * np.sqrt(252)}


def scaled(raw: pd.Series, cap_series: pd.Series | None = None, dd_gate: float | None = None) -> tuple[pd.Series, pd.Series]:
    """Production overlay with optional gates. cap_series: per-day cap (1.0 or CAP)
    from information through D-1. dd_gate: cap 1.0 while the SCALED equity is
    more than dd_gate below its high (through D-1) — iterative, like live."""
    vol = np.sqrt(raw.ewm(halflife=HL).var()) * np.sqrt(252)
    base = (TARGET / vol.replace(0, np.nan)).clip(lower=FLOOR, upper=CAP).shift(1).fillna(1.0)
    if cap_series is not None:
        base = np.minimum(base, cap_series.reindex(base.index).ffill().fillna(CAP))
    if dd_gate is None:
        s = base
    else:
        s = base.copy(); eq = 1.0; peak = 1.0
        vals = raw.values; b = base.values; out = np.empty(len(raw))
        for i in range(len(raw)):
            cap_i = 1.0 if (eq / peak - 1) < -dd_gate else CAP
            out[i] = min(b[i], cap_i)
            eq *= 1 + vals[i] * out[i] - max(out[i] - 1, 0) * BORROW / 252
            peak = max(peak, eq)
        s = pd.Series(out, index=raw.index)
    ret = raw * s - (s - 1).clip(lower=0) * BORROW / 252
    return ret, s


def main() -> None:
    st: dict = {}
    _, prod = run_portfolio("sm_filtered", start="2010-01-01", stages_out=st)
    raw = st["raw_returns"].dropna()
    base_ret, base_s = scaled(raw)
    assert np.allclose(base_ret.loc[prod.index], prod.loc[base_ret.index].reindex(base_ret.loc[prod.index].index), atol=1e-12), "overlay reproduction drifted from run_portfolio"

    spy_cap = compute_spy_trend_filter(start="2010-01-01").reindex(raw.index).ffill().shift(1)
    spy_cap = spy_cap.where(spy_cap >= 1.0, 1.0).where(spy_cap < 1.0, CAP)   # below MA -> cap 1.0
    own_trend = (1 + raw).rolling(63).apply(np.prod, raw=True).shift(1) - 1
    trend_cap = pd.Series(np.where(own_trend < 0, 1.0, CAP), index=raw.index)

    variants = {
        "production (cap 1.5 always)": scaled(raw),
        "no overlay (1.0x)": (raw, pd.Series(1.0, index=raw.index)),
        "cap 1.0 below SPY 200d": scaled(raw, cap_series=spy_cap),
        "cap 1.0 in own drawdown > 3%": scaled(raw, dd_gate=0.03),
        "cap 1.0 in own drawdown > 5%": scaled(raw, dd_gate=0.05),
        "cap 1.0 in own drawdown > 8%": scaled(raw, dd_gate=0.08),
        "cap 1.0 if own 63d return < 0": scaled(raw, cap_series=trend_cap),
        "SPY 200d + drawdown > 5%": scaled(raw, cap_series=spy_cap, dd_gate=0.05),
    }
    print("=== 1. Sign-aware vol scaling — A1, net of costs + 5.5% financing ===")
    print(f"{'variant':34s} {'OOS CAGR':>9s} {'OOS maxDD':>10s} {'Calmar':>7s} | {'full CAGR':>9s} {'full maxDD':>10s} {'Calmar':>7s} | {'at cap':>6s}")
    for name, (ret, s) in variants.items():
        o, f = metrics(ret.loc[OOS:]), metrics(ret)
        at_cap = (s.loc[OOS:] >= CAP - 1e-9).mean()
        print(f"{name:34s} {o['CAGR']:+9.1%} {o['maxDD']:+10.1%} {o['Calmar']:7.2f} | {f['CAGR']:+9.1%} {f['maxDD']:+10.1%} {f['Calmar']:7.2f} | {at_cap:6.0%}")

    # ---- 2. idle cash yield
    prices = download_sp500_prices(); vix = download_vix()
    strat = STOCK_STRATEGIES["stock_momentum"](); strat.set_vix(vix)
    sig = strat.generate_signals(prices)
    spy_f = compute_spy_trend_filter(start="2010-01-01").reindex(raw.index).ffill().shift(1).fillna(1.0)
    gross_raw = sig.shift(1).sum(axis=1).reindex(raw.index).fillna(0) * spy_f
    csv = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3", timeout=30).text
    tb = pd.read_csv(io.StringIO(csv), na_values=".")
    tb = pd.Series(tb.iloc[:, 1].values, index=pd.to_datetime(tb.iloc[:, 0])).ffill().reindex(raw.index).ffill() / 100
    print("\n=== 2. Idle cash yield (3-month T-bill, FRED DTB3) ===")
    print(f"{'variant':34s} {'cash avg':>8s} {'OOS CAGR':>9s} {'Calmar':>7s} | {'full CAGR':>9s} {'Calmar':>7s} | {'+pp OOS':>8s}")
    for name in ("production (cap 1.5 always)", "cap 1.0 in own drawdown > 5%", "SPY 200d + drawdown > 5%"):
        ret, s = variants[name]
        gross = gross_raw * s
        cash = (1 - gross).clip(lower=0)
        with_yield = ret + cash * tb / 252
        o0, o1 = metrics(ret.loc[OOS:]), metrics(with_yield.loc[OOS:]); f1 = metrics(with_yield)
        print(f"{name:34s} {cash.loc[OOS:].mean():8.0%} {o1['CAGR']:+9.1%} {o1['Calmar']:7.2f} | {f1['CAGR']:+9.1%} {f1['Calmar']:7.2f} | {o1['CAGR']-o0['CAGR']:+8.1%}")
    print(f"\nT-bill now {tb.iloc[-1]:.2%}; OOS average {tb.loc[OOS:].mean():.2%}; 2010-2015 average {tb.loc['2010':'2015'].mean():.2%}")


if __name__ == "__main__":
    main()
