"""Live scorecard — the evidence engine for the Q3 real-money checkpoint.

Per account (A1, A2), per 21-trading-day rebalance cycle since the clean
window began (2026-04-21):
  live      account return from equity snapshots
  signal    same-period return of the strategy's backtest path (current
            configs, net of costs) — live minus signal = execution drag
  SPY       benchmark return; live minus SPY = the alpha the Q3 gate needs

Gate reminder (CLAUDE.md next steps): real money wants A1 clean-window
alpha >= 0 over 2-3 cycles. This script is the single source for that
number — no more ad-hoc sessions math.

Usage:
  uv run python3 scripts/live_scorecard.py            # full report
  uv run python3 scripts/live_scorecard.py --notify   # + one-line macOS summary
                                                      # (weekly cron, Monday 09:00 local)
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))

from strategies.portfolio_backtest import run_portfolio

from strategies.base import REBALANCE_ANCHOR

# Cycle boundaries share the strategies' re-ranking phase by construction.
CLEAN_START = pd.Timestamp(REBALANCE_ANCHOR)
CYCLE_DAYS = 21
ACCOUNTS = {1: "sm_filtered", 2: "trend_lowvol"}
# Real-money allocation between the two strategies (2026-08-12 sizing
# decision). The paper accounts sit ~50/50 by equity and are never reset —
# a reset would print as a fake ±38% cycle here — so the 70/30 book is
# scored synthetically from per-account returns instead.
BOOK_WEIGHTS = {1: 0.70, 2: 0.30}


def load_live(account: int) -> pd.Series:
    df = pd.read_parquet(f"data/processed/snapshots_acct{account}.parquet")
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index)
    return df["equity"].sort_index()


def window_return(series: pd.Series, t0: pd.Timestamp, t1: pd.Timestamp) -> float | None:
    s = series.loc[t0:t1].dropna()
    if len(s) < 2:
        return None
    return float(s.iloc[-1] / s.iloc[0] - 1)


def main(notify: bool = False):
    summaries = []
    spy = yf.download("SPY", start="2026-04-10", progress=False, auto_adjust=True)["Close"].squeeze()
    spy.index = pd.to_datetime(spy.index)

    # cycle boundaries: every 21 trading days from the anchor, on SPY's calendar
    cal = spy.index[spy.index >= CLEAN_START]
    bounds = list(cal[::CYCLE_DAYS])
    if bounds[-1] < cal[-1]:
        bounds.append(cal[-1])

    cycle_live: dict[int, dict] = {}   # acct -> {(a, b): live cycle return}
    cycle_spy: dict = {}
    for acct, strat in ACCOUNTS.items():
        live = load_live(acct)
        _, sig_r = run_portfolio(strat, start="2023-01-01")
        signal = (1 + sig_r.fillna(0)).cumprod()

        print(f"\n=== A{acct} ({strat}) — cycles since {CLEAN_START.date()} ===")
        print(f"{'cycle':22s} {'live':>8s} {'signal':>8s} {'drag':>7s} {'SPY':>8s} {'alpha':>7s}")
        tot = {"live": 1.0, "sig": 1.0, "spy": 1.0}
        cycle_live[acct] = {}
        for a, b in zip(bounds, bounds[1:]):
            lv = window_return(live, a, b)
            sg = window_return(signal, a, b)
            sp = window_return(spy, a, b)
            if lv is None or sp is None:
                continue
            cycle_live[acct][(a, b)] = lv
            cycle_spy[(a, b)] = sp
            tag = f"{a.date()} → {b.date()}"
            drag = f"{lv - sg:+7.2%}" if sg is not None else "      —"
            print(f"{tag:22s} {lv:+8.2%} {(f'{sg:+8.2%}' if sg is not None else '       —')} "
                  f"{drag} {sp:+8.2%} {lv - sp:+7.2%}")
            tot["live"] *= 1 + lv
            tot["spy"] *= 1 + sp
            if sg is not None:
                tot["sig"] *= 1 + sg
        lv, sg, sp = tot["live"] - 1, tot["sig"] - 1, tot["spy"] - 1
        print(f"{'CUMULATIVE':22s} {lv:+8.2%} {sg:+8.2%} {lv - sg:+7.2%} {sp:+8.2%} {lv - sp:+7.2%}")
        print(f"Q3 gate (alpha >= 0 over trailing cycles): "
              f"{'MET' if lv - sp >= 0 else 'NOT MET'} at {lv - sp:+.2%} cumulative")
        summaries.append(f"A{acct} alpha {lv - sp:+.1%}")

    # Synthetic book: weights re-applied at every cycle boundary.
    w = " / ".join(f"{int(v * 100)}% A{k}" for k, v in BOOK_WEIGHTS.items())
    print(f"\n=== BOOK (synthetic {w}, rebalanced each cycle) ===")
    print(f"{'cycle':22s} {'book':>8s} {'SPY':>8s} {'alpha':>7s}")
    tot_book, tot_spy = 1.0, 1.0
    for key, sp in cycle_spy.items():
        if any(key not in cycle_live[k] for k in BOOK_WEIGHTS):
            continue
        bk = sum(BOOK_WEIGHTS[k] * cycle_live[k][key] for k in BOOK_WEIGHTS)
        print(f"{f'{key[0].date()} → {key[1].date()}':22s} {bk:+8.2%} {sp:+8.2%} {bk - sp:+7.2%}")
        tot_book *= 1 + bk
        tot_spy *= 1 + sp
    bk, sp = tot_book - 1, tot_spy - 1
    print(f"{'CUMULATIVE':22s} {bk:+8.2%} {sp:+8.2%} {bk - sp:+7.2%}")
    summaries.append(f"book alpha {bk - sp:+.1%}")

    summaries.append(shadow_a4())
    if notify:
        from execution.notifications import notify_macos
        notify_macos("FIRE Weekly Scorecard", " | ".join(x for x in summaries if x))


A4_RETIRED = pd.Timestamp("2026-07-13")


def shadow_a4():
    """What the retired A4 strategy would have done since retirement.

    Honest re-litigation instrument: the account sits in cash, but the
    signal path keeps being computable. If the shadow rips while the cash
    sits, we want that fact surfaced on every scorecard run — retirement
    was a decision, and decisions get scored too. (Retirement rationale:
    HISTORY.md 2026-07-13 — walk-forward decay + unexplained-then-explained
    drag. A sustained shadow rally would reopen the slot conversation,
    starting with the basis-carry successor, not necessarily this strategy.)
    """
    _, r = run_portfolio("crypto_momentum_filtered", start="2025-01-01")
    post = r.loc[A4_RETIRED:].fillna(0)
    if len(post) < 2:
        return ""
    ret = float((1 + post).prod() - 1)
    btc = yf.download("BTC-USD", start=str(A4_RETIRED.date()), progress=False,
                      auto_adjust=True)["Close"].squeeze()
    btc_ret = float(btc.iloc[-1] / btc.iloc[0] - 1) if len(btc) > 1 else float("nan")
    in_market = float((post != 0).mean())
    print(f"\n=== SHADOW A4 (retired {A4_RETIRED.date()} — signal-only, would-have-been) ===")
    print(f"since retirement: strategy {ret:+.2%} | cash +0.00% | BTC {btc_ret:+.2%} "
          f"| signal in-market {in_market:.0%} of days")
    verdict = ("retirement cost nothing so far" if abs(ret) < 0.02
               else "shadow DIVERGING — revisit the slot conversation" if ret > 0.10
               else "retirement saving money" if ret < 0 else "shadow mildly positive — keep watching")
    print(f"read: {verdict}")
    return f"shadowA4 {ret:+.1%}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true", help="send macOS summary notification")
    main(notify=ap.parse_args().notify)
