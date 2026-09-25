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

from data.trading_dates import LIVE_CLOCK_START, REBALANCE_ANCHOR

# Cycle boundaries share the strategies' re-ranking phase by construction
# (counted from REBALANCE_ANCHOR); reporting starts at the live-tracking
# clock (2026-09-21, the first automated cycle — earlier cycles were traded
# on stale rankings, HISTORY.md 2026-09-09).
GRID_START = pd.Timestamp(REBALANCE_ANCHOR)
CLEAN_START = pd.Timestamp(LIVE_CLOCK_START)
CYCLE_DAYS = 21
ACCOUNTS = {1: "sm_filtered"}   # A2 retired 2026-09-25; the book is A1
# Retired strategies keep being scored so the retirement decisions are too.
SHADOWS = [
    (4, "crypto_momentum_filtered", "2026-07-13", "BTC-USD"),
    (2, "trend_lowvol", "2026-09-25", "SPY"),
]


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
    cal = spy.index[spy.index >= GRID_START]
    bounds = [b for b in cal[::CYCLE_DAYS] if b >= CLEAN_START]
    if bounds[-1] < cal[-1]:
        bounds.append(cal[-1])

    for acct, strat in ACCOUNTS.items():
        live = load_live(acct)
        _, sig_r = run_portfolio(strat, start="2023-01-01")
        signal = (1 + sig_r.fillna(0)).cumprod()

        print(f"\n=== A{acct} ({strat}) — cycles since {CLEAN_START.date()} ===")
        print(f"{'cycle':22s} {'live':>8s} {'signal':>8s} {'drag':>7s} {'SPY':>8s} {'alpha':>7s}")
        tot = {"live": 1.0, "sig": 1.0, "spy": 1.0}
        for a, b in zip(bounds, bounds[1:]):
            lv = window_return(live, a, b)
            sg = window_return(signal, a, b)
            sp = window_return(spy, a, b)
            if lv is None or sp is None:
                continue
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

    summaries.extend(shadow(*sh) for sh in SHADOWS)
    if notify:
        from execution.notifications import notify_macos
        notify_macos("Jim Weekly Scorecard", " | ".join(x for x in summaries if x))


def shadow(account: int, strategy_id: str, retired: str, benchmark: str) -> str:
    """What a retired strategy would have done since retirement.

    Honest re-litigation instrument: the account sits in cash, but the
    signal path keeps being computable. If the shadow rips while the cash
    sits, that fact is surfaced on every scorecard run — retirement was a
    decision, and decisions get scored too. (A4: HISTORY.md 2026-07-13 and
    2026-09-10; A2: 2026-09-25.)
    """
    r0 = pd.Timestamp(retired)
    _, r = run_portfolio(strategy_id, start="2025-01-01")
    post = r.loc[r0:].fillna(0)
    if len(post) < 2:
        return ""
    ret = float((1 + post).prod() - 1)
    bm = yf.download(benchmark, start=str(r0.date()), progress=False, auto_adjust=True)["Close"].squeeze()
    bm_ret = float(bm.iloc[-1] / bm.iloc[0] - 1) if len(bm) > 1 else float("nan")
    in_market = float((post != 0).mean())
    print(f"\n=== SHADOW A{account} ({strategy_id}, retired {r0.date()} — signal-only, would-have-been) ===")
    print(f"since retirement: strategy {ret:+.2%} | cash +0.00% | {benchmark} {bm_ret:+.2%} "
          f"| signal in-market {in_market:.0%} of days")
    # The +10% reopen trigger needs a sample: on 2026-09-10 it fired on a
    # two-month BTC rally while the fresh walk-forward's newest full-year
    # window read +3.8% / Calmar 0.26 (HISTORY.md 2026-09-10). Six months
    # minimum before "diverging" means anything.
    min_days = 126
    verdict = ("retirement cost nothing so far" if abs(ret) < 0.02
               else f"shadow +{ret:.0%} over {len(post)}d — too short to judge (needs {min_days}d)"
               if ret > 0.10 and len(post) < min_days
               else "shadow DIVERGING — revisit the slot conversation" if ret > 0.10
               else "retirement saving money" if ret < 0 else "shadow mildly positive — keep watching")
    print(f"read: {verdict}")
    return f"shadowA{account} {ret:+.1%}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true", help="send macOS summary notification")
    main(notify=ap.parse_args().notify)
